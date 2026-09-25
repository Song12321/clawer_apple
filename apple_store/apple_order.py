"""Apple 商城请求流程；未确认的接口契约必须补齐后才能创单。"""

import json
import re
import time
import socket
import ssl
import subprocess
import tempfile
from contextlib import ExitStack, contextmanager
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlencode, parse_qsl, urlunsplit

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Error as BrowserError
if __package__:
    from .network import fetch
    from .request_log import request_label, timing, response_timing
else:
    from network import fetch
    from request_log import request_label, timing, response_timing


# 本机使用 Reqable 抓包代理，显式信任其根证书，仍然校验 HTTPS 证书。
REQABLE_CA = Path.home() / "AppData/Roaming/Reqable/certificate/reqable-root.crt"
# 显式经过当前已确认监听的 Reqable 端口，避免系统代理关闭后证书与链路不匹配。
REQABLE_PROXY = "http://127.0.0.1:9000"

PICKUP_UNAVAILABLE = "你所在的地区无货可取。请尝试重新搜索。"


class CheckoutExpired(ValueError):
    """明确的结账过期；仅由下单前的调用方决定是否恢复。"""


class HTTP541Error(RuntimeError):
    """HTTP 541；由具体业务动作决定是否允许重试。"""


def pickup_unavailable(model):
    checkout = model.get("checkout", {})
    locator = checkout.get("fulfillment", {}).get("pickupTab", {}).get("pickup", {}).get("storeLocator", {})
    return checkout.get("d", {}).get("page") == "Fulfillment" and any(
        isinstance(message, dict) and message.get("level") == "ERROR"
        and message.get("text") == PICKUP_UNAVAILABLE for message in locator.get("m", []))


def is_reqable_available():
    if not REQABLE_CA.is_file():
        return False
    try:
        with socket.create_connection(("127.0.0.1", 9000), timeout=0.2):
            return True
    except OSError:
        return False


