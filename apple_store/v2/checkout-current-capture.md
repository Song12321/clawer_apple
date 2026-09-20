# 当前订单结账链核对

本次只读分析 Reqable 本地记录，未重新提交订单。正文缓存只有请求/响应正文，实际方法和最终提交模块仍需与 Reqable 请求元数据核对。凭据和个人信息不写入本文。

## 已确认的链路

1. 访客入口：`1789721864056324-623-1` 请求体包含 `signIn.guestLogin.deviceID` 及三个 consentOverlay 布尔字段，响应业务 302。deviceID 必须取当次页面运行结果，不能复制旧值或自行猜测生成规则。
2. 自提选择：`1789721865198439-625-3` 提交 `checkout.fulfillment.fulfillmentOptions.selectFulfillmentLocation=RETAIL`。随后 storeLocator 提交门店和地址字段。
3. `1789721867804429-635-3` 进入 PickupContact。其请求最终选择 R479，区别于现有项目配置 R448；不能自动覆盖配置。北京、朝阳区是该抓包中的搜索条件，不代表新订单必须沿用。
4. `...635-4` contactVerify：姓名、电话、邮箱及空 verificationToken。响应 verificationModule.d.authRequired=true、isVerified=false。
5. `...635-5` submitVerificationToken：提交非空 verificationToken；响应 authRequired=false、isVerified=true。令牌来源是当次 Apple 验证组件，服务地址 `https://id.apple.com/identity`，加载器 `https://appleid.cdn-apple.com/identity/static/jsapi/loader/verifyLoader.latest.js`。不能重放旧令牌。
6. `...635-6` 提交联系人、同次验证令牌、个人发票选项及 invoiceHeader，响应进入 Billing。
7. `1789721953904611-683-1` 提交支付选项 ALIPAY；`...635-7` 请求体为支付选项和 locationConsent，响应进入 Review。不能照搬旧记录中 selectBank 字段。
8. Review 模型同时声明 checkout.review 和 checkout.review.placeOrder 下的 continueFromReviewToProcess。`...635-8` 响应指向 `/shop/checkout/status`；尚需核对实际提交请求的模块和空体情况，不以缺少请求正文文件推定空请求。
9. `...635-9` 为状态页，`...635-11` 业务 302 指向 interstitial，`...635-12` 为用户指定订单的结果页。

## 新订单实施前的缺口

用户已明确确认姓 xing、名 min，门店 R448（王府井），保持现有配置。

已增加 Python Cookie 到实际浏览器页面的 CDP 同步，在线确认结账登录页能够在同一浏览器打开并显示“以游客身份继续”。原始模型明确 deviceID 由 load 事件的 DEVICEID 操作生成，而非有值的服务端隐藏输入。下一次访客动作探测在初始化履约查询收到 541，按严格失败要求停止，未加购或提交访客请求。尚未完成访客动作与创单实现。

最新在线诊断：Python 初始化有效会话、加购并核验单件购物袋后，checkout_bag 成功进入 `/shop/signIn`，模型包含 guestLogin 动作。服务端初始模型的 deviceID 为空，HTML 中没有对应有值的输入，因此必须获取页面运行时生成的 deviceID；不能仅解析服务器 HTML。此次停在访客入口，未提交访客表单、联系人或订单。

- 姓名已由用户明确确认，沿用 CONFIG。
- 门店已确认 R448，不沿用历史订单的 R479。
- 需查明并接入当次 deviceID 与联系人验证组件流程；若需要用户完成验证，应保留当次会话，不重新创单或复用历史令牌。
- 实际提交前核对当前 Review 中商品、数量、门店、联系人、支付方式和金额；只创建待支付订单，不执行付款。

主脚本仍止于加购，没有接入不完整的创单流程。
