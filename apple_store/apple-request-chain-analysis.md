# Apple 中国商城请求链路分析

分析日期：2026-09-17。依据：本机 Reqable 已保存的请求体、解压后的响应正文，以及对话中提供的 cURL。没有向 Apple 重放请求，没有新增订单。

## 1. 结论与证据边界

已从订单结果逆向关联到同一购物袋商品，并还原业务流程：

```text
商品选配 → 生成购买摘要 → 异步加购 → 购物袋
→ 购物袋结账 → 访客入口 → Checkout 初始化
→ 门店自提 → 联系人验证 → 联系人与发票信息
→ 支付方式 → Review → 提交订单 → 处理状态 → 订单结果
```

本次样本为 iPhone 17、256GB、鼠尾草绿色，SKU `MG714CH/A`，数量 1；自提门店样本为 `R448`（Apple 王府井）；支付方式为 `ALIPAY`。这些是历史样本值，不是新订单的默认配置。配送到家、其他机型、登录账户、分期付款、以旧换新等分支未由本样本验证。

**业务链路已关联；完整可重放的 HTTP 契约尚未全部确认。** 本地 capture 文件主要保存正文，不是 HAR；其文件名不能直接证明 URL、方法、请求头、HTTP 状态或精确请求时间。本文区分：

- **实测请求**：对话提供了实际 cURL，可确认方法和请求头结构。
- **正文关联**：同一记录前缀的请求体与响应体可关联，但完整请求元数据未恢复。
- **页面声明**：响应的动作地址或表单字段，可证明页面如何描述动作，不能单独证明实际发出的 HTTP 请求。

尤其不能把主商品加购直接等同于附件页里的 `/shop/bag/add`，也不能把 `submit: true` 自动解释为已确认 POST。

## 2. 原始证据索引

原始文件均位于 `C:/Users/15428/AppData/Roaming/Reqable/capture/`。下表为文件前缀，响应通常加 `-res-extract-body.reqable`，请求体加 `-req_raw-body.reqable`。

| 编号 | 文件前缀 | 证据内容 |
|---|---|---|
| P1 | `1789653214857491-59-499` | 商品选配 HTML，SKU 与维度映射、摘要接口配置 |
| P2 | `1789653214857491-59-519` | 目标商品购买摘要，异步加购标记、隐藏表单字段 |
| P3 | `1789653214857491-59-527` | SEO 响应，目标商品 canonicalURL；不是加购成功凭据 |
| P4 | `1789653214857491-59-533` | 迷你购物袋响应，存在目标商品 |
| P5 | `1789653214857491-59-535` | 完整购物袋 HTML，商品行、数量、结账动作 |
| A1 | `1789653214857491-59-421` | 另一段附件页响应；不能冒充本次主商品实际加购请求 |
| B1 | `1789653766495492-449-1` | 购物袋结账请求体；响应指向 signIn |
| G1 | `1789653767482007-451-1` | 登录/访客页面，guestLogin 动作 |
| G2 | `1789653907216370-633-1` | JSON 跳转响应，指向 checkout/start |
| G3 | `1789653908798214-634-1` | JSON 跳转响应，指向 checkout/start |
| C1 | `1789653910441195-640-1` | JSON 跳转响应，指向 checkout/start；具体入口请求未确认 |
| C2 | `1789653910441195-640-3` | Fulfillment-init 页面，门店及下一步动作 |
| C3 | `1789653910441195-640-4` | 门店选择字段及响应 |
| C4 | `1789653910441195-640-6` | 自提提交字段；响应进入 PickupContact-init |
| C5 | `1789653910441195-640-8` | 联系人验证字段；响应要求验证 |
| C6 | `1789653910441195-640-9` | verificationToken 提交；响应 isVerified=true |
| C7 | `1789653910441195-640-10` | 联系人提交失败样本：姓氏非法字符 |
| C8 | `1789653910441195-640-11` | 后续联系人提交；响应进入 Billing-init |
| D1 | `1789654124899576-816-1` | 支付方式字段及响应 |
| D2 | `1789654127657704-822-1` | 继续结账字段；响应进入 Review |
| D3 | `1789654127657704-822-2` | JSON 跳转至 checkout/status；缺少实际提交请求头 |
| D4 | `1789654127657704-822-3` | 正在处理页面及 checkStatus 动作 |
| D5 | `1789654127657704-822-5` | JSON 跳转至 interstitial |
| D6 | `1789654127657704-822-6` | 订单结果、订单号、查询链接、支付入口 |