def validate_proxy(proxy_url, capture_proxy=False):
    if capture_proxy and proxy_url:
        raise ValueError("Clash 代理与 Reqable 抓包不能同时启用")
    parsed = urlsplit(proxy_url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or not parsed.port or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("代理地址须为 http://127.0.0.1:端口")


def configure_proxy(session, proxy_url, capture_proxy=False):
    validate_proxy(proxy_url, capture_proxy)
    session.trust_env = False
    session.proxies = {"http": proxy_url, "https": proxy_url}


def require_browser_proxy(browser, proxy_url):
    """读取本机 Chrome 启动参数，不操作账号业务页面。"""
    validate_proxy(proxy_url)
    page = browser.contexts[0].new_page()
    try:
        page.goto("chrome://version")
        command = page.locator("#command_line").inner_text()
        args = command.split()
        if f"--proxy-server={proxy_url}" not in args or "--no-proxy-server" in args:
            raise RuntimeError("已有 Chrome 未使用配置代理；请关闭该账号浏览器后重新运行 session.py")
    finally:
        page.close()


def copy_browser_cookies(session, cookies):
    """保留浏览器 Cookie 的实际作用域和有效期，不输出或落盘凭据。"""
    session.cookies.clear()
    for item in cookies:
        domain = item["domain"]
        if domain.lstrip(".") != "apple.com.cn" and not domain.endswith(".apple.com.cn"):
            continue
        expiry = item["expires"]
        if expiry != -1 and expiry <= time.time():
            continue
        # CDP 对未显式声明 SameSite 的 Cookie 不返回该属性，保留缺省语义。
        rest = {}
        if "sameSite" in item:
            rest["SameSite"] = item["sameSite"]
        if item["httpOnly"]:
            rest["HttpOnly"] = None
        session.cookies.set_cookie(Cookie(
            version=0, name=item["name"], value=item["value"],
            port=None, port_specified=False, domain=domain,
            domain_specified=domain.startswith("."), domain_initial_dot=domain.startswith("."),
            path=item["path"], path_specified=True, secure=item["secure"],
            expires=None if expiry == -1 else int(expiry), discard=expiry == -1,
            comment=None, comment_url=None, rest=rest, rfc2109=False,
        ))
    if not session.cookies:
        raise ValueError("未读取到商城 Cookie，停止发送无会话请求")


def read_page_cookies(page, urls):
    """从实际页面读取 Cookie，避免 CDP 附加隐身窗口时误读默认上下文。"""
    client = page.context.new_cdp_session(page)
    try:
        return client.send("Network.getCookies", {"urls": urls})["cookies"]
    finally:
        client.detach()


# 使用独立临时目录，不连接或修改日常 Chrome 用户目录。
CHROME_PATH = Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"


@contextmanager
def _handoff(page, product_url, *, include_page=False, capture_proxy=False, proxy_url=None):
    """在已打开的页面上完成官网校验与 Cookie/请求头交接。

    本函数不打开也不关闭浏览器：浏览器来自本次启动还是常驻会话由调用方决定。
    """
    initialization_started = time.perf_counter()
    page.add_init_script("""
        window.addEventListener('shldDone', event => {
            window.__appleVerificationEvent = event.detail.id;
        });
    """)
    navigation = page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
    if navigation is None or navigation.status != 200:
        raise RuntimeError("浏览器商品页未返回 HTTP 200")
    page.wait_for_function("window.__appleVerificationEvent !== undefined", timeout=30000)
    if page.evaluate("window.__appleVerificationEvent") != "shld-result":
        raise RuntimeError("官网浏览器验证未通过")
    # 商品页配送提示不是结账前置契约；真实可用性由后续购物袋、购买摘要和结账校验。
    headers = {k: v for k, v in navigation.request.all_headers().items()
               if not k.startswith(":") and k not in ("cookie", "host", "accept-encoding", "referer")}
    with requests.Session() as session:
        session.trust_env = False
        if proxy_url is not None:
            configure_proxy(session, proxy_url, capture_proxy)
        elif capture_proxy:
            if not is_reqable_available():
                raise RuntimeError("配置要求经 Reqable 抓包，但 127.0.0.1:9000 未监听")
            session.proxies = {"http": REQABLE_PROXY, "https": REQABLE_PROXY}
            session.verify = str(REQABLE_CA)
            print("Python 请求经 Reqable 抓包代理转发（配置：使用抓包代理）。", flush=True)
        else:
            print("Python 请求直连，未经 Reqable 代理；需要抓包时把配置「使用抓包代理」设为 True。", flush=True)
        # 页面校验完成不代表异步 /shop/beacon/atb 已下发加购令牌。
        # 交接前等待浏览器 Cookie 就绪；不重放 beacon，不编造令牌。
        deadline = time.monotonic() + 10
        while True:
            copy_browser_cookies(session, read_page_cookies(page, [product_url]))
            tokens = atb_tokens(session, product_url)
            if len(tokens) == 1 and tokens[0].split("|")[-1]:
                break
            if len(tokens) > 1:
                raise ValueError(f"会话交接发现 {len(tokens)} 个适用的 as_atb Cookie；作用域冲突，未加购")
            if time.monotonic() >= deadline:
                state = "未下发" if not tokens else "令牌尾段为空"
                raise ValueError(f"等待浏览器加购令牌 10 秒仍未就绪：as_atb {state}；未加购")
            page.wait_for_timeout(250)
        session.headers.update(headers)
        print(f"浏览器页面与 Cookie 已交接，业务会话由后续请求验证。会话交接合计 {time.perf_counter() - initialization_started:.3f}s", flush=True)
        if include_page:
            product_page = requests.Response()
            product_page.status_code = navigation.status
            product_page.url = navigation.url
            product_page.headers.update(navigation.all_headers())
            product_page._content = navigation.body()
            product_page.encoding = "utf-8"
            yield session, page, product_page
        else:
            yield session


def live_page(browser):
    """取常驻浏览器的可用页面；没有页面时明确报错，不自己新建上下文。"""
    contexts = browser.contexts
    if not contexts or not contexts[0].pages:
        raise RuntimeError("常驻浏览器没有打开的页面；请重启 v2/session.py")
    return contexts[0].pages[0]


@contextmanager
def browser_session(playwright, product_url, *, include_page=False, profile_dir=None, cdp_endpoint=None,
                    capture_proxy=False, proxy_url=None):
    """打开或连接浏览器并完成会话交接；浏览器和 requests 共用显式代理（传入时）。

    cdp_endpoint 给定时连接常驻浏览器（v2/session.py），既不启动也不关闭它；
    profile_dir 给定时使用固定资料目录且不加 --incognito，登录态在目录内保留；
    两者都不给时保持原来的临时目录加隐身模式。
    """
    if proxy_url is not None:
        validate_proxy(proxy_url, capture_proxy)
    print("开始浏览器初始化与会话交接。", flush=True)
    if cdp_endpoint is not None:
        browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
        if proxy_url is not None:
            require_browser_proxy(browser, proxy_url)
        print(f"已连接常驻浏览器会话：{cdp_endpoint}", flush=True)
        with _handoff(live_page(browser), product_url, include_page=include_page, capture_proxy=capture_proxy, proxy_url=proxy_url) as result:
            yield result
        return
    if not CHROME_PATH.is_file():
        raise ValueError("找不到 Chrome，请检查 CHROME_PATH")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    proxy_arg = f"--proxy-server={proxy_url}" if proxy_url is not None else "--no-proxy-server"
    with ExitStack() as resources:
        if profile_dir is None:
            profile = resources.enter_context(tempfile.TemporaryDirectory(prefix="apple-session-"))
            incognito_args = ["--incognito"]
        else:
            profile = str(Path(profile_dir).resolve())
            Path(profile).mkdir(parents=True, exist_ok=True)
            incognito_args = []
            print(f"使用固定浏览器资料目录：{profile}（登录态保存在目录内，不要提交到版本库）", flush=True)
        process = subprocess.Popen([
            str(CHROME_PATH), f"--user-data-dir={profile}",
            f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
            proxy_arg, "--no-first-run", "--no-default-browser-check",
            *incognito_args, "about:blank",
        ], creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = None
        try:
            endpoint = f"http://127.0.0.1:{port}"
            # 仅等待本机进程启动，不重试网站业务请求。
            with requests.Session() as local:
                local.trust_env = False
                deadline = time.monotonic() + 15
                while True:
                    try:
                        local.get(endpoint + "/json/version", timeout=1).raise_for_status()
                        break
                    except requests.RequestException:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError("Chrome 调试连接启动失败") from None
                        time.sleep(0.25)
            browser = playwright.chromium.connect_over_cdp(endpoint)
            with _handoff(browser.contexts[0].pages[0], product_url, include_page=include_page,
                          capture_proxy=capture_proxy, proxy_url=proxy_url) as result:
                yield result
        finally:
            try:
                if browser is not None:
                    # connect_over_cdp 的 close 只断开连接，先退出本次独立进程。
                    browser.new_browser_cdp_session().send("Browser.close")
                    browser.close()
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
                # 等待 Chrome 释放资料目录；临时目录由 TemporaryDirectory 清理，固定目录保留。
                time.sleep(1)

# 用户配置集中在这里；不保存 Cookie、验证码或历史会话令牌。
# 机型、颜色、容量使用商品页面中的 familyType、dimensionColor、dimensionCapacity。
CONFIG = {
    "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-17/mg714ch/a",
    "机型": "iphone17",  # iPhone 17
    "颜色": "sage",  # 鼠尾草绿色
    "容量": "256gb",
    "数量": 1,
    "自提门店": "R448",  # Apple 王府井；历史样本门店，不代表当前有货。
    # 运行前填写本次订单的真实联系人信息。
    "姓": "xing",
    "名": "min",
    "手机号": "17862852279",
    "邮箱": "17862852279@163.com",
    "发票类型": "e_personal_fdf",  # 沿用抓包中的个人发票类型。
    "支付方式": "ALIPAY",  # 支付宝
}


# 每个元素对应独立会话；需要多组时添加配置字典，顺序执行，不共享购物袋。
SESSION_CONFIGS = [CONFIG]


def require(data, *path):
    """按完整键名读取必填数据，键名本身可以含有点号。"""
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"响应缺少字段：{' / '.join(path)}")
        current = current[key]
    if current is None:
        raise ValueError(f"响应字段为空：{' / '.join(path)}")
    return current


def apple_url(base_url, target):
    if not isinstance(target, str) or not target.strip():
        raise ValueError("请求地址为空或格式错误")
    url = urljoin(base_url, target)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".apple.com.cn")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise ValueError("请求地址不是 Apple 中国商城 HTTPS 地址")
    return url


