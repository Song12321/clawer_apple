"""准备真实结账上下文，人工认证后保持浏览器供 main.py 接续。"""
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apple_store import apple_order as base
from apple_store import network
from config.config import RUN, selected_accounts
from contextlib import contextmanager, ExitStack
from order import bag_page_for_checkout, browser_cookies, log_bag, log_session
from apple_store.request_log import account_name
from playwright.sync_api import sync_playwright, Error as BrowserError, TimeoutError as BrowserTimeout

BAG_URL = "https://www.apple.com.cn/shop/bag"


CheckoutExpired = base.CheckoutExpired


AUTH_REQUIRED = ("[需要人工认证] Apple 要求安全结账登录或双重认证。"
                 "请在该账号浏览器窗口完成认证，停在配送／自提页面后重新运行 main.py；"
                 "当前账号已停止，未自动转访客结账。")


def live_endpoint(config):
    """该账号的常驻会话在运行时返回它的 CDP 地址，否则返回 None。"""
    endpoint = f"http://127.0.0.1:{config['调试端口']}"
    try:
        urllib.request.urlopen(endpoint + "/json/version", timeout=1).read()
    except Exception:
        return None
    return endpoint


def wait_ready(endpoint, process, timeout=30):
    # 防呆：曾经把"未运行时返回的 None"当成端点传进来，导致 30 秒后才报"端口未就绪"。
    if not isinstance(endpoint, str) or not endpoint.startswith("http://127.0.0.1:"):
        raise ValueError(f"调试端点非法：{endpoint!r}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Chrome 启动后立即退出（退出码 {process.returncode}）；通常是资料目录已被另一个 Chrome 占用")
        try:
            urllib.request.urlopen(endpoint + "/json/version", timeout=1).read()
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Chrome 调试端口未就绪")