P5、C2、D2、D6 中的商品行标识对应同一商品，P5 的 `sku=MG714CH/A`、数量为 1。报告以 `<item-key>` 代替这次会话生成的实际商品行键。

## 3. 响应如何驱动下一次请求

### 3.1 页面模型与增量响应

购物袋和结账 HTML 中解析 `script#init_data` 的 JSON。异步 JSON 响应的模型位于 `body`。常见结构：

```text
meta.h                        当前模型的请求头元数据
meta.page.url / htmlUrl        当前阶段的模型地址 / HTML 页面地址
<模块>.d                      当前数据
<模块>.a.<动作>.url            下一动作的 URL
<模块>.b.<字段>                字段绑定、是否提交、事件
<模块>.m                      模块校验消息（本样本含 ERROR）
```

P5 结账动作存在 `submit: true, module: "^"`；支付选择动作存在 `module: "/checkout", validate: false`。这说明动作可能提交关联模块字段，不能认为 `_m` 指向的单个字段就是全部请求体。不要把 `.d` 的全部展示数据直接编码进表单。

部分响应只返回局部模型。例如 C6 只更新 verificationModule，并带有 `meta.u`。实现需要理解模型更新范围；不能把每次 `body` 当完整页面，也不能把旧模型字段无条件全部复用。完整的删除、替换与合并语义仍需前端协议或完整抓包核对。

### 3.2 会话与动态请求头

已由 checkStatus 实际 cURL 证实以下头与 D4 的 `meta.h` 对应：

```text
x-aos-model-page
modelVersion
syntax
x-aos-stk
```

这些字段取自当次页面/响应，而不是写死历史值。结账流程需要连续 Cookie 会话，并按响应的 Set-Cookie 更新；Cookie 的域和路径规则由 HTTP 客户端 CookieJar 处理。不能把一整段 Cookie 无差别发给所有主机。

`secure7.www.apple.com.cn` 是本次实际主机，不应假定永远为 secure7。相对动作 URL 根据产生该动作的响应 URL 解析；跨主机跳转按真实返回地址处理。

`x-aos-ui-fetch-call-1` 的生成规则、各 Cookie 是否必需，以及上述头在每一阶段的要求，尚未通过本样本完整确认。不要随意构造或宣称可省略。

### 3.3 两种跳转必须分别处理

- HTTP 3xx：按真实 HTTP 状态与 Location 处理，方法变化遵循相应状态码语义。
- JSON `head.status=302`：从 `head.data.url` 读取应用层跳转指令。HTTP 自动重定向不会自动处理它。

JSON 的 302 不能证明 HTTP 本身是 302；JSON 的 200 也不能证明业务操作成功。`head.status` 在样本中既有数字也有字符串，解析时应明确支持这两种已观察到的形式，并对其他格式报错。

## 4. 正向流程与字段映射

### 4.1 选配：业务配置映射为 SKU

页面入口样本：`/shop/buy-iphone/iphone-17`；目标商品链接为 `/shop/buy-iphone/iphone-17/mg714ch/a`。

P1 的 `productSelectionData.products[]` 给出以下映射：

```text
familyType=iphone17
dimensionColor=sage
dimensionCapacity=256gb
    → partNumber=MG714CH/A
```

字段来源为用户明确指定的机型、颜色、容量，再与当次商品数据匹配。必须唯一匹配；没有匹配、存在歧义或不可购买时停止，不选择近似商品。

P1 声明摘要地址：

```text
/shop/updateSummary?fae=true&node=home/shop_iphone/family/iphone_17&step=select
```