def validate_config(config):
    for key in CONFIG:
        value = require(config, key)
        if key == "数量":
            if type(value) is not int or value < 1:
                raise ValueError("数量必须为正整数")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"请填写配置：{key}")
    apple_url("", config["商品页面"])


def ssl_failure_detail(error):
    """只提取 SSL 诊断字段，不输出可能含请求凭据的异常全文。"""
    pending, seen, details = [error], set(), []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ssl.SSLError):
            fields = [type(current).__name__]
            for name in ("library", "reason"):
                value = getattr(current, name, None)
                if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
                    fields.append(f"{name}={value}")
            code = getattr(current, "verify_code", None)
            if isinstance(code, int):
                fields.append(f"verify_code={code}")
            details.append(", ".join(fields))
        pending.extend(item for item in (
            getattr(current, "reason", None), current.__cause__, current.__context__,
            *current.args,
        ) if isinstance(item, BaseException))
    return "; ".join(dict.fromkeys(details)) or "SSLError（底层结构化原因不可用）"


def request(session, method, url, *, headers=None, form=None):
    # 不自动重试或重定向：未知跳转不能被当作成功，创单也不能重复提交。
    url = apple_url("", url)
    try:
        with timing(request_label(method, url)) as log:
            response = fetch(session,
                method, url, headers=headers, data=form,
                timeout=30, allow_redirects=False,
            )
            response_timing(log, response)
    except requests.exceptions.SSLError as error:
        raise RuntimeError(f"HTTPS SSL 失败：{ssl_failure_detail(error)}；未自动重试") from None
    except requests.exceptions.ProxyError:
        raise RuntimeError("代理连接失败；请检查 Reqable 是否运行及代理端口") from None
    except requests.exceptions.Timeout:
        raise RuntimeError("请求超时；未自动重试") from None
    except requests.exceptions.ConnectionError:
        raise RuntimeError("网络连接失败；请检查网络与代理连接") from None
    except requests.RequestException:
        # requests 的原始异常可能包含带动态凭据的 URL，不直接打印。
        raise RuntimeError("请求失败或超时；未自动重试，需先确认服务端处理结果") from None
    if response.status_code == 541:
        parsed = urlsplit(url)
        # 只标识接口动作，不输出查询中的会话凭据或整个 URL。
        action = dict(parse_qsl(parsed.query)).get("_a", "")
        action_label = f"，动作 {action}" if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", action) else ""
        raise HTTP541Error(
            f"requests 收到 HTTP 541：{method} {parsed.hostname}{parsed.path}{action_label}；"
            "未取得有效业务响应。"
        )
    if not 200 <= response.status_code < 400:
        raise RuntimeError(f"收到未处理的 HTTP 状态：{response.status_code}")
    return response


