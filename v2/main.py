"""按 ACCOUNTS 并行执行每个账号：接续已准备的结账，不执行付款。

运行前先启动 v2/session.py 并完成各账号登录；本脚本通过各账号的调试端口复用常驻会话。
各账号缺货等待及失败互不阻塞；成功一单即结束对应任务。
"""
import json
import math
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from threading import Event
from datetime import datetime
from pathlib import Path

from config.config import RUN, selected_accounts
from order import base, checkout, StoreSelection541, log_bag, log_session
from session import ready_session, checkout_in_browser
from apple_store.request_log import account_name
from apple_store.network import configure_rotation
from rotate_clash import Controller, INTERVAL_SECONDS, read_group, rotate_once

REQUIRED_KEYS = ("账号", "资料目录", "调试端口", "商品页面", "机型", "颜色", "容量", "数量", "自提门店",
                 "搜索地区", "省", "市", "区", "姓", "名", "手机号", "邮箱", "证件后四位",
                 "发票类型", "支付方式")


def account_config(account):
    """账号配置 + 运行级开关，形成结账流程实际使用的 config。"""
    return {**account, "允许访客结账": RUN["允许访客结账"], "使用抓包代理": RUN["使用抓包代理"],
            "代理地址": RUN["代理地址"],
            "缺货轮询间隔秒": RUN["缺货轮询间隔秒"],
            "选店网络重试次数": RUN["选店网络重试次数"],
            "选店网络重试间隔秒": RUN["选店网络重试间隔秒"]}


def check_account(config):
    """账号级校验：缺字段、非法取值都在联网前停。"""
    name = config.get("账号", "<未命名>")
    for key in REQUIRED_KEYS:
        value = config.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"[{name}] 缺少配置：{key}")
    if config["数量"] != 1:
        raise ValueError(f"[{name}] 本脚本仅支持单件商品")
    if config["支付方式"] != "ALIPAY" or config["发票类型"] != "e_personal_fdf":
        raise ValueError(f"[{name}] 本脚本仅支持支付宝与个人电子发票")
    if len(config["证件后四位"]) != 4:
        raise ValueError(f"[{name}] 证件后四位必须为四个字符")
    if not isinstance(config["调试端口"], int) or not 1 <= config["调试端口"] <= 65535:
        raise ValueError(f"[{name}] 调试端口非法：{config['调试端口']}")


def check_runtime():
    """运行级开关校验。"""
    base.validate_proxy(RUN["代理地址"], RUN["使用抓包代理"])
    for key in ("允许访客结账", "使用抓包代理"):
        if not isinstance(RUN[key], bool):
            raise ValueError(f"RUN[{key}] 必须是 True 或 False")
    interval = RUN["缺货轮询间隔秒"]
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
        raise ValueError("RUN[缺货轮询间隔秒] 必须是有限正数")
    if type(RUN["结账恢复次数"]) is not int or RUN["结账恢复次数"] < 0:
        raise ValueError("RUN[结账恢复次数] 必须是非负整数")
    if type(RUN["选店网络重试次数"]) is not int or RUN["选店网络重试次数"] < 0:
        raise ValueError("RUN[选店网络重试次数] 必须是非负整数")
    interval = RUN["选店网络重试间隔秒"]
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
        raise ValueError("RUN[选店网络重试间隔秒] 必须是有限正数")


def check_accounts(accounts):
    """注册表校验：账号名、资料目录、调试端口都必须唯一且合法。"""
    if not accounts:
        raise ValueError("ACCOUNTS 为空，请至少配置一个账号")
    seen_names, seen_dirs, seen_ports = set(), set(), set()
    for account in accounts:
        check_account(account)
        name = account["账号"]
        directory = str(Path(account["资料目录"]).resolve())
        port = account["调试端口"]
        if name in seen_names:
            raise ValueError(f"账号名重复：{name}")
        if directory in seen_dirs:
            raise ValueError(f"[{name}] 资料目录与其他账号重复：{directory}")
        if port in seen_ports:
            raise ValueError(f"[{name}] 调试端口与其他账号重复：{port}")
        seen_names.add(name)
        seen_dirs.add(directory)
        seen_ports.add(port)


