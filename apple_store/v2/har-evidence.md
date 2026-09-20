# 当前订单抓包证据表

## 数据与使用

源文件：`D:/lqs/crawler/other/apple/url信息/所有_2026_09_20_09_21_37.har`，8,096,790 字节、528 条记录。
SHA-256：`b2f3cc4766e7752c21a964f59f5350c7cc7a93f3c5b12ff2a4256950c66b39fe`。
本表 ID 为 HAR `_id`，与已确认的 Reqable 记录对应；JSON 报告另外保留零基 `har_index`，两者不可混用。

运行：在项目根目录执行 `venv/Scripts/python.exe apple_store/har_analysis.py`。
编辑脚本顶部 `CONFIG` 指定本地 HAR、目标 ID、搜索词及报告位置，无命令行配置或交互输入。输出 `har-evidence.json` 为脱敏结构证据；本 Markdown 是人工验收的分析结论，不由脚本覆盖。源 HAR 不修改、不复制到仓库、不发送网络请求。

脚本使用 Python 标准库，当前整体加载 HAR；当前 8 MB 样本无需流式解析。二进制正文不参与一般文本搜索。支持 UTF-8 文本和 base64 编码文本、JSON 响应及 HTML init_data；选中记录的正文无效时明确报错。不支持的模型类型不猜测解析。缺失正文显式标记，不视为空请求。未知表单值隐藏；字段来源仍需分析者核实。

Skill：`C:/Users/15428/.codex/skills/har-chain-analysis/SKILL.md`。新会话可用 `$har-chain-analysis`，并提供本证据表路径；如果当前会话未刷新技能列表，可明确要求读取该文件。

## 已确认的请求与响应

所有模型字段路径均从响应 JSON 根开始；HTML 中从 `script#init_data` 开始。完整请求体字段名见同目录 JSON 报告。

| ID | 实际方法与动作 | 请求入参摘要 | 响应证据与意义 |
|---|---|---|---|
| 266 | POST continueFromFulfillmentToPickupContact | RETAIL、门店 R645、搜索地址等 9 个字段 | `body.checkout.d.page=PickupContact`；声明联系人及验证动作 |
| 344 | POST contactVerify | 姓、名、电话、邮箱、空 verificationToken | `body.checkout.pickupContact.selfPickupContact.selfContact.address.verificationModule.d` 中 authRequired=true、isVerified=false |
| 490 | POST submitVerificationToken | 一个非空 verificationToken | 同一模块 authRequired=false、isVerified=true；证明服务器接受验证结果，不说明 token 如何产生 |
| 504 | POST continueFromPickupContactToBilling | 联系人、验证令牌、证件后四位、发票类型、空抬头，共 8 项 | `body.checkout.d.page=Billing`；声明支付选择和继续动作 |
| 514 | POST selectBillingOptionAction | ALIPAY、空 selectBank、locationConsent=false | `body.checkout.d.page=Review`；`review.billingReview.alipayReview.d.alipayReview=true` |
| 518 | POST continueFromBillingToReview | ALIPAY、空 selectBank | 同样返回 Review；不能由此认定它可以省略 |
| 536 | POST continueFromReviewToProcess | 空体 | `head.status=302`；`head.data.url=/shop/checkout/status`；进入处理，不单独等于创单最终成功 |
| 541 | GET /shop/checkout/status | 无请求体、无查询参数 | `spinner.a.checkStatus.url` 声明 551 地址；`spinner.b.checkStatus.events` 声明 load 后延迟 500ms |
| 551 | POST /shop/checkoutx/statusX，checkStatus | 空体，_m=spinner | `head.data.url=/shop/checkout/interstitial` |
| 565 | GET /shop/checkout/interstitial | 当前结账会话、无请求体 | 用户已确认目标订单号所在结果页；不在证据表重复记录订单号及查询凭据 |

## 动作地址和模型头来源

下列响应 URL 与目标请求完整 URL 已在内存逐项比较；`har-evidence.json.links` 保留准确字段路径。