但该摘要请求的实际方法、完整维度参数与其他选项参数尚未从请求元数据确认。不要把 `dimensionColor`、`dimensionCapacity` 是产品数据字段直接等同于它们必然是此接口的 URL 参数。

P2 摘要响应的重要字段：

```text
body.response.summarySection.summary.isBuyable = true
body.response.summarySection.summary.disabled = false
body.response.summarySection.summary.productDimensions
body.response.summarySection.summary.buyNowButton
body.response.summarySection.summary.stepAddingToBagAsync = true
body.response.summarySection.summary.pageSubmitAfterAddToBagAjaxCall = false
```

### 4.2 加入购物袋：从购买摘要提取表单，但实际主商品端点仍待补齐

P2 的 `buyNowButton` 是 HTML，包含：

| 字段 | 本次值 | 来源 |
|---|---|---|
| `product` | `MG714CH/A` | 摘要中的有效隐藏字段，与所选 SKU 一致 |
| `purchaseOption` | `fullPrice` | 摘要隐藏字段 |
| `step` | `select` | 摘要隐藏字段 |
| `add-to-cart` | `add-to-cart` | 提交按钮名称和值；实际异步序列化方式待核对 |

同一表单另有 disabled 的空 `product` 输入框。不能错误地取第一个同名输入或提交 disabled 输入。

较早摘要（`59-407`）还包含 `acpart=none`，P2 没有该字段。因此不能把早期快照的可选字段强加到最终请求。

表单声明 `method=get, action=#`，但同时启用了异步加购，**不能据此构造 GET # 请求**。A1 附件页声明 `asyncAddToBagUrl=/shop/bag/add`，仅能作为候选线索，不能确认主商品使用相同接口或同样参数。

加购成功应由后续购物袋数据证明：P4 有目标商品，P5 有对应商品行、SKU 和数量。P3 的 SEO 响应只改变页面标题和链接，不表示加购成功。

### 4.3 购物袋列表与商品行标识

完整购物袋页面路径：`/shop/bag`。P5 中：

```text
init_data.shoppingCart.items.<item-key>.d.sku
init_data.shoppingCart.items.<item-key>.d.name
init_data.shoppingCart.items.<item-key>.itemQuantity.d.quantity
init_data.shoppingCart.items.<item-key>.itemQuantity.d.maxQuantity
init_data.shoppingCart.summary.d.total
```

根据 SKU 查到动态 `<item-key>`，再使用该行的动作地址。行键不是 SKU，不能自行生成，也不能沿用历史 UUID。

页面声明数量更新动作：

```text
/shop/bagx?_a=updateQuantity&_m=shoppingCart.items.<item-key>.itemQuantity
```

对应绑定字段：`shoppingCart.items.<item-key>.itemQuantity.quantity`。数量更新的实际方法及是否还提交其他字段未从本次请求元数据确认。

`/shop/bag/status` 可能用于导航栏购物袋状态，本报告不将其等同于完整购物袋列表。下单前应核对整袋商品、数量、总额与是否多出配件。

### 4.4 购物袋 → 结账入口

P5 动作路径：`shoppingCart.actions.a.checkout.url`：

```text
/shop/bagx/checkout_now?_a=checkout&_m=shoppingCart.actions
```

B1 已观察到的表单字段如下；完整 URL/方法仍需请求元数据核对：

```text
shoppingCart.recommendations.recommendedItem.part
shoppingCart.items.<item-key>.itemQuantity.quantity
shoppingCart.items.<item-key>.delivery.lineDeliveryOptions.address.provinceCityDistrictTabs.city
shoppingCart.items.<item-key>.delivery.lineDeliveryOptions.address.provinceCityDistrictTabs.state
shoppingCart.items.<item-key>.delivery.lineDeliveryOptions.address.provinceCityDistrictTabs.provinceCityDistrict
shoppingCart.items.<item-key>.delivery.lineDeliveryOptions.address.provinceCityDistrictTabs.countryCode
shoppingCart.items.<item-key>.delivery.lineDeliveryOptions.address.provinceCityDistrictTabs.district
shoppingCart.locationConsent.locationConsent
shoppingCart.summary.promoCode.promoCode
shoppingCart.actions.fcscounter
shoppingCart.actions.fcsdata
```