def run_account(config, stop_event):
    """一个工作线程拥有一个账号的全部浏览器及 HTTP 对象。"""
    token = account_name.set(config["账号"])
    try:
        recovery_limit = RUN["结账恢复次数"]
        for attempt in range(recovery_limit + 1):
            if stop_event.is_set():
                raise RuntimeError("用户已停止执行；未开始新的结账")
            with ready_session(config) as (session, browser, entry):
                product_page = base.follow_navigation(session, base.request(session, "GET", config["商品页面"]))
                product = base.select_product(product_page.content, config)
                bag = base.follow_navigation(session, base.request(session, "GET", "https://www.apple.com.cn/shop/bag"))
                log_bag(base.read_model(bag), product["partNumber"], config["数量"], "main入口requests购物袋")
                base.check_bag(base.read_model(bag), product["partNumber"], config["数量"])
                try:
                    return checkout(session, browser, bag, config, product["partNumber"],
                                    prepared=entry, stop_event=stop_event)
                except (base.CheckoutExpired, StoreSelection541) as error:
                    # 仅履约阶段的过期或 select 本身的 541；创单及结果查询绝不重跑。
                    if attempt >= recovery_limit:
                        raise RuntimeError(f"库存等待期间结账过期或选店返回 541；已恢复 {attempt}/{recovery_limit} 次，停止") from None
                    if stop_event.is_set():
                        raise RuntimeError("用户已停止执行；未重新进入结账") from None
                    if isinstance(error, StoreSelection541):
                        log_session(session, browser, "541恢复前：requests待写回浏览器")
                        print(f"[{config['账号']}] 选店 HTTP 541；从官网购物袋重新进入结账（恢复 {attempt + 1}/{recovery_limit} 次）。", flush=True)
                        total = base.require(base.read_model(bag), "shoppingCart", "summary", "d", "total")
                        checkout_in_browser(session, browser, product["partNumber"], config["数量"], total)
                    else:
                        print(f"[{config['账号']}] 库存等待期间结账过期；重新验证并恢复（恢复 {attempt + 1}/{recovery_limit} 次）。", flush=True)
    finally:
        account_name.reset(token)


def describe_failure(error):
    """把异常转成不含请求数据的说明：本地校验错误直接给原文，其余只给类型。"""
    if isinstance(error, (ValueError, RuntimeError)):
        return str(error)
    if isinstance(error, AttributeError):
        return f"AttributeError：{error}"
    if isinstance(error, base.BrowserError):
        if type(error).__name__ == "TargetClosedError":
            return ("常驻浏览器已断开（session.py 被 Ctrl+C、终端被关，或 Chrome 窗口被关闭）；"
                    "请重新运行 .venv/Scripts/python.exe v2/session.py 并确认窗口与服务保持打开")
        return f"浏览器操作失败：{type(error).__name__}"
    return type(error).__name__


def append_result(path, record):
    """结果一行一条 JSON 追加落盘。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    check_runtime()
    accounts = selected_accounts()
    check_accounts(accounts)
    controller = Controller()
    read_group(controller)
    configure_rotation(lambda: rotate_once(controller), INTERVAL_SECONDS)
    print(f"HTTP 请求共用一把锁；每 {INTERVAL_SECONDS} 秒在下一次请求前轮转。请勿另行运行 rotate_clash.py。", flush=True)
    print("本次下单账号：" + "、".join(account["账号"] for account in accounts), flush=True)
    print(f"启动 {len(accounts)} 个账号并行执行；各账号成功一单即停止，缺货独立轮询。", flush=True)
    results, failures = [], []
    stop_event = Event()
    # 每个账号仅提交一次任务；完成后不重新入队。结果统一由主线程写入。
    with ThreadPoolExecutor(max_workers=len(accounts)) as pool:
        pending = {}
        try:
            for account in accounts:
                config = account_config(account)
                print(f"=== [{config['账号']}] 开始：{config['商品页面']} ===", flush=True)
                record = {"时间": datetime.now().astimezone().isoformat(timespec="seconds"), "账号": config["账号"],
                          "商品页面": config["商品页面"], "门店": config["自提门店"], "数量": config["数量"]}
                pending[pool.submit(run_account, config, stop_event)] = record
            while pending:
                try:
                    done, _ = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                except KeyboardInterrupt:
                    stop_event.set()
                    print("收到停止指令：结束缺货等待，不再开始新动作；已提交订单仍查询并记录结果。", flush=True)
                    continue
                for future in done:
                    record = pending.pop(future)
                    name = record["账号"]
                    try:
                        result = future.result()
                    except Exception as error:
                        message = describe_failure(error)
                        print(f"[{name}] 停止：{message}", flush=True)
                        failures.append((name, message))
                        append_result(RUN["结果文件"], {**record, "状态": "失败", "失败原因": message})
                        continue
                    print(f"[{name}] 成功：订单号 {result['订单号']}；本账号停止，支付链接见本地结果文件。", flush=True)
                    results.append((name, result))
                    append_result(RUN["结果文件"], {**record, "状态": "成功", "SKU": result.get("SKU"),
                                                  "金额": result.get("金额"), "订单号": result["订单号"],
                                                  "支付链接": result.get("支付链接", "")})
        finally:
            stop_event.set()
    print(f"=== 结束：成功 {len(results)} 个，停止 {len(failures)} 个；结果已追加到 {RUN['结果文件']} ===", flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} 个账号停止，详见上方日志")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        # 本地配置、预检与流程错误均已使用不包含凭据的错误信息。
        raise SystemExit("流程停止：" + str(error) + "；未自动重试创单。") from None
    except Exception as error:
        # 原始网络/浏览器异常可能含 Cookie、URL 令牌或个人信息，不打印详情。
        raise SystemExit("流程停止：" + type(error).__name__ + "；未自动重试创单。") from None
