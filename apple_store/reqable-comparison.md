# 成功加购与新会话对比

## 定位 CDP 隐身窗口会话交接缺陷

普通 Chrome 进程以隐身模式启动，再通过 connect_over_cdp 附加时，实测 browser.contexts[0].cookies() 返回空列表，但页面实际发送 14 项 Cookie。页面级 Network.getCookies 可读取这 14 项。此前该路径中“同步 Cookie 后 Python 541”实际是发送了空 CookieJar，不能归因于 Python 客户端被拒绝或 Cookie 不可转移。这不能解释较早 Playwright 新上下文本身返回 541 的问题。

同一成功会话受控对照：浏览器 200；原始 Cookie 的 requests 直连 200；旧上下文 CookieJar 同步 541（缺失全部 14 项）；原始 Cookie 经 Reqable 200；原始 Cookie 再次直连 200；浏览器再次 200。该样本排除了代理路径作为必要失败因素。

修复：新增 read_page_cookies，从实际页面的 CDP Network.getCookies 读取；copy_browser_cookies 支持 CDP 未声明 SameSite 的 Cookie，并拒绝空的商城 CookieJar。browser_session 使用页面 Cookie 来源。

修复后的在线验证：浏览器履约 200；同步 14 项 Cookie，与原始请求逐项比较值无差异；requests 履约 HTTP 200、业务 200；浏览器再次 200。没有发送加购请求。普通 Chrome 启动器仍为诊断实验，主脚本仍使用 Playwright launch，未宣称端到端 requests 加购已完成。

## 自动浏览器会话初始化

主脚本已改为由 Playwright 启动有界面 Chrome，SESSION_CONFIGS 的每组配置创建独立 browser context 和 requests.Session。官网原始 verify.js 自动执行，监听 shldDone 并检查 Cookie，保留浏览器的 Cookie 域、路径、有效期等属性。不再读取剪贴板，不保存会话凭据。当前入口止于购物袋检查，不进入结账；默认只运行 CONFIG 一组，遇到失败停止后续组。

在线验证：新浏览器的 GET /q、POST /q 均 200，脚本报告 shld-result，Cookie 同步成功；Python 商品摘要成功，但加购仍 541。额外 beacon 请求被观察到更新 shld_bt_ck 与 as_atb；取消重复 beacon、改为使用浏览器当前令牌后，加购仍 541。Cookie 出现或验证脚本报告完成不能作为可加购的充分证据。没有实现独立加购成功，不能标为已完成。没有为此伪造浏览器环境或验证结果。

## 更新：动态会话接入与再次验证

`apple_order.py` 已接入 `import_browser_session(session)`：运行前从 Reqable 复制成功加购记录的原始 cURL；仅在内存中导入浏览器请求头和 Cookie，校验 cURL 中 atbtoken 与 as_atb 一致。选配和摘要仍使用项目 CONFIG，并从当次响应构造加购参数，不使用历史商品参数。

实测 beacon 返回 as_atb 的 Domain 为 `.www.apple.com.cn`，而 dssid2、dssf、as_dc、shld_bt_m 为 `.apple.com.cn`。已修正 as_atb 导入域，避免当次响应更新后出现两个同名令牌。其余导入 Cookie 采用商城父域；cURL 本身不包含完整 Cookie 作用域元数据，不能据此证明所有原始作用域均已恢复。

此次商品页、购物袋、updateSummary、beacon 均返回 200；动态加购返回 541。另一次不调用 beacon 的隔离实验也返回 541。对同款 MG6Y4CH/A 核对发现动态查询字段、值、顺序与原始请求完全一致，商品页和摘要后 Cookie 值未变。

随后再次运行此前成功的 `replay_856.py`，原样重放也返回 541。因此当前历史请求已不能复现此前成功，无法使用该样本完成动态加购的成功验收；确切服务端原因尚不明确，不能直接断言令牌过期。未继续重试，未创建订单。购物袋读取到已有多款商品，原有单商品结账检查保持不变。

## 更新：Python 原样重放成功

2026-09-18，在用户明确要求原样重放后，从 Reqable 复制 856 cURL，在内存中解析完整请求头及 URL，使用 requests 经本机 Reqable 代理发送一次 GET。保留原始 Cookie 和 atbtoken，不重新初始化会话，不跟随跳转。实际返回 HTTP 303，Location 路径为 `/shop/buy-iphone/iphone-17`，参数 product=mg6y4ch/a、step=attach。未继续进入购物袋或结账，未创建订单。

