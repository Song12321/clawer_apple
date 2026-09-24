# 当前订单抓包证据表

后续请求缩减以 [必要请求链路](../../v2/必要请求链路.md) 为当前基线。2026-09-24 21:34 已完成一次省略 search 的有货完整创单回归（MG714CH/A、R448），当前直接 select 配置门店；此前缺货实验不能证明 search 必需，本次成功也不能推广到所有会话。该文档单独区分新线上日志与本文历史 HAR 证据。

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

## 2026-09-22 登录态结账样本（Reqable 本地缓存，未导出 HAR）

### 数据与强度

源：`C:/Users/15428/AppData/Roaming/Reqable/capture`，本次会话正文文件 1,005 个，命名形如 `{连接起始微秒}-{连接号}-{HTTP/2 流号}-{方向}-{类型}.reqable`，本地时间 20:49:07–20:53:45。结账链路集中在连接 `1790081462623766-121`（20:51:02–20:53:45）。

本次没有导出 HAR，磁盘只有正文缓存，没有请求行、状态码与响应头；端点由响应模型自带的动作地址和 302 响应正文反推，耗时按“请求正文落盘时刻 → 响应正文落盘时刻”估算。证据强度低于上面的 HAR 表，HTTP 状态与响应头仍需导出 HAR 复核。头名可见但值未输出。

### 实际链路（本地时间）

| 动作（依据） | 请求落盘 | 响应落盘 | 耗时 | 响应证据 |
|---|---|---|---|---|
| POST grantCode（空值 10 字节） | 20:51:02.852 | 20:51:03.248 | 0.40s | 302，`head.data.url=https://www.apple.com.cn/iphone/` |
| POST grantCode（空值 10 字节） | 20:51:55.716 | 20:51:57.152 | 1.44s | 302，`url=…/shop/checkout/start`，`method=post`，`args.pltn` |
| POST /shop/checkout/start（pltn） | 20:51:57.164 | 20:51:58.429 | 1.27s | 空正文，进入结账模型 |
| selectFulfillmentLocationAction | 20:52:01.396 | 20:52:02.945 | 1.55s | `page=Fulfillment` |
| storeLocator.search | 20:52:03.000 | 20:52:12.411 | 9.41s | `page=Fulfillment`，含 searchResults |
| continueFromFulfillmentToPickupContact（合并 selectStore） | 20:52:14.731 | 20:52:22.293 | 7.56s | `page=PickupContact`，`authRequired=false` |
| continueFromPickupContactToBilling | 20:52:43.021 | 20:52:44.072 | 1.05s | `page=Billing` |
| selectBillingOptionAction | 20:52:45.655 | 20:52:53.915 | 8.26s | `page=Billing` |
| continueFromBillingToReview | 20:52:47.760 | 20:53:03.875 | 16.12s | `page=Review` |
| 同一 billing 表单再次提交 | 20:53:01.545 | 20:53:13.331 | 11.79s | `page=Review` |
| continueFromReviewToProcess | 未见请求正文文件 | 20:53:23.319 | — | 302，`url=/shop/checkout/status`；空体仍待 HAR 复核 |
| statusX 轮询至跳转 | — | 20:53:43.269 | 约 19.5s | 302，`url=/shop/checkout/interstitial` |
| 购物袋浮动层配置 | — | 20:53:44.344 | — | `{"items":0,…}`，袋子已清空 |

结账入口到结果页合计约 110s；Apple ID 认证（组件页、两次 SRP `{"a":…}`、`authType=hsa2`）发生在 20:49:31–20:50:38，早于结账入口。

### 结论

1. 登录态样本未要求手机号验证：PickupContact 模型 `authRequired=false`，随后的 continueFromPickupContactToBilling 表单共 7 项且 `verificationModule.verificationToken` 为空，服务端仍返回 `page=Billing`；该表单不含 emailAddress。对照上面的 344→365→487→490，访客态同一位置 `authRequired=true`，必须补令牌。
2. 登录态模型自 Billing 起多出 `x-as-actk` 头（514/518 等访客态模型只有 `x-aos-model-page`、`modelVersion`、`syntax`、`x-aos-stk`）。该头在后续步骤间还会变化，来源尚未追踪。
3. 慢请求没有变少：两侧的慢点都是门店搜索、Fulfillment 绑定、Billing/Review 模型往返与 statusX 轮询。本次 9.41s、7.56s、8.26s、16.12s、11.79s 均超过 6s，且 billing/review 比 9/20 的 8.12s+1.15s 慢。登录态省下的是 365→487 之间 40.28s 的等码与校验段（含 344、490 共约 2.2s 请求）。
4. 缓存中本次门店绑定已合并进 continueFromFulfillmentToPickupContact，与 `order.py` 现有做法一致；未出现单独的 storeLocator.select。
5. 20:51:55 的 grantCode 与 checkout/start 两步共 2.71s，是“闪一下登录页”的 shop 侧会话提升，不是口令登录。

### 待查