def follow_navigation(session, response):
    """处理已确认的 HTTP/JSON 页面跳转，不重复提交原来的业务动作。"""
    seen = set()
    for _ in range(10):
        if response.status_code in (301, 302, 303):
            target = response.headers.get("Location")
        elif 300 <= response.status_code < 400:
            raise ValueError("该 HTTP 跳转需要核对请求方法，停止自动跟随")
        elif response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() == "application/json":
            payload = parse_json(response.text)
            status = require(payload, "head", "status")
            if type(status) in (int, str) and status in (200, "200"):
                return response
            if type(status) not in (int, str) or status not in (302, "302"):
                raise ValueError("业务响应没有返回成功模型或已确认的跳转")
            data = require(payload, "head", "data")
            # checkout.js 的 hn 函数在未声明 method 时按 GET 导航。
            if "method" in data and data["method"].lower() != "get":
                raise ValueError("业务跳转要求非 GET 方法，需要核对该分支")
            if data.get("args"):
                raise ValueError("业务跳转带有尚未验证的 args，停止自动跟随")
            target = require(data, "url")
        else:
            return response
        target = apple_url(response.url, target)
        if target in seen:
            raise ValueError("页面发生循环跳转")
        seen.add(target)
        response = request(session, "GET", target, headers={"Referer": response.url})
    raise ValueError("页面跳转次数超过限制")


def post_action(session, page_url, model, module_path, action_name, form, *, extra_headers=None):
    # checkout.js/createAjax/fetchOrbit 确认模型动作统一使用 POST 表单。
    module = require(model, *module_path)
    url = apple_url(page_url, require(module, "a", action_name, "url"))
    headers = model_headers(model)
    if extra_headers:
        headers.update(extra_headers)
    origin = urlsplit(page_url)
    headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "Fetch",
        "Referer": page_url,
        "Origin": f"{origin.scheme}://{origin.netloc}",
    })
    fields = {}
    for key, value in form.items():
        if type(value) not in (str, int, bool):
            raise ValueError(f"表单字段类型错误：{key}")
        fields[key] = str(value).lower() if isinstance(value, bool) else str(value)
    return request(session, "POST", url, headers=headers, form=fields)


