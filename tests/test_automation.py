import asyncio
import os
import unittest
from urllib.parse import urlsplit, parse_qs

import httpx
from playwright.async_api import async_playwright
from pydantic import ValidationError

from apple_store.models import ApiError, Idempotency, Product, Choice, Quantity
from apple_store.server import create_app
from apple_store.store import StoreSession


PRODUCT = Product(url="https://www.apple.com.cn/shop/product/example",
                  expectedBagName="示例商品", choices=[Choice(role="radio", name="标准款")])


class Contracts(unittest.IsolatedAsyncioTestCase):
    def test_validation(self):
        for url in ("http://www.apple.com.cn/shop/a", "https://apple.com.cn.evil.test/shop/a",
                    "https://evil.test/shop/a", "https://u:p@www.apple.com.cn/shop/a"):
            with self.assertRaises(ValidationError):
                Product(url=url, expectedBagName="示例商品")
        with self.assertRaises(ValidationError):
            Choice(role="button", name="提交订单")
        with self.assertRaises(ValidationError):
            Quantity(quantity=True)

    async def test_idempotency(self):
        cache = Idempotency()
        calls = []

        async def action():
            calls.append(1)
            return 42

        self.assertEqual(await asyncio.gather(cache.run("a", {}, action), cache.run("a", {}, action)), [42, 42])
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ApiError):
            await cache.run("a", {"different": True}, action)

        async def fail():
            calls.append(1)
            raise RuntimeError("uncertain")

        for _ in range(2):
            with self.assertRaises(RuntimeError):
                await cache.run("b", {}, fail)
        self.assertEqual(len(calls), 2)

    async def test_cancellation_does_not_repeat_action(self):
        cache, release, started = Idempotency(), asyncio.Event(), asyncio.Event()
        calls = []

        async def action():
            calls.append(1)
            started.set()
            await release.wait()
            return 42

        waiter = asyncio.create_task(cache.run("key", {}, action))
        await started.wait()
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        release.set()
        self.assertEqual(await cache.run("key", {}, action), 42)
        self.assertEqual(len(calls), 1)

    async def test_http(self):
        class Fake:
            id, phase = "test", "configured"
            lock = asyncio.Lock()
            idempotency = Idempotency()
            count = 0

            async def add(self):
                self.count += 1
                return {"phase": "bag"}

            async def close(self):
                pass

        session = Fake()

        async def factory(_):
            return session

        app = create_app("secret", factory)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                self.assertEqual((await client.get("/health")).status_code, 401)
                client.headers["Authorization"] = "Bearer secret"
                self.assertEqual((await client.get("/health", headers={"Origin": "https://evil.test"})).status_code, 403)
                self.assertEqual((await client.post("/sessions", json={})).status_code, 201)
                self.assertEqual((await client.put("/sessions/test/product", json={})).status_code, 422)
                self.assertEqual((await client.post("/sessions/test/bag/items")).status_code, 400)
                for _ in range(2):
                    response = await client.post("/sessions/test/bag/items", headers={"Idempotency-Key": "add"})
                    self.assertEqual(response.status_code, 200)
                self.assertEqual(session.count, 1)
                self.assertEqual((await client.delete("/sessions/test")).status_code, 204)
                self.assertEqual((await client.get("/sessions/test")).status_code, 404)


class BrowserFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.addAsyncCleanup(self.runtime.stop)
        self.browser = await self.runtime.chromium.launch(headless=True, channel=os.getenv("BROWSER_CHANNEL", "msedge"))
        self.addAsyncCleanup(self.browser.close)
        self.context = await self.browser.new_context()
        self.quantity, self.additions = "1", 0
        self.missing, self.login = False, False

        async def route_handler(route):
            url = urlsplit(route.request.url)
            if url.path == "/shop/product/example":
                html = """<h1>购买示例商品</h1><label><input type="radio" onclick="document.querySelector('button').disabled=false">标准款</label>
                <button disabled onclick="location.href='/shop/added'">添加到购物袋</button>"""
            elif url.path == "/shop/added":
                self.additions += 1
                html = '<h1>已添加</h1><a href="/shop/bag">查看购物袋</a>'
            elif url.path == "/shop/bag":
                options = ''.join(f'<option value="{n}" {"selected" if self.quantity == n else ""}>{n}</option>' for n in ("1", "2"))
                item = '' if self.missing else f'''<div class="rs-bag-item"><h2>示例商品</h2><select aria-label="数量" onchange="fetch('/quantity?q='+this.value)">{options}</select></div>'''
                target = "signIn" if self.login else "checkout"
                html = f'''<h1>购物袋</h1>{item}<button onclick="location.href='/shop/{target}'">结账</button>'''
            elif url.path == "/quantity":
                self.quantity = parse_qs(url.query)["q"][0]
                html = "ok"
            elif url.path == "/shop/checkout":
                html = '<h1>送货信息</h1><button>提交订单</button>'
            elif url.path == "/shop/signIn":
                html = '<h1>登录</h1><input type="password">'
            else:
                return await route.abort()
            await route.fulfill(content_type="text/html; charset=utf-8", body=html)

        await self.context.route("**/*", route_handler)
        self.session = StoreSession(self.context, await self.context.new_page())

    async def test_full_flow(self):
        with self.assertRaises(ApiError):
            await self.session.checkout()
        self.assertEqual((await self.session.configure(PRODUCT))["phase"], "configured")
        self.assertEqual((await self.session.add())["phase"], "bag")
        with self.assertRaises(ApiError):
            await self.session.add()
        await self.session.quantity(2)
        self.assertEqual(self.quantity, "2")
        self.assertEqual((await self.session.checkout())["phase"], "checkout")
        self.assertEqual(await self.session.page.get_by_role("button", name="提交订单").count(), 1)
        self.assertEqual(self.additions, 1)

    async def test_unknown_add_blocks_retry(self):
        self.missing = True
        self.session.page.set_default_timeout(800)
        await self.session.configure(PRODUCT)
        with self.assertRaises(ApiError) as caught:
            await self.session.add()
        self.assertEqual(caught.exception.code, "ADD_RESULT_UNKNOWN")
        self.assertEqual(self.session.phase, "add_unknown")
        with self.assertRaises(ApiError):
            await self.session.add()
        self.assertEqual(self.additions, 1)
        self.missing = False
        self.assertEqual((await self.session.bag())["phase"], "bag")

    async def test_login_redirect(self):
        self.login = True
        await self.session.configure(PRODUCT)
        await self.session.add()
        self.assertEqual((await self.session.checkout())["phase"], "login_required")


if __name__ == "__main__":
    unittest.main()