1. 导出本次 Reqable 会话为 HAR，补齐 URL、方法、状态码、响应头与真实耗时，替换本节的估算值。
2. `x-as-actk` 的取值来源、变化时机及是否可省略；未澄清前不能在脚本里跳过登录握手直接打 `checkoutx` 动作。
3. 第二个 grantCode 能否直接以空值重放取决于 shop 会话 cookie 是否已处认证结账态；需要一次可控会话做对照验证。
4. 20:53:01 的重复 billing 提交是页面重试还是重复点击，需凭 HAR 的 initiator 判断。

## 2026-09-22 21:10 登录态加购+结账（HAR 导出，未重放）

### 数据与强度

源：`D:/lqs/crawler/other/apple/url信息/_2026_09_22_21_13_08-登录态加购_结账.har`，8,821,909 字节、341 条记录。
SHA-256：`c9fbdc189d9860438d663075ab1832a71bfa1fdb849282710f7cfce4958d3266`。
Reqable 2.33.12 全流量导出，含 chatgpt、douyin、youtube 等无关域名；Apple 域名 186 条，全部落在 13:10:50–13:12:52Z（本地 21:10:50–21:12:52），涉及连接 `_cid` 234/235/236/237/239。

本表 ID 为 HAR `_id`，时间取 HAR `startedDateTime`（UTC，本地时间 = +8h）。本次是真实 HAR，带 URL、方法、状态码、响应头与实测 `time`，强度高于上一条的缓存估算。

上一节 20:51 缓存样本（连接 `1790081462623766-121`）的 Apple 请求不在本 HAR 中，两者是两次独立下单；该节的估算值仍未由 HAR 替换。本条结论只覆盖本次抓包。

提取方式：复用 `apple_store/v2/har_analysis.py` 的 `response_text`/`model_from`/`walk`/`fields` 对这些 ID 做只读专项读取；未改 `CONFIG`，未覆盖 `har-evidence.json`，未重放任何请求，未输出凭据与个人信息原值。

### 实测链路

购物袋结账按钮 → 结果页：106.63s（1007 开始 → 1089 完成）。

| ID | 本地开始 | 耗时 | 请求 | 响应证据 |
|---|---|---|---|---|
| 1007 | 21:11:05.551 | 0.436s | POST `/shop/bagx/checkout_now`，_a=checkout | `head.data.url=/shop/checkout/start?pltn=…` |
| 1008 | 21:11:05.995 | 1.510s | GET `/shop/checkout/start?pltn=…` | HTTP 302，Location `/shop/checkout`，空正文 |
| 1009 | 21:11:07.863 | 2.208s | GET `/shop/checkout` | 200，`checkout.d.page=Fulfillment` |
| 1013 | 21:11:08.573 | 2.807s | GET `/shop/shld/v2_1/verify.js` | 200，41,400 字节 |
| 1016 | 21:11:10.089 | 1.292s | GET `/shop/bag/status` | 200；secure10 结账会话的 apikey 与购物袋页不同值 |
| 1020 | 21:11:12.780 | 1.173s | POST `/shop/checkoutx/fulfillment`，_a=selectFulfillmentLocationAction | 局部更新，仍 Fulfillment |
| 1023 | 21:11:13.982 | 9.850s | POST `/shop/checkoutx/fulfillment`，_a=search（storeLocator） | 含 searchResults |
| 1041 | 21:11:25.014 | 8.378s | POST `/shop/checkoutx/fulfillment`，_a=continueFromFulfillmentToPickupContact | `page=PickupContact`，门店与地址字段随本次提交 |
| 1054 | 21:11:50.552 | 1.009s | POST `/shop/checkoutx`，_a=continueFromPickupContactToBilling | `page=Billing` |
| 1056 | 21:11:52.976 | 8.173s | POST `/shop/checkoutx/billing`，_a=selectBillingOptionAction | `page=Billing` |
| 1058 | 21:11:54.365 | 17.132s | POST `/shop/checkoutx/billing`，_a=continueFromBillingToReview | `page=Review` |
| 1062 | 21:12:04.197 | 16.656s | 同一 billing 动作重复提交 | 同样返回 `page=Review` |
| 1070 | 21:12:16.221 | 14.639s | POST `/shop/checkoutx/review`，_a=continueFromReviewToProcess，空体 | `head.status=302`，`head.data.url=/shop/checkout/status` |
| 1075 | 21:12:22.870 | 无 | 同一 review 动作重复提交，空体 | 无响应正文，`status=0`，未完成 |
| 1076 | 21:12:30.869 | 0.776s | GET `/shop/checkout/status` | 200 |
| 1085 | 21:12:34.704 | 16.087s | POST `/shop/checkoutx/statusX`，_a=checkStatus，空体 | `head.data.url=/shop/checkout/interstitial` |
| 1089 | 21:12:50.801 | 1.378s | GET `/shop/checkout/interstitial` | 200；随后 1097 `/shop/bag/status` 返回 `items=0` |

乱序与重叠（依据 `_stime`）：1058 在 1056 未返回时发出（间隔 1.389s）；1062 在 1058 未返回时发出（间隔 9.832s）；1075 在 1070 未返回时发出（间隔 6.649s）。记录顺序不能当作依赖关系。