requests 使用 HTTP/1.1，此结果说明 HTTP/2 并非该次成功的必要条件。此前新会话的 HTTP 541 不能代表原样重放失败。成功会话可以由 Python 重放，但尚未证明全新会话自动初始化可以成功，也未单独确定哪个 Cookie 必需。独立诊断脚本 `replay_856.py` 从剪贴板读取 Reqable 原始 cURL，不保存凭据。每次运行会再发一次加购请求。

2026-09-18，直接操作 Reqable 的调试列表，筛选 URL 并读取成功记录 752 的 cURL。没有保存或复用其中的 Cookie 值、令牌。界面中的“选购+加入购物袋”是空 API 文件夹，不是抓包会话。

## 已确认的成功请求

- 方法：GET。
- 路径：`/shop/buy-iphone/iphone-17/mg714ch/a`。
- HTTP 状态：303。
- 参数：`product=MG714CH/A`、`purchaseOption=fullPrice`、`step=select`、`acpart=none`、`igt=true`、`add-to-cart=add-to-cart`、当次动态 `atbtoken`。
- Referer：同一 SKU 商品页。
- User-Agent：Windows Chrome 152。
- 导航头包含 Accept、Accept-Language、sec-ch-ua 系列、Sec-Fetch 系列、Upgrade-Insecure-Requests。
- 列表另有记录 762：系列购买入口返回 HTTP 200；与此前读取到的 attach 页面一致，但尚未读取 752 的 Location 来证明二者直接跳转关联。

## 已执行的差异验证

1. 全新 requests.Session，显式经过 Reqable，使用成功记录中的非敏感浏览器请求头；不复制历史 Cookie，重新访问商品页、摘要和加购 beacon。结果：加购 HTTP 541。
2. 全新有界面 Chrome，会话显式经过 Reqable；选择不折抵和不加 AppleCare，等待对应摘要响应及 acpart=none 隐藏字段出现，再点击加购。实际请求包含上述全部参数。结果：加购 HTTP 541。

因此不能将问题归结为只缺普通请求头，或仅因浏览器在 AppleCare 摘要更新前提交。

成功记录 Cookie 名称包含 `shld_bt_m`、`shld_bt_ck`、`as_sfa`、`as_loc`、`rtsid`、`as_atb` 等；新 Python 会话在摘要阶段仅有 `as_dc`、`as_pcts`、`dssf`、`dssid2`、`geo`，随后由 beacon 初始化 as_atb。集合差异不能证明某个 Cookie 单独必需，不能据此编造或固定历史值。

## 第二次成功记录 856 的对比

直接从 Reqable 复制 856 和 752 的 cURL，在内存中比较；未保存凭据值。856 商品为 MG6Y4CH/A，界面确认 HTTP 303。

- 两次查询字段集合一致；值变化仅 product、atbtoken。路径和 Referer 随 SKU 变化。
- 请求头值变化仅 referer、cookie；其余捕获请求头一致。
- Cookie 名称集合一致；值变化仅 s_fid、s_vi、as_atb、mbox。
- dssid2 相同，因此这两个样本不是两次独立的新会话成功。
- 两次 atbtoken 均精确等于各自 as_atb 的最后一个竖线分段，支持当前代码的动态提取规则。
- 从 752 响应原始头确认 Location 为 `https://www.apple.com.cn/shop/buy-iphone/iphone-17?product=mg714ch/a&step=attach`。856 的完整 Location 尚未可靠读取，不将剪贴板残留的 752 响应当作 856 证据。

本次没有发现需要改动的加购业务字段，也未重放成功会话的加购请求。现有 HTTP 541 阻塞仍未解决；下一项需要验证的是成功会话的前序初始化与新会话之间的差异，不能仅凭 Cookie 集合推断必要性。

## 仍未证明

- HTTP 541 的确切服务端原因。
- 成功浏览器会话的前序初始化与新会话的关键差异。
- 纯 requests 能否在不依赖浏览器当前状态的情况下完成加购。
- 成功加购后整袋核对与最终创单。

此次未解决 541，未创建订单。不要用新会话失败的结果否定正常浏览器的成功，也不要把历史成功响应当作本次自动化成功。
