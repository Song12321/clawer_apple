from config import CONFIG
from order import base, checkout


def main():
    for key, value in CONFIG.items():
        if isinstance(value, str) and not value.strip():
            raise ValueError("请填写配置：" + key)
    if CONFIG["数量"] != 1 or CONFIG["支付方式"] != "ALIPAY" or CONFIG["发票类型"] != "e_personal_fdf":
        raise ValueError("本脚本仅支持单件商品、支付宝、个人电子发票")
    if len(CONFIG["证件后四位"]) != 4:
        raise ValueError("证件后四位必须为四个字符")
    with base.sync_playwright() as playwright:
        with base.browser_session(playwright, CONFIG["商品页面"], include_page=True) as (session, browser):
            page = base.request(session, "GET", CONFIG["商品页面"])
            product = base.select_product(page.content, CONFIG)
            bag = base.read_model(base.follow_navigation(session, base.request(session, "GET", base.apple_url(page.url, "/shop/bag"))))
            if any(k.startswith("item-") for k in bag["shoppingCart"]["items"]):
                raise ValueError("初始购物袋非空")
            _, form = base.fetch_summary(session, page, product)
            bag_page = base.add_to_bag(session, page, form)
            result = checkout(session, browser, bag_page, CONFIG, product["partNumber"])
            print("订单号：" + result["订单号"])
            return result


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        # 本地配置及业务检查已使用不包含凭据的错误信息。
        raise SystemExit("流程停止：" + str(error) + "；未自动重试。") from None
    except Exception as error:
        # 原始网络/浏览器异常可能含 Cookie、URL 令牌或个人信息，不打印详情。
        raise SystemExit("流程停止：" + type(error).__name__ + "；未自动重试。") from None
