"""本地只读 HAR 分析。修改 CONFIG 后运行；不发请求、不导出原始凭据。"""
import base64
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit

CONFIG = {
    "har_path": "D:/lqs/crawler/other/apple/url信息/所有_2026_09_20_09_21_37.har",
    "target_ids": [266, 344, 490, 504, 514, 518, 536, 541, 551, 565],
    # 在 URL、请求正文、响应正文中搜索；只输出命中位置，不输出原文。
    "search_terms": ["contactVerify", "submitVerificationToken"],
    "output_path": str(Path(__file__).with_name("har-evidence.json")),
}
HEADERS = ("x-aos-model-page", "modelversion", "syntax", "x-aos-stk")


class InitData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "init_data":
            if self.parts:
                raise ValueError("多个 init_data，无法唯一定位")
            self.active = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def response_text(entry):
    content = entry["response"]["content"]
    if "text" not in content:
        return None
    text = content["text"]
    encoding = content.get("encoding")
    if encoding == "base64":
        return base64.b64decode(text, validate=True).decode("utf-8")
    if encoding is not None:
        raise ValueError("不支持的 HAR 正文编码")
    return text


def model_from(entry, text):
    if text is None:
        return None
    mime = entry["response"]["content"].get("mimeType", "").split(";")[0]
    if mime == "application/json" or mime.endswith("+json"):
        return json.loads(text)
    if mime == "text/html":
        parser = InitData()
        parser.feed(text)
        return json.loads("".join(parser.parts)) if parser.parts else None
    return None


def endpoint(url):
    # 路径本身也可能包含订单号、邮箱、令牌，仅展示已知商城接口路径。
    parsed = urlsplit(url)
    path = parsed.path
    if not re.fullmatch(r"/shop/(?:checkoutx?(?:/(?:statusX|status|interstitial|review|billing|fulfillment|start))?|signInx?|bagx?)", path):
        path = "<路径已隐藏>"
    return {"host": parsed.hostname, "path": path,
            "query_names": [k for k, _ in parse_qsl(parsed.query, keep_blank_values=True)],
            "actions": {k: v if re.fullmatch(r"[A-Za-z][A-Za-z.-]{0,180}", v) else "<已隐藏>"
                        for k, v in parse_qsl(parsed.query) if k in ("_a", "_m", "_s")}}


def fields(entry):
    request = entry["request"]
    if "postData" not in request:
        return {"state": "empty" if request.get("bodySize") == 0 else "not_exported_or_unknown", "fields": []}
    post = request["postData"]
    if "params" in post:
        pairs = [(p["name"], p.get("value")) for p in post["params"]]
    elif "text" in post and post.get("mimeType", "").split(";")[0] == "application/x-www-form-urlencoded":
        pairs = parse_qsl(post["text"], keep_blank_values=True)
    else:
        return {"state": "unparsed", "fields": []}
    return {"state": "present" if pairs else "empty", "fields": [
        {"name": key, "value": "" if value == "" else "<已隐藏>"} for key, value in pairs]}


def walk(node, path="$", parent=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + "." + key, key, value, parent
            yield from walk(value, path + "." + key, key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]", parent)


def analyze(path, target_ids, terms):
    raw = Path(path).read_bytes()
    entries = json.loads(raw.decode("utf-8-sig"))["log"]["entries"]
    by_id = {}
    for index, entry in enumerate(entries):
        identity = entry.get("_id", f"har-index:{index}")
        if identity in by_id:
            raise ValueError("重复记录 ID；请先按会话拆分 HAR")
        by_id[identity] = (index, entry)
    if any(identity not in by_id for identity in target_ids):
        raise ValueError("目标 ID 不在 HAR 中；无 _id 时使用 har-index:N，不假定它等于界面编号")
    parsed = {}
    hits = []
    for identity, (index, entry) in by_id.items():
        mime = entry["response"]["content"].get("mimeType", "")
        textual = any(t in mime for t in ("json", "text/", "javascript", "xml"))
        text = response_text(entry) if textual or identity in target_ids else None
        parts = {"request.url": entry["request"]["url"],
                 "request.postData": json.dumps(entry["request"].get("postData", {})),
                 "response.content.text": text or ""}
        for term_index, term in enumerate(terms):
            for location, content in parts.items():
                if term in content:
                    hits.append({"id": identity, "term_index": term_index, "location": location})
        if identity in target_ids:
            parsed[identity] = model_from(entry, text)
    records, links = [], []
    for identity in target_ids:
        index, entry = by_id[identity]
        model = parsed[identity]
        headers = {h["name"].lower(): h["value"] for h in entry["request"]["headers"]}
        record = {"id": identity, "har_index": index, "started": entry["startedDateTime"],
                  "duration_ms": entry["time"], "method": entry["request"]["method"],
                  "endpoint": endpoint(entry["request"]["url"]), "http_status": entry["response"]["status"],
                  "body": fields(entry), "model_headers_present": [h for h in HEADERS if h in headers],
                  "response_body_exported": "text" in entry["response"]["content"], "model_facts": []}
        for location, key, value, parent in walk(model):
            if key in ("page", "isVerified", "authRequired", "alipayReview", "selectBillingOption") and isinstance(value, (str, bool)):
                safe = value if isinstance(value, bool) or value in ("", "Billing", "Review", "PickupContact", "Fulfillment", "ALIPAY") else "<已隐藏>"
                record["model_facts"].append({"path": location, "value": safe})
            if key == "url" and isinstance(value, str):
                absolute = urljoin(entry["request"]["url"], value)
                for dest in target_ids:
                    if dest == identity or by_id[dest][1]["request"]["url"] != absolute:
                        continue
                    destination = by_id[dest][1]
                    dest_headers = {h["name"].lower(): h["value"] for h in destination["request"]["headers"]}
                    source_model = model.get("body", model)
                    source_headers = {k.lower(): v for k, v in source_model.get("meta", {}).get("h", {}).items()}
                    links.append({"source": identity, "target": dest, "evidence_path": location,
                                  "kind": "response_url_exact_match_not_causality",
                                  "header_equal": {h: source_headers[h] == dest_headers[h] for h in HEADERS if h in source_headers and h in dest_headers}})
        for header in entry["response"]["headers"]:
            if header["name"].lower() == "location":
                for dest in target_ids:
                    if by_id[dest][1]["request"]["url"] == urljoin(entry["request"]["url"], header["value"]):
                        links.append({"source": identity, "target": dest, "evidence_path": "response.headers.Location", "kind": "http_location_match"})
        records.append(record)
    return {"source_sha256": hashlib.sha256(raw).hexdigest(), "entry_count": len(entries),
            "records": records, "links": links, "search_hits": hits,
            "limits": ["URL 相同或请求头一致不单独证明因果关系", "仅分析配置的目标记录；搜索命中可用于下一轮扩展", "缺少正文不等于空正文", "未知值隐藏；原始数据仅在内存中读取"]}


def main():
    report = analyze(CONFIG["har_path"], CONFIG["target_ids"], CONFIG["search_terms"])
    output = Path(CONFIG["output_path"])
    if output.resolve() == Path(CONFIG["har_path"]).resolve():
        raise ValueError("输出不能覆盖源 HAR")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已分析 {report['entry_count']} 条记录；输出 {len(report['records'])} 个目标及 {len(report['search_hits'])} 个搜索命中。")


if __name__ == "__main__":
    main()
