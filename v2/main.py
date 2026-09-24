"""按 ACCOUNTS 串行跑完每个账号：接续已准备的结账，不执行付款。

运行前先启动 v2/session.py 并完成各账号登录；本脚本通过各账号的调试端口复用常驻会话。
一个账号失败不影响后续账号，但会在结尾汇总并以非零状态退出。
"""
import json
import time
from datetime import datetime
from pathlib import Path

from config import ACCOUNTS, RUN
from order import base, checkout
from session import live_endpoint, ready_session

REQUIRED_KEYS = ("账号", "资料目录", "调试端口", "商品页面", "机型", "颜色", "容量", "数量", "自提门店",
                 "搜索地区", "省", "市", "区", "姓", "名", "手机号", "邮箱", "证件后四位",
                 "发票类型", "支付方式")


def account_config(account):
    """账号配置 + 运行级开关，形成结账流程实际使用的 config。"""
    return {**account, "允许访客结账": RUN["允许访客结账"], "使用抓包代理": RUN["使用抓包代理"]}


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
    for key in ("允许访客结账", "使用抓包代理"):
        if not isinstance(RUN[key], bool):
            raise ValueError(f"RUN[{key}] 必须是 True 或 False")
    if not isinstance(RUN["账号间隔秒"], (int, float)) or RUN["账号间隔秒"] < 0:
        raise ValueError("RUN[账号间隔秒] 必须是非负数")


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


def require_sessions(accounts):
    """预检：所有账号都必须有活着的常驻会话，避免跑到一半才发现要登录。"""
    missing = [account["账号"] for account in accounts if live_endpoint(account) is None]
    if missing:
        raise RuntimeError(
            "以下账号没有检测到常驻会话：" + "、".join(missing)
            + "；请先运行 .venv/Scripts/python.exe v2/session.py 并完成登录后重试")

def run_account(config):
    """下单前验证会话，明确过期时只自动准备一次。"""
    with ready_session(config) as (session, browser, entry):
        product_page = base.follow_navigation(session, base.request(session, "GET", config["商品页面"]))
        product = base.select_product(product_page.content, config)
        bag = base.follow_navigation(session, base.request(session, "GET", "https://www.apple.com.cn/shop/bag"))
        base.check_bag(base.read_model(bag), product["partNumber"], config["数量"])
        # 商品页和购物袋只做一致性校验；结账动作使用交接时 requests 取得的最新 Fulfillment 模型。
        return checkout(session, browser, bag, config, product["partNumber"], prepared=entry)


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
    check_accounts(ACCOUNTS)
    require_sessions(ACCOUNTS)
    print("预检通过：" + str(len(ACCOUNTS)) + " 个账号的常驻浏览器可连接（逐账号验证结账会话）（"
          + "、".join(account["账号"] for account in ACCOUNTS) + "）；开始串行下单。", flush=True)
    results, failures = [], []
    for index, account in enumerate(ACCOUNTS):
        if index:
            time.sleep(RUN["账号间隔秒"])
        name = account["账号"]
        config = account_config(account)
        print(f"=== [{name}] 开始：{config['商品页面']} ===", flush=True)
        record = {"时间": datetime.now().astimezone().isoformat(timespec="seconds"), "账号": name,
                  "商品页面": config["商品页面"], "门店": config["自提门店"], "数量": config["数量"]}
        try:
            result = run_account(config)
        except Exception as error:  # 单个账号失败不影响后续账号；失败原因单独记录
            message = describe_failure(error)
            print(f"[{name}] 失败：{message}", flush=True)
            failures.append((name, message))
            append_result(RUN["结果文件"], {**record, "状态": "失败", "失败原因": message})
            continue
        print(f"[{name}] 成功：订单号 {result['订单号']}"
              + (f"，支付链接 {result['支付链接']}" if "支付链接" in result else ""), flush=True)
        results.append((name, result))
        append_result(RUN["结果文件"], {**record, "状态": "成功", "SKU": result.get("SKU"),
                                        "金额": result.get("金额"), "订单号": result["订单号"],
                                        "支付链接": result.get("支付链接", "")})
    print(f"=== 结束：成功 {len(results)} 个，失败 {len(failures)} 个；结果已追加到 {RUN['结果文件']} ===",
          flush=True)
    for name, message in failures:
        print(f"  失败账号 {name}：{message}", flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} 个账号失败，详见上方汇总")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        # 本地配置、预检与流程错误均已使用不包含凭据的错误信息。
        raise SystemExit("流程停止：" + str(error) + "；未自动重试。") from None
    except Exception as error:
        # 原始网络/浏览器异常可能含 Cookie、URL 令牌或个人信息，不打印详情。
        raise SystemExit("流程停止：" + type(error).__name__ + "；未自动重试。") from None