| 上游 → 请求 | 动作或跳转字段 |
|---|---|
| 266 → 344 | `body.checkout.pickupContact.selfPickupContact.selfContact.address.a.contactVerify.url` |
| 344 → 490 | `body.checkout.pickupContact.selfPickupContact.selfContact.address.verificationModule.a.submitVerificationToken.url` |
| 266 → 504 | `body.checkout.pickupContact.a.continueFromPickupContactToBilling.url` |
| 504 → 514 | `body.checkout.billing.billingOptions.a.selectBillingOptionAction.url` |
| 504 → 518 | `body.checkout.billing.a.continueFromBillingToReview.url` |
| 514 / 518 → 536 | `body.checkout.review.placeOrder.a.continueFromReviewToProcess.url` |
| 536 → 541、551 → 565 | `head.data.url` |
| 541 → 551 | `spinner.a.checkStatus.url` |

上述模型动作的四项请求头与来源 `meta.h`（JSON 在 body 内）均一致。这里只证明值匹配：多个响应共享同一令牌时，无法仅凭相等证明前端具体取自哪一份响应。URL 匹配也不能单独证明因果关系。

## 时序纠正：514 与 518 重叠

以下是 HAR Reqable `_startTimestamp` / `_endTimestamp` 对应的 UTC 时间：

| 请求 | 请求开始 | 响应完成 |
|---|---|---|
| 514 | 08:52:17.496695 | 08:52:25.611036 |
| 518 | 08:52:19.571406 | 08:52:20.717487 |
| 536 | 08:52:28.807254 | 08:52:36.168837 |

518 发出时 514 未返回；518 还先于 514 完成。因此不能描述为“收到 514 响应后再构造 518”。不能从此推导串行重放的等效性，也不能未经验证删除任何动作。

## 待查与下一步

1. 令牌返回来源已由下方追加分析定位至 487 响应头；仍需核对验证码交互、mode 语义和身份会话更新后才能实现。
2. 266 之前的加购、访客与自提记录已定位，见下方；仍需核对运行时 deviceID 与加购参数来源，不能把本样本 R645 代替其他配置。
3. 证件后四位是用户输入：266 模型中 nationalIdSelf 的绑定提示可证明其含义；不推断完整证件号，不复用样本个人信息。
4. x-aos-ui-fetch-call-1 的来源及必要性仍未确认；四个模型头匹配不代表其余头可省略。
5. 本工作仅分析已成功样本，不解决在线 HTTP 541，不证明新的 requests 会话可以创单。自动报告是证据提取器，不是已验证的交易执行器。

## 本次验证

真实 HAR 已成功提取 10 个目标记录与 6 个搜索命中，自动定位到此前尚未人工提供的 344、490。4 项回归测试通过，覆盖正文缺失与空体区分、base64 HTML 模型、隐私值不输出、精确地址关联、未知及重复 ID 拒绝。
Skill 标准校验器因本机两个 Python 环境均缺少 PyYAML 未能运行；已人工检查必填 frontmatter、名称、内容及引用。未为校验额外安装依赖。

## 2026-09-20 继续反推结果

本节直接只读检查同一 HAR，未重放网络请求。JSON 自动摘要仍覆盖此前的 10 条记录；以下新增事实以 HAR `_id` 和字段路径定位。

### 联系人验证令牌来源已闭合

| ID | 实际请求 | 证据 |
|---|---|---|
| 354 | GET id.apple.com/identity/verification | 返回验证组件 HTML，设置身份会话头 |
| 364 | GET /identity/verification/load | 返回本地化配置；响应 X-Apple-ID-Session-Id 与 487 请求中的值一致 |
| 365 | POST /identity/verification/generate/phone | JSON 请求字段 phoneNumber、mode；响应正文含 resend |
| 487 | POST /identity/verification/validate/phone | JSON 请求字段 phoneNumber、securityCode、mode；响应头含 X-Apple-Verification-Token |
| 490 | POST submitVerificationToken | 表单 verificationToken 与 487 响应头令牌完全一致 |
| 504 | POST continueFromPickupContactToBilling | 表单 verificationToken 与 490 的值完全一致 |