### 与访客态样本（9/20 HAR）对比

| 维度 | 访客态 9/20 | 登录态 9/22 |
|---|---|---|
| 结账按钮 → 结果页 | 139.22s（HAR 08:50:29.194→08:52:48.416Z） | 106.63s（21:11:05.551→21:12:52.179） |
| 链路请求数（不含静态与埋点） | 22 | 17 |
| ≥5s 慢请求 | 5 个，合计 39.42s | 7 个，合计 90.92s |
| 慢点构成 | 门店搜索 9.08、履约绑定 8.60、Billing 8.12、Review 7.36、statusX 6.27 | 门店搜索 9.85、履约绑定 8.38、Billing 8.17+17.13+16.66、Review 14.64、statusX 16.09 |
| 全链路请求耗时合计 | 55.33s | 103.50s |
| 手机号验证段 | contactVerify 0.75s + 验证组件 3 请求 1.34s + 等码与输码 39.62s + validate 0.70s + submitVerificationToken 0.73s | 不存在 |
| 登录相关请求 | GET /shop/signIn 0.62s + POST /shop/signInx guestLogin 0.67s | 无 |
| 门店选择 | 单独 storeLocator.select 1.06s | 已并入 1041，未单独出现 |
| 人工填表停顿 | 266→344 16.26s、490→504 13.53s | 1041→1054 17.16s |

### 本次新确认的事实

1. 登录态确实免手机号验证：1041 响应 `body.checkout.pickupContact.selfPickupContact.selfContact.address.verificationModule.d.authRequired=false`；1054 表单 7 项，`verificationModule.verificationToken` 为空即返回 `page=Billing`；全 HAR 中 `contactVerify`、`submitVerificationToken`、`id.apple.com`、`idmsa.apple.com.cn` 请求均为 0 条。
2. 登录态模型不再下发验证组件：对照 266（访客）与 1041（登录）同一路径，访客态有 `d.isVerified`、`d.emailAddress`、`address.a.contactVerify`、`verificationModule.d.serviceURL/jsLibrary/options.token/options.nonce`；登录态这些字段全部不存在，`verificationModule.d` 仅剩 `id`、空 `verificationToken`、`authRequired=false`。1054 表单也不含 `emailAddress`。
3. 本次没有任何 Apple ID 登录：无 `/shop/signIn` 页面、无 `/shop/signInx` guestLogin、无 `grantCode`、无 id.apple.com。唯一会话动作是 1008 的 `GET /shop/checkout/start?pltn=…` → 302 → `/shop/checkout`，即从购物袋会话切到 secure10 结账会话；同一路径 `bag/status` 的 apikey 在结账前后不同值，下单完成后回到结账前的值。上一节 20:51 样本出现过两次 `grantCode`，本次没有，说明该步骤不稳定，不能因一次未出现就删除处理逻辑。
4. `x-as-actk` 只在登录态 Billing/Review 请求出现（1056、1058、1062、1070）；访客态 514、518、536、551 及其余请求都只有 `x-aos-model-page`、`x-aos-stk`、`x-aos-ui-fetch-call-1`、`x-requested-with`。传递规则已在内存逐值核对：1054 响应 `body.meta.h."x-as-actk"` 与 1056 请求头相等，1056 响应与 1058 请求头相等；1058、1062 响应不再下发该头，1062、1070 请求仍携带同一值，说明客户端在下发一次后会持续沿用。1076 状态页与 1085 statusX 请求都没有该头。实现时应从模型 `meta.h` 取值并在该结账会话内保持，不能写死。
5. 重复提交与登录态无关但影响自动化：本样本 1062 重复 billing、1075 重复 review（后者被中断）。照抄浏览器行为可能导致重复提交 placeOrder。

### 待查与下一步

1. 1062、1075 重复提交的触发者：HAR 无 initiator 字段，需在 Reqable 界面按记录查看发起信息，或做一次人工单击对照。
2. 20:51 缓存样本仍未导出 HAR，其估算值未经实测确认；若要闭合，应单独导出该会话窗口。
3. 登录态免验证是否稳定：本样本只有一次，需不同账号或不同门店的自提样本复核后才能写进实现契约。
4. `x-as-actk` 取值来源与变化时机。
5. 1089 之后的订单结果页未在本 HAR 中；`items=0` 只能说明购物袋已清空，不能等同创单成功。
6. 门店搜索与履约提交的门店地址字段：`provinceCityDistrict` 在 1023（登录态）为“湖北 武汉 江汉区”，在 9/20 的 228、266（访客态）为“北京 朝阳区”；同一 `_a=search` 动作的 `searchInput` 在 1023 为“湖北 武汉 江汉区”而 228 为“北京 朝阳区”，266 又变为“北京 北京 朝阳区”。该字段由页面选择器生成，格式随地区变化，`v2/order.py` 目前按“市 区”合成，与两次抓包都不完全一致，线上是否校验仍待验证。
