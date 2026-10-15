"""由共用 fetch 在跨进程锁内轮转；不再独立定时运行。

依赖 PyYAML。控制地址、证书和凭据只从本机毛熊 VPN 配置读取，不复制凭据。
仅影响经过 PROXY_GROUP 的流量；不同节点不保证拥有不同公网 IP。
"""

import json
import os
import re
import ssl
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

import yaml
import requests


INTERVAL_SECONDS = 1 * 60
PROXY_GROUP = "🌍 国外网站"
# 空字符串表示不限制名称后缀；仍排除港澳台节点、策略组、直连和拒绝项。
NODE_NAME_SUFFIX = ""
EXCLUDED_REGION_NAME = re.compile(
    r"香港|台湾|臺灣|台灣|澳门|澳門|🇭🇰|🇹🇼|🇲🇴|"
    r"hong[\s_-]*kong|tai[\s_-]*wan|maca[uo]|"
    r"(?<![a-z])(?:hk|tw|mo)(?![a-z])", re.IGNORECASE)
PROBE_TIMEOUT_MS = 2000
CHECK_URL = "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyc4ch/a"
PROBE_URL = CHECK_URL
MIHOMO_CONFIG = (
    Path(os.environ["APPDATA"])
    / "maoxiong-vpn" / "mihomo" / "config.yaml"
)


class Controller:
    def __init__(self):
        config = yaml.safe_load(MIHOMO_CONFIG.read_text(encoding="utf-8"))
        endpoint = urlsplit("https://" + config["external-controller-tls"])
        if (endpoint.hostname != "127.0.0.1" or not endpoint.port
                or endpoint.username or endpoint.password or endpoint.path
                or endpoint.query or endpoint.fragment):
            raise ValueError("毛熊控制接口须监听 127.0.0.1:端口")
        # 本机控制证书的 SAN 是 localhost；保持证书链和主机名验证。
        self.url = f"https://localhost:{endpoint.port}"
        self.secret = config["secret"]
        context = ssl.create_default_context(cafile=config["tls"]["certificate"])
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.url + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.secret,
                "Content-Type": "application/json",
            },
        )
        with self.opener.open(request, timeout=10) as response:
            body = response.read()
        return json.loads(body) if body else None


def read_group(controller):
    proxies = controller.request("GET", "/proxies")["proxies"]
    group = proxies[PROXY_GROUP]
    if group["type"] != "Selector":
        raise ValueError("指定代理组必须是手动选择组 Selector")
    nodes = [
        name for name in group["all"]
        if name.endswith(NODE_NAME_SUFFIX) and "all" not in proxies[name]
        and not EXCLUDED_REGION_NAME.search(name)
        and proxies[name]["type"].lower() not in {"direct", "reject", "rejectdrop"}
    ]
    if len(nodes) < 2:
        raise ValueError("代理组至少需要两个匹配的实际节点")
    return group["now"], nodes


def check_product_page(proxy_url):
    """独立无账号 Cookie 会话；541 才尝试下一节点，其他失败明确停止。"""
    with requests.Session() as probe:
        probe.trust_env = False
        probe.proxies = {"http": proxy_url, "https": proxy_url}
        try:
            with probe.get(CHECK_URL, timeout=30, allow_redirects=False) as response:
                if response.status_code == 541:
                    return False
                if response.status_code != 200:
                    raise RuntimeError(f"节点商品页验证失败：HTTP {response.status_code}")
                if ("text/html" not in response.headers.get("Content-Type", "").lower()
                        or "productSelectionData:" not in response.text
                        or "MJYC4" not in response.text):
                    raise RuntimeError("节点返回 200，但不是预期商品页，停止轮转")
        except requests.RequestException:
            raise RuntimeError("节点商品页验证网络失败，停止轮转") from None
    return True


def rotate_once(controller, proxy_url):
    current, nodes = read_group(controller)
    index = (nodes.index(current) + 1) % len(nodes) if current in nodes else 0
    for offset in range(len(nodes)):
        target = nodes[(index + offset) % len(nodes)]
        if target == current:
            continue
        print(f"检测候选节点：{target}（超时 {PROBE_TIMEOUT_MS} ms）", flush=True)
        path = "/proxies/" + quote(target, safe="") + "/delay?" + urlencode(
            {"url": PROBE_URL, "timeout": PROBE_TIMEOUT_MS}
        )
        try:
            result = controller.request("GET", path)
        except HTTPError as error:
            if error.code not in {503, 504}:
                raise RuntimeError(f"节点检测控制接口异常：HTTP {error.code}，停止轮转") from error
            error.close()
            print(f"候选节点检测失败：{target}；HTTP {error.code}，检查下一个。", flush=True)
            continue
        delay = result["delay"]
        if type(delay) is not int or delay < 0:
            raise ValueError("节点检测返回非法 delay，已停止")
        print(f"候选节点检测通过：{target}；{delay} ms", flush=True)
        connections = controller.request("GET", "/connections")["connections"]
        old_ids = [c["id"] for c in connections if PROXY_GROUP in c["chains"]]
        group_path = "/proxies/" + quote(PROXY_GROUP, safe="")
        controller.request("PUT", group_path, {"name": target})
        if controller.request("GET", group_path)["now"] != target:
            raise RuntimeError("切换后代理组状态不匹配，已停止")
        for connection_id in old_ids:
            controller.request("DELETE", "/connections/" + quote(connection_id, safe=""))
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} 已切换到 {target}；"
              f"已关闭 {len(old_ids)} 条旧连接；开始商品页验证", flush=True)
        if check_product_page(proxy_url):
            print(f"节点商品页验证通过：{target}；轮转完成", flush=True)
            return
        print(f"节点商品页返回 HTTP 541：{target}；检查下一节点", flush=True)
    raise RuntimeError("所有候选节点检测失败或返回 541；停止轮转及后续请求")


if __name__ == "__main__":
    raise SystemExit("请运行 v2/session.py 或 v2/main.py；轮转已由共用 fetch 统一管理。")
