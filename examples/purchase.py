"""python examples/purchase.py product.json --quantity 1"""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description="配置商品、加购并进入结账页面")
    parser.add_argument("product", type=Path, help="商品配置 JSON 文件")
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    product = json.loads(args.product.read_text(encoding="utf-8-sig"))
    with httpx.Client(base_url=args.base_url, timeout=180,
                      headers={"Authorization": f"Bearer {os.environ['APPLE_API_TOKEN']}"}) as client:
        def call(method, path, body=None):
            response = client.request(method, path, json=body, headers={"Idempotency-Key": str(uuid4())})
            response.raise_for_status()
            return response.json()

        session = call("POST", "/sessions", {"headless": False})
        prefix = f"/sessions/{session['id']}"
        print(f"Session: {session['id']}", flush=True)
        # Deliberately keep the browser open on success OR failure for inspection.
        call("PUT", prefix + "/product", product)
        call("POST", prefix + "/bag/items")
        call("PATCH", prefix + "/bag/item", {"quantity": args.quantity})
        result = call("POST", prefix + "/checkout")
        print(json.dumps({key: result[key] for key in ("id", "phase", "url")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