def parse_json(text):
    try:
        result = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("响应不是有效 JSON") from None
    if not isinstance(result, dict):
        raise ValueError("响应 JSON 根节点必须是对象")
    return result


def check_business_errors(model, *, allow_pickup_unavailable=False):
    # 抓包中业务状态 200 仍可能携带模块 m 中的 ERROR。
    # 诊断时只输出字段名、少量错误标识和脱敏后的错误文本，不回显原始响应。
    def safe_text(value):
        if not isinstance(value, (str, int, bool)):
            return None
        text = str(value).strip()
        if not text:
            return None
        text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "<邮箱已脱敏>", text)
        text = re.sub(r"(?<!\d)1\d{10}(?!\d)", "<手机号已脱敏>", text)
        text = re.sub(r"(?<!\d)\d{17}[0-9Xx](?!\d)", "<证件号已脱敏>", text)
        text = re.sub(r"(?i)\b[A-Za-z0-9_-]{32,}\b", "<长标识已脱敏>", text)
        return text[:200] + ("…" if len(text) > 200 else "")

    def visit(node, path):
        if isinstance(node, dict):
            if isinstance(node.get("m"), list):
                for message in node["m"]:
                    if isinstance(message, dict) and message.get("level") == "ERROR":
                        # 仅履约轮询允许这一条已确认的库存状态，其余 ERROR 仍立即失败。
                        if (allow_pickup_unavailable and pickup_unavailable(model)
                                and path == "/checkout/fulfillment/pickupTab/pickup/storeLocator"
                                and message.get("text") == PICKUP_UNAVAILABLE):
                            continue
                        details = ["字段=" + ",".join(sorted(str(key) for key in message))]
                        for key in ("code", "errorCode", "type"):
                            value = safe_text(message.get(key))
                            if value is not None:
                                details.append(f"{key}={value}")
                        for key in ("text", "message", "description", "title"):
                            value = safe_text(message.get(key))
                            if value is not None:
                                details.append(f"{key}={value}")
                                break
                        raise ValueError(f"业务字段校验失败：{path or '根节点'}；" + "；".join(details))
            for key, value in node.items():
                visit(value, f"{path}/{key}")
        elif isinstance(node, list):
            for value in node:
                visit(value, path)
    visit(model, "")


def read_model(response, *, allow_pickup_unavailable=False):
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if content_type == "application/json":
        payload = parse_json(response.text)
        status = require(payload, "head", "status")
        if type(status) not in (str, int) or status not in (200, "200"):
            raise ValueError("JSON 响应不是成功模型；需单独处理跳转或错误")
        model = require(payload, "body")
    elif content_type == "text/html":
        soup = BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")
        scripts = soup.select('script#init_data[type="application/json"]')
        if len(scripts) != 1:
            raise ValueError("页面缺少唯一的 init_data 模型，可能未进入预期页面")
        model = parse_json(scripts[0].get_text())
    else:
        raise ValueError("不支持的响应 Content-Type")
    if not isinstance(model, dict):
        raise ValueError("页面模型必须是对象")
    check_business_errors(model, allow_pickup_unavailable=allow_pickup_unavailable)
    return model


def select_product(html, config):
    # productSelectionData 是脚本中的 JSON 对象，不执行页面 JavaScript。
    soup = BeautifulSoup(html, "html.parser")
    marker = "productSelectionData:"
    scripts = [s.get_text() for s in soup.find_all("script") if marker in s.get_text()]
    if len(scripts) != 1 or scripts[0].count(marker) != 1:
        raise ValueError("没有找到唯一的 productSelectionData")
    source = scripts[0].split(marker, 1)[1].lstrip()
    try:
        selection, _ = json.JSONDecoder().raw_decode(source)
    except ValueError:
        raise ValueError("商品选配数据不是有效 JSON") from None
    products = require(selection, "products")
    if not isinstance(products, list):
        raise ValueError("商品列表格式错误")
    matches = [p for p in products if (
        require(p, "familyType") == config["机型"]
        and require(p, "dimensionColor") == config["颜色"]
        and require(p, "dimensionCapacity") == config["容量"]
    )]
    if len(matches) != 1:
        raise ValueError("指定机型、颜色和容量未唯一匹配到商品")
    require(matches[0], "partNumber")
    return matches[0]


