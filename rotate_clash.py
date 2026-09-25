"""独立运行时每 5 分钟轮转指定组，关闭该组旧连接；Ctrl+C 停止。

v2/main.py 已在请求间隙调用本模块轮转，不得与本脚本独立进程同时运行。

依赖 PyYAML。控制地址和凭据只从本机 Verge 配置读取，不复制凭据。
仅影响经过 PROXY_GROUP 的流量；不同节点不保证拥有不同公网 IP。
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, build_opener

import yaml


INTERVAL_SECONDS = 5 * 60
PROXY_GROUP = "🚀 手动切换"
# 空字符串表示不限制名称后缀；仍排除策略组、直连和拒绝项。
NODE_NAME_SUFFIX = ""
PROBE_URL = "https://secure11.www.apple.com.cn/"
PROBE_TIMEOUT_MS = 2000
VERGE_CONFIG = (
    Path(os.environ["APPDATA"])
    / "io.github.clash-verge-rev.clash-verge-rev"
    / "clash-verge.yaml"
)


class Controller:
    def __init__(self):
        config = yaml.safe_load(VERGE_CONFIG.read_text(encoding="utf-8"))
        self.url = "http://" + config["external-controller"]
        self.secret = config["secret"]
        self.opener = build_opener(ProxyHandler({}))

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
        and proxies[name]["type"].lower() not in {"direct", "reject", "rejectdrop"}
    ]
    if len(nodes) < 2:
        raise ValueError("代理组至少需要两个匹配的实际节点")
    return group["now"], nodes


def rotate_once(controller):
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
            if error.code != 504:
                raise
            error.close()
            print(f"候选节点检测失败：{target}；HTTP 504，检查下一个。", flush=True)
            continue
        delay = result["delay"]
        if type(delay) is not int or delay < 0:
            raise ValueError("节点检测返回非法 delay，已停止")
        print(f"候选节点检测通过：{target}；{delay} ms", flush=True)
        break
    else:
        raise RuntimeError("所有候选节点检测失败，保留当前节点，停止轮转")
    # 在切换前记录旧连接，只断开指定组，避免删除其他应用的连接。
    connections = controller.request("GET", "/connections")["connections"]
    old_ids = [c["id"] for c in connections if PROXY_GROUP in c["chains"]]
    group_path = "/proxies/" + quote(PROXY_GROUP, safe="")
    controller.request("PUT", group_path, {"name": target})
    if controller.request("GET", group_path)["now"] != target:
        raise RuntimeError("切换后代理组状态不匹配，已停止")
    for connection_id in old_ids:
        controller.request("DELETE", "/connections/" + quote(connection_id, safe=""))
    print(
        f"{datetime.now():%Y-%m-%d %H:%M:%S} {current} -> {target}；"
        f"已关闭 {len(old_ids)} 条旧连接", flush=True,
    )


def main():
    if INTERVAL_SECONDS <= 0:
        raise ValueError("切换间隔必须大于零")
    controller = Controller()
    current, nodes = read_group(controller)
    print(
        f"代理组：{PROXY_GROUP}；当前：{current}；候选：{len(nodes)} 个。\n"
        f"每 {INTERVAL_SECONDS} 秒切换，首次切换在一个间隔后；Ctrl+C 停止。",
        flush=True,
    )
    while True:
        time.sleep(INTERVAL_SECONDS)
        rotate_once(controller)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已停止轮转，保留当前节点。")