数量来自已确认购物袋行；省市区来自当前地址选择状态和用户选择；其余字段按当前页面绑定及实际提交契约处理。观察到某字段存在不代表它独立必填，也不代表可以省略。

点击结账事件先执行 `a.updateFCS`，再执行 `a.checkout`。P5 中 updateFCS 把 `d.fcs1` 赋给 `d.fcsdata`、`d.fcs2` 赋给 `d.fcscounter`，再清空前两项。本次 B1 的两个提交字段为空；这不证明其他会话也可以固定为空。

B1 响应指向带动态 `ssi` 的 signIn 地址。下一请求使用返回的完整地址，不能自己编码或拼接历史 `ssi`。

### 4.5 访客入口 → Checkout 初始化

G1 的 `init_data.signIn.guestLogin.a.guestLogin.url` 声明：

```text
/shop/signInx?ssi=<当次动态值>&up=true&_a=guestLogin&_m=signIn.guestLogin
```

动作有 `submit=true, module=^`。实际方法与完整请求体未确认。G2/G3/C1 存在跳转至 `/shop/checkout/start` 的响应，但缺少请求元数据，不能断言三个响应都是同一 guestLogin 的固定必要步骤。

初始化后的 C2 明确进入 `Fulfillment-init`。实际跳转 URL 可能包含动态查询参数；应完整沿用响应，不只截取 `/shop/checkout/start` 路径。

### 4.6 选择门店与自提方式

以下简写仅为报告方便；发送时展开为完整字段名：

```text
F = checkout.fulfillment
L = checkout.fulfillment.pickupTab.pickup.storeLocator
Q = checkout.fulfillment.pickupTab.pickup.storeLocator.address.stateCitySelectorForCheckout
```

门店候选来自 `L.searchResults.d.retailStores[]`，包含 `storeId`、`storeName`、`storeDisabled`、`availability`、`pickupMessages` 等。按用户指定门店匹配并检查可用性；不能只拿到 ID 就假定有货。

页面声明选择动作：

```text
/shop/checkoutx/fulfillment?_a=select&_m=checkout.fulfillment.pickupTab.pickup.storeLocator
```

C3 请求体字段：`L.showAllStores`、`L.selectStore`、`L.searchInput`，以及 `Q.city/state/provinceCityDistrict/countryCode/district`。样本选择 `R448`，它来自服务端候选门店，而不是自行编造门店编号。

继续到联系人动作：

```text
/shop/checkoutx/fulfillment?_a=continueFromFulfillmentToPickupContact&_m=checkout.fulfillment
```

C4 请求体包含上述门店/地址字段，另外包含 `F.fulfillmentOptions.selectFulfillmentLocation=RETAIL`。响应进入 `PickupContact-init`，据此确认自提步骤完成。

这两步属于页面动作与请求体关联，实际 HTTP 方法仍待确认。配送到家不能仅将 RETAIL 换为猜测值；必须另查配送分支模型及请求。

### 4.7 联系人验证：不是简单复制一个 Cookie

简写：

```text
P = checkout.pickupContact
C = checkout.pickupContact.selfPickupContact.selfContact.address
V = checkout.pickupContact.selfPickupContact.selfContact.address.verificationModule
```

页面声明发起验证：

```text
/shop/checkoutx?_a=contactVerify&_m=checkout.pickupContact.selfPickupContact.selfContact.address
```

C5 请求体包括 `C.emailAddress`、`C.fullDaytimePhone`、`C.lastName`、`C.firstName`、`V.verificationToken`，最后一项当时为空。联系人字段来自用户真实输入，不是上一接口自动生成。

C5 响应 `V.d.authRequired=true`、`V.d.isVerified=false`，并提供验证组件 options（包括上下文及动态凭据）。它们属于当次验证会话。

完成组件验证后，页面声明提交结果：

