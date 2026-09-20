# 从订单结果倒推的接口入参表

依据：同目录 har-evidence.md 中标识的 HAR；所有 ID 为 Reqable `_id`。仅分析成功样本，不重放。分类：①前序响应/会话提供；②运行时生成（是否加密须有证据）；③固定协议值或用户配置；？未确认。字段名为便于阅读省略模块前缀，完整字段名见 HAR。表内“固定”仅指当前已确认分支，不泛化至其他支付、配送或商品类型。

## 公共输入（不在每行重复）

- Cookie：①本次会话初始化及后续 Set-Cookie 持续更新，requests.Session 保留域/路径；不是只复制某一个响应。不应自行加密或使用历史值。初始化通过官网验证的能力仍受 HTTP 541 阻塞。
- 商城模型头：①来源模型 meta.h：x-aos-model-page、modelVersion、syntax、x-aos-stk；JSON 通常在 body.meta.h，HTML 在 init_data.meta.h。已匹配的具体来源见 har-evidence.json.links。值相同不唯一证明前端取自哪个响应。
- 动作 URL：①读取模型 a.<动作>.url，携带 _a、_m 及其他动态参数；不把 secure7 固定为所有会话主机。
- Origin/Referer：①实际页面上下文；Content-Type：③按抓包的表单或 JSON 编码。其他浏览器头最小必要集合未验证。
- x-aos-ui-fetch-call-1：②前端 fetch 包装器生成/注入，完整规则及必要性待查；无证据需要密码学加密。

## 逆序逐接口