def read_add_form(model, sku):
    summary = require(model, "response", "summarySection", "summary")
    if require(summary, "isBuyable") is not True or require(summary, "disabled") is not False:
        raise ValueError("当前商品不可购买")
    soup = BeautifulSoup(require(summary, "buyNowButton"), "html.parser")
    forms = soup.find_all("form")
    if len(forms) != 1:
        raise ValueError("购买摘要没有唯一表单")
    fields = {}
    for field in forms[0].select('input[type="hidden"][name]:not([disabled])'):
        name = field["name"]
        if name in fields or "value" not in field.attrs:
            raise ValueError("加购隐藏字段重复或缺少值")
        fields[name] = field["value"]
    if require(fields, "product") != sku:
        raise ValueError("加购摘要与选配 SKU 不一致")
    require(fields, "purchaseOption")
    require(fields, "step")
    # 隐藏字段来自当次摘要；按钮值与令牌由 add_to_bag 补充。
    return fields


def fetch_summary(session, page, product):
    # 前端 step1evolution.js 的 fetchSummary 使用 GET，并追加 product/purchaseOption。
    # 地址从当次页面读取，不固定商品系列的 node 参数。
    urls = set(re.findall(r"url:\s*'(/shop/updateSummary\?[^']+)'", page.text))
    if len(urls) != 1:
        raise ValueError("页面没有唯一的 updateSummary 地址")
    url = apple_url(page.url, urls.pop())
    url += "&" + urlencode({
        "product": require(product, "partNumber"),
        "purchaseOption": "fullPrice",  # 本流程为全额购买，结账时选择支付宝。
        "igt": "true",  # 已捕获的“不折抵”分支。
        "acpart": "none",  # 已捕获的“不加 AppleCare+”分支。
    })
    response = request(session, "GET", url, headers={"Referer": page.url})
    model = read_model(response)
    form = read_add_form(model, require(product, "partNumber"))
    return model, form


def atb_tokens(session, url):
    """读取实际适用于加购 URL 的 Cookie，不按名称任取一个令牌。"""
    header = session.prepare_request(requests.Request("GET", url)).headers.get("Cookie", "")
    return [entry.strip().split("=", 1)[1] for entry in header.split(";")
            if entry.strip().startswith("as_atb=")]


def add_to_bag(session, page, form):
    # 浏览器实测：从当前商品页按表单 GET 提交，不使用附件加购接口。
    # 浏览器商品页已请求 beacon；使用该会话当前令牌，不重复初始化。
    tokens = atb_tokens(session, page.url)
    if len(tokens) != 1:
        raise ValueError(f"加购前适用的 as_atb Cookie 数量为 {len(tokens)}，要求恰好 1 个；未加购")
    if not tokens[0].split("|")[-1]:
        raise ValueError("加购前 as_atb 令牌尾段为空；未加购")
    fields = dict(form)
    fields.update({"atbtoken": tokens[0].split("|")[-1], "igt": "true", "add-to-cart": "add-to-cart"})
    parsed = urlsplit(page.url)
    # 保留当前页面查询参数，但由当次表单覆盖同名购买参数。
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(fields)
    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))
    response = request(session, "GET", url, headers={"Referer": page.url})
    response = follow_navigation(session, response)
    # 新成功抓包进入 attach 配件页后，还需按页面表单“查看购物袋”。
    response = continue_from_attach(session, response, require(form, "product"))
    # 配件页跳转已返回完整购物袋，调用方继续核对 SKU 和数量。
    return response


def continue_from_attach(session, page, sku):
    configs = []
    for match in re.finditer(r"config:\s*(\{)", page.text):
        try:
            config, _ = json.JSONDecoder().raw_decode(page.text[match.start(1):])
        except ValueError:
            continue  # 页面含其他 JS 配置；只识别完整 JSON 的购买表单。
        if isinstance(config, dict) and "buyFlowForm" in config:
            configs.append(config)
    if len(configs) != 1:
        marker_count = len(re.findall(r"config:\s*\{", page.text))
        raise ValueError(
            "加购响应没有唯一的配件页购买表单："
            f"HTTP={page.status_code}，路径={urlsplit(page.url).path}，"
            f"配置标记数={marker_count}，"
            f"buyFlowForm出现次数={page.text.count('buyFlowForm')}，"
            f"可解析购买表单数={len(configs)}；不能确认下一步"
        )
    config = configs[0]
    if require(config, "step") != "attach" or require(config, "part") != sku:
        raise ValueError("配件页阶段或商品与选配不一致")
    form = require(config, "buyFlowForm")
    if require(form, "method").lower() != "get":
        raise ValueError("配件页表单方法发生变化")
    fields = {}
    for item in require(form, "hiddenFields", "items"):
        value = require(item, "value")
        name = require(value, "attrName")
        if name in fields:
            raise ValueError("配件页隐藏字段重复")
        fields[name] = require(value, "attrValue")
    button = require(config, "addToCartButton")
    if require(button, "disabled") is not False:
        raise ValueError("查看购物袋按钮不可用")
    fields[require(button, "name")] = require(button, "value")
    target = apple_url(page.url, require(form, "action"))
    target += ("&" if "?" in target else "?") + urlencode(fields)
    return follow_navigation(session, request(session, "GET", target, headers={"Referer": page.url}))