```text
/shop/checkoutx?_a=submitVerificationToken&_m=checkout.pickupContact.selfPickupContact.selfContact.address.verificationModule
```

C6 请求体只有 `V.verificationToken`。实际值是长字符串，不是纯数字验证码，不能把短信验证码直接填入这个字段。其完整生成/取得流程尚未定位；也没有证据证明它等于验证 options 中的 token。

C6 响应变为 `isVerified=true, authRequired=false`。只有确认服务端接受验证结果，才可继续联系人提交。尚未补齐验证组件网络链路前，不能宣称可无人值守自动完成这一关。

### 4.8 提交联系人与发票 → Billing

页面声明动作：

```text
/shop/checkoutx?_a=continueFromPickupContactToBilling&_m=checkout.pickupContact
```

C7 请求体观察到：

```text
C.emailAddress
C.fullDaytimePhone
C.lastName
C.firstName
V.verificationToken
P.selfPickupContact.nationalIdSelf.nationalIdSelf
P.eFapiaoSelector.selectFapiao
P.eFapiaoSelector.ePersonalFapiao.invoiceHeader
```

本次发票枚举为 `e_personal_fdf`。实名字段是否在其他场景必填，不能由单个失败请求推出。

**C7 是失败样本，不能作为成功请求模板。** 它的业务状态为 200，但响应停留 PickupContact，并有：

```text
checkout.pickupContact.selfPickupContact.selfContact.address.m[]
  key = b.lastName
  level = ERROR
  text = 请只输入字母数字字符。
```

C8 后续请求体仅有 `C.lastName`、`C.firstName`、空的 `V.verificationToken`、发票类型和空抬头，响应进入 `Billing-init`。这表明本次会话前面已保存了其他信息，**不代表新会话只需要这五个字段，也不代表可以跳过验证**。

### 4.9 支付方式 → Review

页面声明选择动作：

```text
/shop/checkoutx/billing?_a=selectBillingOptionAction&_m=checkout.billing.billingOptions
```

D1 请求体：

```text
checkout.billing.billingOptions.selectBillingOption = ALIPAY
checkout.billing.billingOptions.bankLookUp.selectBank = 空
checkout.locationConsent.locationConsent = false
```

支付方式编码应从当次 `checkout.billing.billingOptions.d.options` 及展示分组中核对可选值。不能据此假定所有地区/商品都支持 ALIPAY。

继续动作：

```text
/shop/checkoutx/billing?_a=continueFromBillingToReview&_m=checkout.billing
```

D2 请求体为支付方式和空 selectBank；响应 `body.meta.page` 进入 Review。复核 `checkout.review` 的商品、数量、金额、自提门店、联系人、发票和支付方式；任何与任务配置不一致的内容都应停止。

### 4.10 Review → 提交订单

D2 声明两个动作：

```text
/shop/checkoutx/review?_a=continueFromReviewToProcess&_m=checkout.review
/shop/checkoutx/review?_a=continueFromReviewToProcess&_m=checkout.review.placeOrder
```

两者均有 `submit=true`。D3 响应指向 `/shop/checkout/status`，与后续处理链对应，但目前没有实际提交请求元数据，不能确认本次选中了哪一个 `_m`、实际方法或是否为空请求体。

未发现独立请求体文件不等于已证明 Content-Length 为 0。这里不编造 `termsAccepted`、`orderId` 等字段。

提交超时或响应丢失时，不自动再次提交订单；应先查已有处理结果，无法确认时停止并报告，避免重复创单。

### 4.11 处理状态 → 返回订单号（实际请求已确认）

```text
GET /shop/checkout/status
```

从 D4 的 `init_data.meta.h` 读取当前模型头，从 `init_data.spinner.a.checkStatus.url` 读取状态动作。页面 load 事件声明延迟 500ms；这只是首次触发延迟，不能推出固定轮询周期。

```text
POST /shop/checkoutx/statusX?_a=checkStatus&_m=spinner
Content-Type: application/x-www-form-urlencoded
请求体：空
```

