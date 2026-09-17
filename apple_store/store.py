import asyncio
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.async_api import async_playwright, Error as PlaywrightError

from .models import ApiError, Idempotency, Product, SessionInput


class StoreSession:
    BAG_URL = "https://www.apple.com.cn/shop/bag"
    ITEM = ".rs-bag-item"
    ADD = re.compile(r"^(添加到购物袋|加入购物袋)$")
    CHECKOUT = re.compile(r"^(结账|立即结账)$")

    def __init__(self, context, page):
        self.id = str(uuid4())
        self.context, self.page = context, page
        self.lock = asyncio.Lock()
        self.idempotency = Idempotency()
        self.phase = "new"
        self.product = None
        self.closed = False
        self.browser = self.runtime = None
        page.set_default_timeout(15_000)
        page.set_default_navigation_timeout(45_000)

    @classmethod
    async def create(cls, options: SessionInput):
        runtime = await async_playwright().start()
        browser = None
        try:
            browser = await runtime.chromium.launch(
                headless=options.headless, channel=os.getenv("BROWSER_CHANNEL", "msedge"))
            context = await browser.new_context(locale="zh-CN")
            session = cls(context, await context.new_page())
            session.runtime, session.browser = runtime, browser
            return session
        except BaseException:
            if browser:
                await browser.close()
            await runtime.stop()
            raise

    def require(self, *phases):
        if self.closed or self.page.is_closed():
            raise ApiError("SESSION_CLOSED", "浏览器会话已关闭", 410)
        if self.phase not in phases:
            raise ApiError("INVALID_STATE", f"当前状态 {self.phase}，需要 {' / '.join(phases)}")

    async def snapshot(self):
        self.require(self.phase)
        return dict(id=self.id, phase=self.phase, url=self.page.url,
                    title=await self.page.title(), page=await self.page.locator("body").aria_snapshot())

    async def configure(self, product: Product):
        self.require("new", "product", "configured")
        self.phase, self.product = "product", product
        await self.page.goto(product.url, wait_until="domcontentloaded")
        for choice in product.choices:
            locator = self.page.get_by_role(choice.role, name=choice.name, exact=True)
            if choice.role == "radio":
                await locator.check()
            elif choice.role == "combobox":
                await locator.select_option(label=choice.value)
            else:
                await locator.click()
        add = self.page.get_by_role("button", name=self.ADD)
        try:
            await add.wait_for(state="visible")
            if not await add.is_enabled():
                raise ApiError("CONFIGURATION_REQUIRED", "加购按钮不可用，请补全规格或核对库存")
        except PlaywrightError as error:
            raise ApiError("CONFIGURATION_REQUIRED", "未找到可用加购按钮，请读取会话页面补全选项") from error
        self.phase = "configured"
        return await self.snapshot()

    async def open_bag(self):
        await self.page.goto(self.BAG_URL, wait_until="domcontentloaded")

    async def bag_item(self):
        heading = self.page.get_by_role("heading", name=self.product.expected_bag_name, exact=True)
        row = self.page.locator(self.ITEM).filter(has=heading)
        await row.wait_for(state="visible")
        if await row.count() != 1:
            raise ApiError("BAG_AMBIGUOUS", "未能唯一识别指定商品")
        return row

    async def add(self):
        self.require("configured")
        self.phase = "add_unknown"  # A timeout may occur AFTER the server accepts the add.
        try:
            await self.page.get_by_role("button", name=self.ADD).click()
            name = re.compile(r"^(查看购物袋|检查购物袋)$")
            view = self.page.get_by_role("button", name=name).or_(self.page.get_by_role("link", name=name))
            checkout = self.page.get_by_role("button", name=self.CHECKOUT)
            await view.or_(checkout).first.wait_for(state="visible")
            if await view.count() and await view.first.is_visible():
                await view.first.click()
            await self.bag_item()
            self.phase = "bag"
            return await self.snapshot()
        except (PlaywrightError, ApiError) as error:
            raise ApiError("ADD_RESULT_UNKNOWN", "加购结果未确认，禁止自动重试；调用 GET bag 核对购物袋") from error

    async def bag(self):
        self.require("add_unknown", "bag", "quantity_unknown")
        await self.open_bag()
        await self.bag_item()
        self.phase = "bag"
        return await self.snapshot()

    async def quantity(self, quantity: int):
        self.require("bag")
        row = await self.bag_item()
        self.phase = "quantity_unknown"
        await row.get_by_role("combobox").select_option(str(quantity))
        await self.page.wait_for_load_state("networkidle")
        await self.open_bag()
        actual = await (await self.bag_item()).get_by_role("combobox").input_value()
        if actual != str(quantity):
            raise ApiError("QUANTITY_NOT_UPDATED", "购物袋数量未成功更新")
        self.phase = "bag"
        return await self.snapshot()

    async def checkout(self):
        self.require("bag")
        await self.bag_item()
        self.phase = "checkout_unknown"
        try:
            await self.page.get_by_role("button", name=self.CHECKOUT).click()
            await self.page.wait_for_url(lambda url: bool(re.search(r"/(checkout|signIn)(/|$)", urlsplit(url).path, re.I)))
        except PlaywrightError as error:
            raise ApiError("CHECKOUT_RESULT_UNKNOWN", "未确认进入结账页面，请读取会话状态") from error
        self.phase = "login_required" if "signin" in urlsplit(self.page.url).path.lower() else "checkout"
        return await self.snapshot()

    async def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.browser:
                await self.browser.close()
            else:
                await self.context.close()
        finally:
            if self.runtime:
                await self.runtime.stop()