def checkout_bag(session, page, model, item_key):
    cart = require(model, "shoppingCart")
    row = require(cart, "items", item_key)
    quantity = require(row, "itemQuantity", "d", "quantity")
    prefix = f"shoppingCart.items.{item_key}"
    address = require(row, "delivery", "lineDeliveryOptions", "address", "provinceCityDistrictTabs", "d")
    fields = {
        "shoppingCart.recommendations.recommendedItem.part": require(cart, "recommendations", "recommendedItem", "d", "part"),
        f"{prefix}.itemQuantity.quantity": quantity,
        "shoppingCart.locationConsent.locationConsent": require(cart, "locationConsent", "d", "locationConsent"),
        "shoppingCart.summary.promoCode.promoCode": require(cart, "summary", "promoCode", "d", "promoCode"),
        "shoppingCart.actions.fcscounter": require(cart, "actions", "d", "fcscounter"),
        "shoppingCart.actions.fcsdata": require(cart, "actions", "d", "fcsdata"),
    }
    for key in ("city", "state", "provinceCityDistrict", "countryCode", "district"):
        fields[f"{prefix}.delivery.lineDeliveryOptions.address.provinceCityDistrictTabs.{key}"] = require(address, key)
    response = post_action(session, page.url, model, ("shoppingCart", "actions"), "checkout", fields)
    return follow_navigation(session, response)


def check_bag(model, sku, quantity):
    items = require(model, "shoppingCart", "items")
    rows = [(key, value) for key, value in items.items() if key.startswith("item-")]
    if len(rows) != 1:
        raise ValueError("购物袋不是指定的单一商品，请核对已有商品")
    key, row = rows[0]
    if require(row, "d", "sku") != sku:
        raise ValueError("购物袋 SKU 与选配不一致")
    actual = require(row, "itemQuantity", "d", "quantity")
    if type(actual) is not int or actual != quantity:
        raise ValueError("购物袋数量与配置不一致；数量更新契约尚未确认")
    require(model, "shoppingCart", "summary", "d", "total")
    return key


def model_headers(model):
    source = require(model, "meta", "h")
    headers = {}
    for name in ("x-aos-model-page", "modelVersion", "syntax", "x-aos-stk"):
        value = require(source, name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"模型请求头无效：{name}")
        headers[name] = value
    # 登录态结账的 Billing/Review 模型会额外下发 x-as-actk；访客态模型没有该头。
    action_key = source.get("x-as-actk")
    if action_key is not None:
        if not isinstance(action_key, str) or not action_key:
            raise ValueError("模型请求头无效：x-as-actk")
        headers["x-as-actk"] = action_key
    return headers


def read_order(model):
    data = require(model, "thankYouInterstitial", "d")
    number = require(data, "orderNumber")
    if not isinstance(number, str) or not number.strip():
        raise ValueError("结果页没有有效订单号")
    order_info = {
        "订单号": number,
        "订单链接": apple_url("", require(data, "orderStatusUrl")),
    }
    if "externalUrl" in data and isinstance(data["externalUrl"], str) and data["externalUrl"].strip():
        order_info["支付链接"] = data["externalUrl"]
    return order_info


def extract_checkout_errors(model, html_text=""):
    messages = []
    def visit(node):
        if isinstance(node, dict):
            if isinstance(node.get("m"), list):
                for m in node["m"]:
                    if isinstance(m, dict) and m.get("level") in ("ERROR", "FATAL"):
                        text = m.get("text") or m.get("message")
                        if text and text not in messages:
                            messages.append(str(text))
            for key, val in node.items():
                if key in ("messages", "globalMessages", "errors") and isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            text = item.get("message") or item.get("text") or item.get("description")
                            if text and text not in messages:
                                messages.append(str(text))
                        elif isinstance(item, str) and item and item not in messages:
                            messages.append(item)
                visit(val)
        elif isinstance(node, list):
            for x in node:
                visit(x)

    if isinstance(model, dict):
        visit(model)
    if not messages and html_text:
        soup = BeautifulSoup(html_text, "html.parser")
        selectors = [
            ".as-banner-message", ".as-notification-content", ".as-notification-message",
            "[role='alert']", ".form-message-error", ".as-errormessage"
        ]
        for sel in selectors:
            for el in soup.select(sel):
                text = el.get_text(strip=True)
                if text and text not in messages:
                    messages.append(text)
    return messages


