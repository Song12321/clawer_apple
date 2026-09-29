"""Apple phone verification using the current checkout verification model."""
from urllib.parse import urlencode, urlsplit

import requests
from apple_store.network import fetch
from apple_store.request_log import timing


def verify(store_session, page_url, data, phone):
    service = data["serviceURL"].rstrip("/")
    if service != "https://id.apple.com/identity":
        raise ValueError("Unsupported identity service URL")
    options = data["options"]
    parsed = urlsplit(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    widget_url = service + "/verification?" + urlencode({
        "widgetKey": data["serviceKey"], "redirect_uri": origin,
    })
    with requests.Session() as identity:
        identity.trust_env = False
        identity.proxies.update(store_session.proxies)
        identity.headers.update({"User-Agent": store_session.headers["User-Agent"],
                                 "Accept": "application/json"})

        def send(method, url, **kwargs):
            try:
                response = fetch(identity, method, url, timeout=30, allow_redirects=False, **kwargs)
            except requests.RequestException:
                raise RuntimeError("Identity request failed; no automatic retry") from None
            if response.status_code != 200:
                raise RuntimeError(f"Identity {urlsplit(url).path}: HTTP {response.status_code}")
            return response

        send("GET", widget_url, headers={"Referer": page_url, "Accept": "text/html"})
        loaded = send("GET", service + "/verification/load", params={
            "serviceKey": data["serviceKey"], "redirect_uri": origin,
            "frameId": options["frameId"], "language": options["locale"],
        }, headers={"Referer": widget_url, "Content-Type": "application/json"})
        identity.headers.update({
            "X-Apple-ID-Session-Id": loaded.headers["X-Apple-ID-Session-Id"],
            "X-Apple-AppID-Key": data["serviceKey"],
            "X-Apple-Identity-token": options["token"],
            "X-Apple-I-Verification-Context": options["context"],
            "X-Apple-Frame-Id": options["frameId"],
            "X-Apple-I-Verification-Nonce": options["nonce"],
            "Origin": "https://id.apple.com", "Referer": widget_url,
        })
        body = {"phoneNumber": {"countryCode": "CN", "countryDialCode": "86", "number": phone},
                "mode": "sms"}
        generated = send("POST", service + "/verification/generate/phone", json=body)
        identity.headers["X-Apple-ID-Session-Id"] = generated.headers["X-Apple-ID-Session-Id"]
        print("短信已发送到配置的手机号。", flush=True)
        with timing("等待用户输入验证码（人工耗时）"):
            print("请输入短信验证码（6 位数字），输入后回车继续：", end="", flush=True)
            code = input().strip()
        if len(code) != 6 or not code.isascii() or not code.isdigit():
            raise ValueError("Verification code must contain six digits")
        validated = send("POST", service + "/verification/validate/phone",
                         headers={"X-Apple-Verification-Complete": "true"},
                         json={**body, "securityCode": code})
        token = validated.headers.get("X-Apple-Verification-Token")
        if not token:
            raise ValueError("Identity verification returned no verification token")
        return token