**令牌在 487 的响应头，不在 JSON 正文。** 只搜索 response.content.text 会漏掉它；本次通过查看响应头名称后在内存逐值比较确认，未输出原值。不能把 securityCode（验证代码）直接当作 verificationToken。

344 响应中 `body.checkout.pickupContact.selfPickupContact.selfContact.address.verificationModule.d`，以下简称 V，其值与 365、487 实际请求头逐项相等：

| 来源 | 请求头 |
|---|---|
| V.serviceKey | X-Apple-AppID-Key |
| V.options.token | X-Apple-Identity-token |
| V.options.context | X-Apple-I-Verification-Context |
| V.options.frameId | X-Apple-Frame-Id |
| V.options.nonce | X-Apple-I-Verification-Nonce |

354 的身份会话 ID 与 487 使用的不同，364 和 365 响应的值则与 487 一致。因此不可固定使用最初的会话 ID；其具体更新逻辑仍须逐请求核对。487 另带 X-Apple-Verification-Complete，其来源尚未追踪。

### 访客入口存在 POST 应用跳转

| ID | 行为 | 来源证据 |
|---|---|---|
| 143 | POST /shop/bagx/checkout_now，checkout | 116 模型 shoppingCart.actions.a.checkout.url 与实际地址一致 |
| 146 | GET /shop/signIn | 143 的 head.data.url 与 146 地址完整匹配 |
| 175 | POST /shop/signInx，guestLogin | 146 的 signIn.guestLogin.a.guestLogin.url 与实际地址一致 |
| 189 | POST /shop/checkout/start | 175 的 head.data.method=post；head.data.args 仅含 pltn，与 189 表单完整相等 |
| 202 | GET /shop/checkout，Fulfillment-init | 189 HTTP 302 的 Location 与 202 地址完整匹配 |

175 表单含 deviceID 和三项 consentOverlay 字段。146 的 `signIn.guestLogin.b.deviceID.events` 声明 load 时执行 DEVICEID 操作，不能用服务端初始空值代替运行结果。

175 的应用层 302 **不能固定转换为 GET**，必须处理明确声明的 POST 和 args。189 虽标注 application/json，实际 HTTP 302 响应正文为空；应先处理 HTTP 跳转，不能强制 JSON 解码。现有分析器若直接将 189 加入目标列表会遇到该格式边界，本次专项读取按原始状态/Location 核对，未修改业务代码。

### 自提选择与第二处响应乱序

实际请求开始顺序是 `202 → 222 → 228 → 216 → 266`，不是 ID 数值排序。

- 222 POST selectFulfillmentLocationAction，选择 RETAIL；响应选中门店 R479。
- 228 POST storeLocator.search，响应仍为 R479。
- 216 POST storeLocator.select，响应选中 R645。
- 266 提交 R645，进入联系人阶段。

228 开始时间戳 1789807842493653、结束 1789807851569838；216 开始 1789807844537798、结束 1789807845600714（均为 Reqable 微秒时间戳）。搜索请求尚未完成时选择请求已发出且先返回。不能将最后收到的 R479 搜索响应当作最终选店结果；必须保留动作语义并核对 266 的实际提交值。

### 加购到购物袋

- 53 GET 主商品地址，HTTP 303 Location 与 54 完整地址一致；54 是 attach 页面。
- 113 GET attach 页面表单请求，HTTP 303 Location 与 116 购物袋地址一致。
- 116 模型中只有一个商品行，SKU=MG714CH/A、数量=1；其 checkout 动作与 143 一致。
- 已证明这份历史样本中的商品和后续结账入口关联；53 的动态加购令牌和商品摘要来源还未逐字段追溯。

### 下一轮优先事项及原因