def query_order(session, status_url, max_attempts=30, interval=1.0):
    """使用当前结账会话查询结果；支持处理中状态轮询，不负责创建订单或恢复历史 Cookie。"""
    current_url = status_url
    for attempt in range(1, max_attempts + 1):
        page = request(session, "GET", current_url)
        model = read_model(page)
        action_url = apple_url(page.url, require(model, "spinner", "a", "checkStatus", "url"))
        headers = model_headers(model)
        parsed = urlsplit(page.url)
        headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "Fetch",
            "Origin": f"{parsed.scheme}://{parsed.netloc}",
            "Referer": page.url,
        })
        response = request(session, "POST", action_url, headers=headers)
        payload = parse_json(response.text)
        check_business_errors(payload)
        status = require(payload, "head", "status")
        if type(status) not in (str, int) or status not in (302, "302"):
            raise ValueError(f"状态检查未返回已确认的结果页跳转（status={status}）；停止，不重复提交订单")
        result_url = apple_url(response.url, require(payload, "head", "data", "url"))
        result_path = urlsplit(result_url).path
        if result_path == "/shop/checkout/interstitial":
            return read_order(read_model(request(session, "GET", result_url)))
        if result_path == "/shop/checkout/status":
            if attempt < max_attempts:
                time.sleep(interval)
                current_url = result_url
                continue
            raise RuntimeError(f"订单处理状态查询超时（已尝试 {max_attempts} 次仍处于处理中），请核对手机短信或邮箱确认")
        err_reasons = []
        try:
            err_page = request(session, "GET", result_url)
            err_model = None
            try:
                err_model = read_model(err_page)
            except Exception:
                pass
            err_reasons = extract_checkout_errors(err_model, err_page.text)
        except Exception:
            pass
        if err_reasons:
            raise ValueError(f"订单被 Apple 拒绝并跳转至 {result_path}：{'；'.join(err_reasons)}")
        if result_path == "/shop/checkout":
            raise ValueError(f"订单被 Apple 拒绝并退回结账页（{result_path}），未取得订单结果（常见原因：所选门店该机型无现货库存、当前无可用自提时段或联系人与证件不符）")
        raise ValueError(f"状态检查跳转到未预期页面（{result_path}），尚未取得订单结果")
    raise RuntimeError("订单处理状态查询超时，尚未取得订单结果")


def main():
    if not SESSION_CONFIGS:
        raise ValueError("至少配置一组会话")
    for config in SESSION_CONFIGS:
        validate_config(config)
        if config["数量"] != 1:
            raise ValueError("当前仅确认单次加购一件，数量必须为 1")
    try:
        with sync_playwright() as playwright:
            for index, config in enumerate(SESSION_CONFIGS, 1):
                print(f"会话 {index}/{len(SESSION_CONFIGS)}：普通 Chrome 初始化，Python 直连。")
                with browser_session(playwright, config["商品页面"]) as session:
                    page = request(session, "GET", config["商品页面"])
                    product = select_product(page.content, config)
                    before = read_model(follow_navigation(session, request(
                        session, "GET", apple_url(page.url, "/shop/bag"))))
                    if any(key.startswith("item-") for key in require(before, "shoppingCart", "items")):
                        raise ValueError("独立会话购物袋不为空，停止加购")
                    _, add_form = fetch_summary(session, page, product)
                    print("选配与购买摘要已通过，由 Python requests 加购一次。")
                    bag = read_model(add_to_bag(session, page, add_form))
                    check_bag(bag, require(product, "partNumber"), config["数量"])
                    print(f"会话 {index}：Python 加购成功，SKU={require(product, 'partNumber')}，数量={config['数量']}；未结账。")
    except BrowserError as exc:
        raise RuntimeError(f"浏览器操作失败：{type(exc).__name__}；已停止，未自动重试") from None


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, NotImplementedError) as exc:
        raise SystemExit(str(exc)) from None