def spawn_chrome(args):
    """把会话浏览器从本进程的进程树里分离，避免宿主停止时连带关闭登录态。

    典型场景：在 IDE 的同一个运行标签里启动 main.py 会先终止正在运行的 session.py；
    若 Chrome 属于该进程树，登录态就会一起消失。分离后 Chrome 继续存活，main.py 仍可复用。
    """
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(args, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        # 某些作业对象不允许 breakaway，退回到仅新建进程组。
        return subprocess.Popen(args, creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def page_response(page):
    response = base.requests.Response()
    response.status_code = 200
    response.url = page.url
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response._content = page.content().encode("utf-8")
    return response


def require_fulfillment(response):
    path = urlsplit(response.url).path
    if path == "/shop/sorry/session_expired":
        raise CheckoutExpired("结账会话已过期")
    if path == "/shop/signIn":
        raise RuntimeError(AUTH_REQUIRED)
    if path == "/shop/checkout/interstitial":
        raise ValueError("[已有订单结果] 当前结账已进入订单结果页，并非登录过期；"
                         "停止，避免重复下单。请核对 results.jsonl 中的成功记录；"
                         "如需另下一单，需先准备新的结账上下文。")
    if path == "/shop/checkout/status":
        raise ValueError("[订单处理中] 当前结账已进入订单处理阶段；"
                         "停止，请先核实订单结果，不自动重新下单。")
    if response.status_code != 200 or urlsplit(response.url).path != "/shop/checkout":
        raise ValueError("服务端未返回预期结账页面；停止，不自动重建结账")
    model = base.read_model(response, allow_pickup_unavailable=True)
    if "signIn" in model or base.require(model, "checkout", "d", "page") != "Fulfillment":
        raise ValueError("当前结账不在 Fulfillment 阶段；停止，不自动重建或重复提交")
    return model


def prepared_page(browser):
    apple_pages = [p for context in browser.contexts for p in context.pages
                   if (urlsplit(p.url).hostname or "").endswith(".apple.com.cn")]
    for page in apple_pages:
        if urlsplit(page.url).path == "/shop/signIn":
            page.bring_to_front()
            raise RuntimeError(AUTH_REQUIRED)
    pages = [p for context in browser.contexts for p in context.pages
             if urlsplit(p.url).path == "/shop/checkout"
             and (urlsplit(p.url).hostname or "").endswith(".apple.com.cn")]
    if not pages:
        if any(urlsplit(p.url).path in ("/shop/checkout/status", "/shop/checkout/interstitial")
               for p in apple_pages):
            raise ValueError("浏览器停在订单处理或结果页；停止，请先核实已有订单")
        raise CheckoutExpired("未找到可接续的结账页面")
    if len(pages) != 1:
        raise ValueError("存在多个结账页面，无法确定当前上下文；停止")
    require_fulfillment(page_response(pages[0]))
    return pages[0]


def login_state(endpoint):
    # 只读取现有页面，不发探针请求、不刷新正在认证的页面。
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(endpoint)
        try:
            prepared_page(browser)
        except RuntimeError as error:
            return str(error)
        except ValueError:
            return "本地结账页面未就绪；main.py 将检查是否可自动准备"
    return "本地结账页面就绪（服务端有效性在 main.py 执行时验证）"


@contextmanager
def prepared_session(endpoint, capture_proxy=False, *, proxy_url):
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(endpoint)
        base.require_browser_proxy(browser, proxy_url)
        page = prepared_page(browser)
        with base.requests.Session() as session:
            base.configure_proxy(session, proxy_url, capture_proxy)
            session.headers["User-Agent"] = page.evaluate("navigator.userAgent")
            session.headers["Accept-Language"] = page.evaluate("navigator.language")
            # 包括 secure 主机的 host-only Cookie，不能只取商品／履约域名。
            base.copy_browser_cookies(session, base.read_page_cookies(page, [page.url, BAG_URL]))
            log_session(session, page, "接续结账：浏览器到requests")
            # 使用同一次请求取得的会话状态与 Fulfillment 模型接续结账。
            response = base.follow_navigation(session, base.request(session, "GET", page.url))
            if urlsplit(response.url).path == "/shop/signIn":
                browser_cookies(session, page)
                page.goto(response.url, wait_until="domcontentloaded", timeout=30000)
                page.bring_to_front()
            require_fulfillment(response)
            yield session, page, response


@contextmanager
def ready_session(account):
    """只在进入业务流程前恢复一次；yield 后的错误绝不触发重建或重下单。"""
    endpoint = live_endpoint(account)
    if endpoint is None:
        raise RuntimeError("常驻浏览器不可用；请先启动 session.py")
    name = account["账号"]
    print(f"[{name}] 连接诊断 | CDP={endpoint} | 配置资料目录={Path(account['资料目录']).resolve()}", flush=True)
    with network.pause_rotation(), ExitStack() as stack:
        print(f"[{name}] 正在验证服务端结账会话。", flush=True)
        try:
            ready = stack.enter_context(prepared_session(endpoint, account["使用抓包代理"], proxy_url=account["代理地址"]))
        except CheckoutExpired:
            print(f"[{name}] 结账上下文缺失或已过期；复用账号登录态自动准备一次。", flush=True)
            prepare_checkout(account, endpoint, force=True)
            ready = stack.enter_context(prepared_session(endpoint, account["使用抓包代理"], proxy_url=account["代理地址"]))
            print(f"[{name}] 自动恢复成功，无需人工登录；继续执行。", flush=True)
        else:
            print(f"[{name}] 服务端结账会话有效；继续执行。", flush=True)
        yield ready


def checkout_in_browser(session, page, sku, quantity, total):
    """使用官网结账事件和浏览器会话准备入口；不提交订单。"""
    browser_cookies(session, page)
    response = page.goto(BAG_URL, wait_until="networkidle", timeout=30000)
    if response is None or response.status != 200:
        raise ValueError("浏览器购物袋未返回 HTTP 200")
    model = base.read_model(page_response(page))
    log_bag(model, sku, quantity, "写回Cookie后浏览器购物袋")
    base.check_bag(model, sku, quantity)
    if base.require(model, "shoppingCart", "summary", "d", "total") != total:
        raise ValueError("浏览器购物袋金额与已验证购物袋不一致")
    target = base.apple_url(page.url, base.require(model, "shoppingCart", "actions", "a", "checkout", "url"))
    with page.expect_response(lambda r: r.url == target and r.request.method == "POST", timeout=30000) as pending:
        page.locator('[id="shoppingCart.actions.checkout"]').click(timeout=30000)
    response = pending.value
    if response.status != 200:
        raise RuntimeError(f"浏览器购物袋结账失败：HTTP {response.status}；未自动重试")
    # 跨主机导航后旧响应体可能已不可读取，以最终页面验证结账结果。
    page.wait_for_url(lambda url: (urlsplit(url).hostname or "").endswith(".apple.com.cn")
                      and urlsplit(url).path in ("/shop/signIn", "/shop/checkout", "/shop/sorry/session_expired"),
                      wait_until="domcontentloaded", timeout=30000)
    page.bring_to_front()
    if urlsplit(page.url).path != "/shop/signIn":
        require_fulfillment(page_response(page))


def retry_after_seconds(value):
    if not value:
        return 0
    if value.isdigit():
        return int(value)
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            raise ValueError("Retry-After 日期缺少时区")
        return max(0, (date - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        raise ValueError("入口 Retry-After 格式非法；停止") from None


def wait_product_entry(page, url, config):
    """只重试商品页读取；返回成功导航，后续交接和写入不在循环内。"""
    interval = RUN["入口重试间隔秒"]
    rotation = RUN["入口轮转间隔秒"]
    for name, value, allow_zero in (("入口重试间隔秒", interval, False),
                                    ("入口轮转间隔秒", rotation, True)):
        if (type(value) not in (int, float) or not math.isfinite(value)
                or value < 0 or (not allow_zero and value == 0)):
            raise ValueError(name + " 配置非法")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "www.apple.com.cn" or not parsed.path.startswith("/shop/buy-iphone/"):
        raise ValueError("入口必须是苹果中国大陆 iPhone 商品页")
    for key in ("机型", "颜色", "容量"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError("商品配置非法：" + key)
    attempt = 0
    while True:
        attempt += 1
        delay = interval
        reason = "未返回预期商品数据"
        with network.browser_entry(config["代理地址"], rotation):
            if page.is_closed() or not page.context.browser.is_connected():
                raise RuntimeError("浏览器已断开，停止入口等待")
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except BrowserTimeout:
                reason = "商品页访问超时"
                page.evaluate("window.stop()")
                response = None
            except BrowserError as error:
                # 仅已知临时网络错误重试；浏览器关闭、证书和调用错误直接停止。
                if not any(code in str(error) for code in (
                    "net::ERR_CONNECTION_RESET", "net::ERR_CONNECTION_CLOSED",
                    "net::ERR_CONNECTION_TIMED_OUT", "net::ERR_TIMED_OUT",
                    "net::ERR_PROXY_CONNECTION_FAILED", "net::ERR_TUNNEL_CONNECTION_FAILED",
                    "net::ERR_NAME_NOT_RESOLVED", "net::ERR_EMPTY_RESPONSE")):
                    raise
                reason = "商品页网络暂不可用"
                response = None
            if response is not None:
                target = urlsplit(page.url)
                if target.path == "/shop/signIn" or "idmsa.apple.com" == target.hostname:
                    raise RuntimeError(AUTH_REQUIRED)
                if target.hostname != "www.apple.com.cn":
                    raise RuntimeError("商品入口跳转到其他主机；停止并检查浏览器")
                if response.status in (401, 403, 407):
                    raise RuntimeError(f"商品入口明确拒绝访问：HTTP {response.status}；请检查浏览器")
                # 空响应/无 body 的错误页同样属于入口未就绪，不等待 DOM 元素。
                text = page.evaluate("document.body ? document.body.innerText : ''")
                if any(marker in text.lower() for marker in (
                    "验证码", "验证你是真人", "verify you are human", "access denied")):
                    raise RuntimeError("商品入口要求人工验证或拒绝访问；请检查浏览器")
                delay = max(delay, retry_after_seconds(response.all_headers().get("retry-after")))
                if response.status == 200:
                    html = response.body().decode("utf-8")
                    if "productSelectionData:" in html:
                        # 已有商品结构时严格检查；选配错误不能当维护页吞掉。
                        base.select_product(html, config)
                        print(f"[{config['账号']}] 商品入口已就绪（第 {attempt} 次）；接续当前会话。", flush=True)
                        return response
                reason = f"入口未就绪（HTTP {response.status}）"
        print(f"[{config['账号']}] {reason}；第 {attempt} 次，{delay:g} 秒后重试。", flush=True)
        # 分段等待，及时响应 Ctrl+C，并让浏览器事件正常分发。
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            page.wait_for_timeout(min(250, max(1, (deadline - time.monotonic()) * 1000)))


@network.pause_rotation()
def prepare_checkout(account, endpoint, *, force=False):
    config = {**account, "允许访客结账": False, "使用抓包代理": RUN["使用抓包代理"], "代理地址": RUN["代理地址"]}
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(endpoint)
        base.validate_proxy(config["代理地址"], config["使用抓包代理"])
        base.require_browser_proxy(browser, config["代理地址"])
        # 已准备的页面或尚待人工完成的认证页都不重新创建结账。
        for context in browser.contexts:
            for page in context.pages:
                host = urlsplit(page.url).hostname or ""
                path = urlsplit(page.url).path
                if host.endswith(".apple.com.cn") and path == "/shop/checkout":
                    require_fulfillment(page_response(page))
                    if not force:
                        return
                if host.endswith(".apple.com.cn") and path == "/shop/signIn":
                    page.bring_to_front()
                    return
        with base.browser_session(pw, config["商品页面"], include_page=True,
                                  cdp_endpoint=endpoint,
                                  capture_proxy=config["使用抓包代理"], proxy_url=config["代理地址"],
                                  entry_loader=lambda page, url: wait_product_entry(page, url, config)) as (session, page, product_page):
            log_session(session, page, "准备加购：浏览器到requests")
            product = base.select_product(product_page.content, config)
            bag = bag_page_for_checkout(session, product_page, config, product)
            model = base.read_model(bag)
            log_bag(model, product["partNumber"], config["数量"], "准备阶段加购或复用后")
            base.check_bag(model, product["partNumber"], config["数量"])
            checkout_in_browser(session, page, product["partNumber"], config["数量"],
                                base.require(model, "shoppingCart", "summary", "d", "total"))


def main():
    base.validate_proxy(RUN["代理地址"], RUN["使用抓包代理"])
    if not base.CHROME_PATH.is_file():
        raise ValueError("找不到 Chrome，请检查 CHROME_PATH")
    accounts = selected_accounts()
    print("本次准备账号：" + "、".join(account["账号"] for account in accounts), flush=True)
    sessions = []
    try:
        for account in accounts:
            endpoint = f"http://127.0.0.1:{account['调试端口']}"
            process = None
            if not live_endpoint(account):
                profile = str(Path(account["资料目录"]).resolve())
                Path(profile).mkdir(parents=True, exist_ok=True)
                process = spawn_chrome([
                    str(base.CHROME_PATH), f"--user-data-dir={profile}",
                    f"--remote-debugging-port={account['调试端口']}", "--remote-debugging-address=127.0.0.1",
                    "--no-first-run", "--no-default-browser-check", f"--proxy-server={RUN['代理地址']}", BAG_URL,
                ])
                sessions.append((account["账号"], endpoint, process))
                wait_ready(endpoint, process)
            else:
                sessions.append((account["账号"], endpoint, None))
            print(f"[{account['账号']}] 连接诊断 | CDP={endpoint} | 配置资料目录={Path(account['资料目录']).resolve()}", flush=True)
            token = account_name.set(account["账号"])
            try:
                prepare_checkout(account, endpoint)
            finally:
                account_name.reset(token)
            print(f"[{account['账号']}] {login_state(endpoint)}", flush=True)
        print("仅出现‘需要人工认证’时，请在对应窗口完成安全结账登录及双重认证。", flush=True)
        print("另开终端运行 .venv/Scripts/python.exe v2/main.py；结账过期时会自动准备一次。", flush=True)
        print("保持窗口打开；main.py 启动后不要操作页面。Ctrl+C 只停止本脚本，保留浏览器。", flush=True)
        while True:
            time.sleep(300)
            summary = "，".join(f"{name}={login_state(endpoint)}" for name, endpoint, _ in sessions)
            print(f"[{time.strftime('%H:%M')}] {summary}", flush=True)
    except KeyboardInterrupt:
        print("收到退出信号；保持已启动 Chrome 会话，不自动关闭浏览器。", flush=True)
    finally:
        # Chrome 使用独立进程运行，用户可能需要继续观察购物袋、完成登录或处理认证。
        # 不在这里 terminate，避免 IDE 停止 Python 后会话窗口立即消失。
        pass


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit("停止：" + str(error)) from None