| ID / 方法 / 接口 | 它需要什么 | ①明确来源 | ③固定或用户配置 | ② / ？缺口 |
|---|---|---|---|---|
| 565 GET interstitial | 地址、当前会话；无请求体 | 551 head.data.url；结果读取 init_data.thankYouInterstitial.d.orderNumber | GET | 无独立加密字段证据 |
| 551 POST checkStatus | 地址、模型头；空体 | 541 spinner.a.checkStatus.url、meta.h | 空 POST；_m 随动作 URL | 其他处理中响应尚未验证 |
| 541 GET status | 地址、会话；无体 | 536 head.data.url | 本次 GET | 无独立加密字段证据 |
| 536 POST continueFromReviewToProcess | 动作 URL、模型头；空体 | 514/518 body.checkout.review.placeOrder.a.continueFromReviewToProcess.url、meta.h | POST；本次空体 | 下单前核对订单内容；不能把进入 status 当最终成功 |
| 518 POST continueFromBillingToReview | selectBillingOption、selectBank | 504 billing.a.continueFromBillingToReview.url；bankLookUp.d.selectBank 初始为空 | ALIPAY 为用户支付配置；selectBank 本次空串 | 与 514 重叠，不能断言可省略或必须等待它 |
| 514 POST selectBillingOptionAction | selectBillingOption、selectBank、locationConsent | 504 billing.billingOptions.a.selectBillingOptionAction.url；bankLookUp.d.selectBank；checkout.locationConsent.d.locationConsent=false | ALIPAY 为用户选择 | 无独立加密字段证据；响应已为 Review |
| 504 POST continueFromPickupContactToBilling | emailAddress、fullDaytimePhone、lastName、firstName、verificationToken、nationalIdSelf、selectFapiao、invoiceHeader | 动作来自 266 pickupContact.a；token 来自 487 响应头并经 490 验证；266 发票模型含空抬头 | 联系人、证件后四位为用户配置；本次个人发票 e_personal_fdf、空抬头 | 不自行加密/生成 token；其他发票类型未分析 |
| 490 POST submitVerificationToken | verificationToken | 487 响应头 X-Apple-Verification-Token；动作来自 344 verificationModule.a | POST 表单 | 此 token 与验证码不是同一值 |
| 487 POST /identity/verification/validate/phone | phoneNumber、securityCode、mode、身份头 | phoneNumber 与 365 相同；身份头见下表 | mode=sms；securityCode 来自当次收到的短信 | 验证码需要接收人输入，未具备自动收取渠道；token 由服务器返回，不需本地伪造 |
| 365 POST /identity/verification/generate/phone | phoneNumber、mode、身份头 | number 与 344 联系人手机相同；会话头来自 364 | 国家配置，本次 CN/86；mode=sms | 身份服务 URL 的完整前端动作来源待补，不能仅靠名称推导其他分支 |
| 364 GET /identity/verification/load | serviceKey、redirect_uri、frameId、language | serviceKey=344 V.serviceKey；frameId=V.options.frameId；language=V.options.locale，逐值核对为 zh_CN | 无需硬编码令牌 | redirect_uri 与结账页 Origin 相同，来源语义需前端核对 |
| 354 GET /identity/verification | widgetKey、redirect_uri | widgetKey=344 V.serviceKey；响应提供初始身份会话头 | 页面加载 GET | redirect_uri 与结账 Origin 相同；初始会话头后来变化，不能一直复用 |
| 344 POST contactVerify | 姓、名、电话、邮箱、空 verificationToken | 动作来自 266 address.a.contactVerify；初始 token 来自 266 verificationModule.d，为空 | 联系人来自用户配置 | 返回 authRequired=true 后才能按该响应启动验证组件 |
| 266 POST continueFromFulfillmentToPickupContact | RETAIL、showAllStores、selectStore、searchInput、省市区五字段 | 当次履约模型及动作；216 响应确认 R645 | 门店与地区为用户选择；本次 RETAIL、showAllStores=false | 228/216 响应乱序，不能用最后返回的搜索结果覆盖选店 |
| 216 POST storeLocator.select | showAllStores、selectStore、searchInput、省市区五字段 | 当次 storeLocator、地址模型及 select 动作 | 用户选择 R645；搜索条件 | 选店可用性应按本次模型核验，不能以旧 Cookie 的 R479 判断最终选择 |
| 228 POST storeLocator.search | 与 216 同组字段 | 当次 storeLocator、地址模型及 search 动作 | 搜索地区为用户输入；选择字段携带当前状态 | 请求早于 216，响应晚于 216；不按 ID 数值排序 |
| 222 POST selectFulfillmentLocationAction | selectFulfillmentLocation | 202 fulfillment.fulfillmentOptions 动作模型 | RETAIL（自提分支） | 配送分支不在当前范围 |
| 202 GET checkout | 地址、会话 | 189 HTTP Location | GET | 返回 Fulfillment 初始模型 |
| 189 POST checkout/start | pltn | 175 head.data.args.pltn；method=post | 按响应声明 POST，不自行改 GET | 已完整比对 args 与实际表单；不能把此值写死 |
| 175 POST guestLogin | deviceID、三项 consentOverlay | 动作来自 146 signIn.guestLogin.a，动态 ssi/up 随 URL | 同意项来自用户同意及页面状态，不自动视为 true | deviceID=页面 DEVICEID 操作的运行结果；取得方式未闭合，无证据证明必须自行加密 |
| 146 GET signIn | 含 ssi/up 的地址、会话 | 143 head.data.url | GET | ssi 不自行拼接/复制历史值 |
| 143 POST checkout | 推荐商品 part、动态商品行键、数量、省市区、locationConsent、promoCode、fcscounter、fcsdata | 116 shoppingCart 各模块及 actions.a.checkout；商品行键从 items 读取 | 数量、地址、优惠配置按用户选择 | fcscounter/fcsdata 的运行时更新需进一步对照 b.events，不能只取初始模型便称完成 |
| 116 GET bag | 地址、会话 | 113 HTTP Location | GET | 已核验单件 MG714CH/A |
| 113 GET attach 继续 | proceed、product、step | 54 表单/按钮及隐藏字段为待逐字段核对来源 | step=attach 为实际分支值 | 不单凭 54→113 的先后认定所有字段来源已闭合 |
| 54 GET attach 页 | product、step | 53 HTTP Location 完整匹配 | GET | 无独立加密字段证据 |
| 53 GET 加购 | product、purchaseOption、step、acpart、atbtoken、igt、add-to-cart | atbtoken 与请求 Cookie as_atb 最后一个竖线分段逐值一致；Cookie 最早产生响应尚待定位 | SKU 为用户商品映射；样本 fullPrice/select/none/true/add-to-cart | 其余字段应来自当前商品表单/摘要，完整来源待补；atbtoken 相等关系不等于已知 Cookie 生成算法 |

## 身份请求头来源（365、487）

V = 344 响应 `body.checkout.pickupContact.selfPickupContact.selfContact.address.verificationModule.d`。

| 请求头 | 来源及证据 |
|---|---|
| X-Apple-AppID-Key | ①V.serviceKey，逐值相等 |
| X-Apple-Identity-token | ①V.options.token，逐值相等 |
| X-Apple-I-Verification-Context | ①V.options.context，逐值相等 |
| X-Apple-Frame-Id | ①V.options.frameId，逐值相等 |
| X-Apple-I-Verification-Nonce | ①V.options.nonce，逐值相等 |
| X-Apple-ID-Session-Id | ①365 使用 364 响应头；487 与 365 响应头一致；354 的初始值不同 |
| X-Apple-Verification-Complete | ③487 本次为 true；前端设置条件待查，不能当通用常量 |

## 汇总结论

本次没有证据要求我们自己加密联系人、商品参数、pltn 或 verificationToken；它们是配置或服务器返回值。deviceID 与会话验证的生成机制仍是未知，不应提前归类为“必须破解加密”。

主要缺口已收敛为：有效新会话（541）、当次 deviceID、短信验证码输入、加购参数最初来源、少量前端状态字段及重叠请求的串行契约。逆推可以说明参数来源，但不能代替新会话执行验收。