1. 核对 365、487 的 mode、phoneNumber、会话头更新及验证组件事件，解释如何合法取得当次 verificationToken；仅有令牌返回位置还不等于可无人值守验证。
2. 追溯 146 的 DEVICEID 运行结果及 53 的动态加购参数；这两类值仍不能从固定配置构造。
3. 解析器后续可增加响应头内存匹配和无正文 HTTP 跳转处理。当前默认正文搜索不覆盖响应头，人工分析必须补看。
4. 在完整契约确认前，不把历史成功链、重叠请求或模型动作声明直接转成未经验证的串行下单程序。

## 2026-09-20 验证参数与 deviceID 专项核对

365 与 487 的 JSON 请求均有 `mode=sms`。365 提交 `phoneNumber` 对象，键为 countryCode、countryDialCode、number；487 提交相同 phoneNumber，加上字符串 securityCode。两处手机号对象逐值相等，number 与 344 的联系人 fullDaytimePhone 相等。本次国家字段为 CN、86，不应据此替代其他国家的配置契约。securityCode 是当次短信验证码，不从历史抓包复制。

354 查询参数 widgetKey 与 344 的 verificationModule.d.serviceKey 相等。364 查询参数 serviceKey 也与之相等，frameId 与该模块 options.frameId 相等。364 另有 redirect_uri、language，具体来源仍需核实，不能只凭字段名猜测。

365 请求的 X-Apple-ID-Session-Id 与 364 响应同名头相等。365 响应继续返回同值，487 请求也使用此值；354 响应最初返回的值不同。487 的 X-Apple-Verification-Complete 为字符串 true；仅确认抓包实际值，前端如何决定设置此头仍未追踪。

该样本要求短信验证码输入，故不能仅凭产品配置保证无人参与下单。目前已还原这次验证码请求和令牌返回契约，不代表已实际发送短信或验证新手机号，也没有实现短信收取渠道。

146 HTML 引用 unified-signin.js、external.js、echo.min.js 等脚本，但按完整 src 地址在当前 HAR 中未找到对应记录；authService.latest.min.js 对应 148，HTTP 304，正文大小为 0。这是 deviceID 分析的实际证据缺口：当前只有模型声明 DEVICEID 操作，缺少执行该操作的脚本正文，不能推断它是 UUID、固定指纹或可省略字段。这里只确认 HAR 不含所需脚本，不断言所有本地缓存均不存在。

下一步可只读查找 Reqable 其他本地缓存中的同版本脚本；若仍缺失，补充浏览器禁用缓存后加载访客页的静态资源抓包，或读取对应公开脚本。此补证不需要重新提交订单。身份验证接口已足以定位短信参与点，暂不继续搜集历史验证码或凭据值。

## 2026-09-20 本地脚本缓存继续检查

只读搜索了 `C:/Users/15428/AppData/Roaming/Reqable/capture` 中约 38,000 个正文文件，以及 146 页面引用的三个公开脚本（unified-signin.js、external.js、echo.min.js）。没有发现可定位 `DEVICEID` 操作实现的脚本正文。部分历史文件只包含分析命令文本或页面数据，不能当作官网实现证据；公开脚本虽然含有 `x-aos-ui-fetch-call-1` 的 fetch 包装逻辑，但没有 `DEVICEID` 生成实现。

146、202、541 页面正文都出现 `pageViewId` 文本；页面内联代码用 `Math.random().toString(36).substring(2, 12) + '-' + Date.now().toString(36)` 生成账户页面埋点标识。当前没有证据证明它等于访客 `DEVICEID`，不能替代 DEVICEID 字段。

已确认 `x-aos-ui-fetch-call-1` 由网页 fetch 包装器在 `uiConfig.fetchHeaders.sendHeaders=true` 时加入；其请求头值是每次调用的运行时值，当前 HAR 未提供足以证明其生成规则的配置全貌。它不应写死为历史样本值。

结论：本地目录可作为长期证据源，但当前这批缓存没有闭合 deviceID。下一步若要继续，只读导出一次“禁用浏览器缓存后打开 /shop/signIn 并点击访客”的静态资源和请求；目标是取得包含 DEVICEID 操作实现的脚本或观察运行时字段形状，不需要重新提交订单。
