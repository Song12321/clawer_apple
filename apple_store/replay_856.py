"""重放 Reqable 中复制的 856 cURL；只加购一次，不继续结账。"""

import json
import shlex
import tkinter
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests


PROXY = "http://127.0.0.1:9000"
CA = Path.home() / "AppData/Roaming/Reqable/certificate/reqable-root.crt"
PRODUCT = "MG6Y4CH/A"


def main():
    # 在 Reqable 对目标记录执行“复制 cURL”；不把 Cookie 和令牌写入文件。
    root = tkinter.Tk()
    root.withdraw()
    try:
        args = shlex.split(root.clipboard_get())
    finally:
        root.destroy()
    if not args or args[0] != "curl":
        raise ValueError("剪贴板必须为 Reqable 导出的原始 cURL")
    urls = [value for value in args if value.startswith("https://")]
    if len(urls) != 1:
        raise ValueError("cURL 必须包含唯一 HTTPS 地址")
    url = urls[0]
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    if (parsed.hostname != "www.apple.com.cn"
            or parsed.path != "/shop/buy-iphone/iphone-17/" + PRODUCT.lower()
            or query.get("product") != [PRODUCT]
            or query.get("add-to-cart") != ["add-to-cart"]):
        raise ValueError("剪贴板不是指定商品的加购请求")
    headers = {}
    for index, value in enumerate(args):
        if value == "-H":
            name, content = args[index + 1].split(":", 1)
            headers[name] = content.strip()
    if not any(name.lower() == "cookie" for name in headers):
        raise ValueError("重放请求缺少原始 Cookie")

    with requests.Session() as session:
        session.trust_env = False
        session.proxies = {"http": PROXY, "https": PROXY}
        session.verify = str(CA)
        # 保留原始查询和请求头；不重建会话、不重试、不跟随跳转。
        try:
            with session.get(url, headers=headers, timeout=30,
                             allow_redirects=False, stream=True) as response:
                target = urlsplit(response.headers.get("Location", ""))
                fields = parse_qs(target.query)
                print(json.dumps({
                    "status": response.status_code,
                    "location_path": target.path,
                    "product": fields.get("product"),
                    "step": fields.get("step"),
                }, ensure_ascii=False))
                if (response.status_code != 303
                        or target.path != "/shop/buy-iphone/iphone-17"
                        or fields.get("product") != [PRODUCT.lower()]
                        or fields.get("step") != ["attach"]):
                    raise RuntimeError("未返回已确认的加购跳转，停止")
        except requests.RequestException as exc:
            # 原始异常可能含带凭据的 URL，只输出异常类型。
            raise RuntimeError(f"重放失败：{type(exc).__name__}；未重试") from None


if __name__ == "__main__":
    main()