会话 Cookie 持续使用；模型头按 D4 取得。对话中的实际请求还包含 `X-Requested-With: Fetch`、Origin、Referer、浏览器上下文头等。最小必需头集合未经过删减验证。

D5 响应：

```json
{"head":{"status":302,"data":{"url":"/shop/checkout/interstitial"}},"body":{}}
```

随后实际请求：

```text
GET /shop/checkout/interstitial
```

解析 D6 的 `script#init_data`，提取：

```text
thankYouInterstitial.d.orderNumber
thankYouInterstitial.d.orderStatusUrl
thankYouInterstitial.d.paymentType
thankYouInterstitial.d.paymentExpiryData
```

本样本已有订单号，同时仍显示支付宝“现在支付”和 30 分钟支付期限。因此可以把业务目标定义为“订单已创建并取得订单号”，不能标记为“已支付”。支付链接不属于此目标的下一步。

## 5. 自动化输入设计：业务参数与会话状态分开

以下是建议的应用配置结构，**不是 Apple 的请求 JSON**，字段值由用户明确提供；不在此填入个人数据或凭据。

| 类型 | 输入/状态 | 获取方式 |
|---|---|---|
| 用户输入 | 机型、颜色、容量、数量 | 用户指定，匹配当次商品数据 |
| 用户输入 | 自提/配送、门店或地址 | 用户指定；仅自提分支已分析 |
| 用户输入 | 联系人、联系电话、邮箱、适用实名信息 | 用户输入，按当前页面契约验证 |
| 用户输入 | 发票类型及相应信息 | 用户选择，再映射当次页面枚举 |
| 用户输入 | 支付方式 | 用户选择，再核对当次可选编码 |
| 运行时状态 | SKU、购买摘要隐藏字段 | 商品页面与摘要响应 |
| 运行时状态 | 商品行键、数量限制、购物袋金额 | 当前购物袋响应 |
| 运行时状态 | 动作 URL、模型头、阶段 | 当前模型及后续更新响应 |
| 运行时状态 | Cookie、跳转中的动态参数 | HTTP 响应；按域/路径维护 |
| 运行时状态 | 验证组件上下文与验证结果令牌 | 当次验证流程，来源链仍待补齐 |
| 最终输出 | 订单号、订单查询链接、待支付状态 | interstitial 响应 |

提交字段遵循已确认的 form-urlencoded 契约时，用标准编码器处理完整字段名和值，不能手工拼接；空字符串和缺失字段需要区分。页面数据、请求头、隐藏字段和用户输入不能混为一个可全部复制的字典。

## 6. 完成可执行实现前仍需补齐的证据

| 缺口 | 当前已知 | 尚缺内容 |
|---|---|---|
| 摘要更新 | 配置中有 updateSummary URL；有目标摘要响应 | 实际请求方法、完整 URL 参数与请求头 |
| 主商品加购 | 购买摘要字段、异步标记、后续购物袋成功状态 | 真正主商品加购请求的 URL、方法、参数与跳转 |
| 访客与初始化 | guestLogin 动作及 checkout/start 跳转响应 | 实际请求体、方法、完整重定向/Set-Cookie 链 |
| 联系人验证 | contactVerify → verificationToken → isVerified | 组件获取验证结果令牌的请求及响应关联 |
| 其他业务动作 | 页面动作 URL、同记录请求/响应正文 | 实际方法、请求头、HTTP 状态等元数据 |
| 最终提交 | 两个 continueFromReviewToProcess 动作、成功后续状态 | 实际使用的 `_m`、方法、请求体及请求头 |

补证最直接的方式是从 Reqable 导出覆盖“选配到 interstitial”的 HTTP 记录为带请求/响应正文的 HAR。目标是补齐元数据，不需要重新创建订单。日志范围应包含 Apple 商城与该订单使用的验证组件请求；无需导出无关流量。

本次只读分析已交叉核对 SKU、商品行、阶段转换、联系人错误、验证结果和订单结果；没有做线上重放，不能宣称所有接口可直接独立调用或整个流程已具备无人值守能力。
