# Apple 中国官网自动化接口

Python 3.11+ / FastAPI / Playwright。提供本机 HTTP 接口，通过独立浏览器会话操作 Apple 中国商店，不依赖猜测的内部接口、固定 Cookie 或 CSRF token。Python 实现已替换原 Node.js 代码。

实现范围：指定商品 URL 和规格 → 加入购物袋 → 调整数量 → 进入结账或登录页面。
**目前不包含填写收货/支付资料、提交订单与付款。** 登录、验证码和后续结账可以在服务打开的浏览器中手动完成。会话保留到显式关闭或服务退出。

## 启动

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
$env:APPLE_API_TOKEN = 'replace-with-a-long-random-secret'
./.venv/Scripts/python.exe -m apple_store.server
```

默认使用本机 Microsoft Edge，监听 `127.0.0.1:3000`。若未设置 token，启动时生成临时 token。不要把服务直接暴露到公网。
没有 Edge 时运行 `./.venv/Scripts/python.exe -m playwright install chromium`，并设置 `$env:BROWSER_CHANNEL = 'chromium'`。也可使用 `chrome`。本工作区已经创建 `.venv` 并安装依赖，可直接使用其 Python。

Linux/macOS 使用 `.venv/bin/python` 替代上述路径。服务使用单进程，不要添加多 worker 或自动 reload 参数。

## Python 调用

编辑 `examples/product.json` 为实际商品 URL、完整购物袋标题和规格选项，然后在另一个终端设置相同的 `APPLE_API_TOKEN` 并执行：

```powershell
./.venv/Scripts/python.exe examples/purchase.py examples/product.json --quantity 1
```

该示例会执行实际加购并进入结账页面，结束后保留浏览器供你继续操作。不要将示例配置当作已确认的购买目标。
实现位于 `apple_store/store.py`（浏览器流程）、`apple_store/server.py`（HTTP 接口）、`apple_store/models.py`（参数校验和幂等）。

## 接口

所有接口要求 `Authorization: Bearer <token>`。商品配置、加购、数量修改和结账要求 `Idempotency-Key`，同一次操作重试必须复用相同值；新操作使用新值。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 服务状态 |
| POST | `/sessions` | 创建独立会话，body 为 `{"headless":false}` |
| GET | `/sessions/:id` | 当前 URL、阶段及页面可访问性快照 |
| PUT | `/sessions/:id/product` | 打开商品并配置规格 |
| POST | `/sessions/:id/bag/items` | 加购一次，并核对购物袋商品 |
| GET | `/sessions/:id/bag` | 打开购物袋、核对不确定的加购结果 |
| PATCH | `/sessions/:id/bag/item` | 设置商品绝对数量，如 `{"quantity":2}` |
| POST | `/sessions/:id/checkout` | 进入结账页面，可能返回 `login_required` |
| DELETE | `/sessions/:id` | 关闭会话浏览器 |

每个会话只操作一种商品。数量通过购物袋修改，不循环点击加购。一个会话内全部请求串行执行。幂等缓存仅在当前服务进程内有效；重启后不能复用旧会话。

## 调用示例（PowerShell）

用你的目标商品替换以下链接和名称；示例商品只用于展示参数格式，不代表已为你选购。

```powershell
$base = 'http://127.0.0.1:3000'
$headers = @{ Authorization = "Bearer $env:APPLE_API_TOKEN" }
$s = Invoke-RestMethod "$base/sessions" -Method Post -Headers $headers -ContentType 'application/json' -Body '{"headless":false}'
$id = $s.id

$product = @{
  url = 'https://www.apple.com.cn/shop/buy-airpods/airpods-5'
  expectedBagName = 'AirPods 5'
  choices = @(
    @{ role = 'radio'; name = 'AirPods 5 RMB 999' },
    @{ role = 'radio'; name = '不加镌刻' }
  )
} | ConvertTo-Json -Depth 6
$headers['Idempotency-Key'] = 'configure-1'
Invoke-RestMethod "$base/sessions/$id/product" -Method Put -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($product))

$headers['Idempotency-Key'] = 'add-1'
Invoke-RestMethod "$base/sessions/$id/bag/items" -Method Post -Headers $headers

$headers['Idempotency-Key'] = 'quantity-1'
Invoke-RestMethod "$base/sessions/$id/bag/item" -Method Patch -Headers $headers -ContentType 'application/json' -Body '{"quantity":1}'

$headers['Idempotency-Key'] = 'checkout-1'
Invoke-RestMethod "$base/sessions/$id/checkout" -Method Post -Headers $headers

# 完成后关闭浏览器
# Invoke-RestMethod "$base/sessions/$id" -Method Delete -Headers $headers
```

`choices` 按顺序执行，name 必须是页面中控件的完整可访问名称（空白会由 Playwright 规范化）。支持 radio、combobox（需 value，按选项显示文本匹配）、button（仅“继续 / 选择 / 选取”）。不同产品规格流程不同，不自动选择颜色、容量、换购、AppleCare 或付费附加项。

遇到 `CONFIGURATION_REQUIRED` 时，调用会话查询读取页面选项，补全 choices 后使用新的幂等键重新配置。`expectedBagName` 是购物袋商品标题的完整名称，用于阻止仅凭按钮点击成功就认定加购成功。

## 状态和恢复

正常状态：`new → product → configured → bag → checkout / login_required`。

加购点击前即设置 `add_unknown`，只有购物袋确实出现指定商品后才变为 `bag`。遇到 `ADD_RESULT_UNKNOWN`，使用购物袋查询核对；不要以新幂等键反复加购。页面改版或验证提示会使流程停止，不会自动猜测下一步。

当前购物袋适配器默认使用 `.rs-bag-item`、完整商品标题及行内数量下拉框；结账按钮匹配“结账 / 立即结账”。需要适配官网变化时修改 `apple_store/store.py` 的类常量与对应方法。快照可能包含结账个人信息，服务不将其写入日志或磁盘。数量修改结果不确定时返回 `quantity_unknown`，可查询购物袋恢复。

## 验证与限制

```powershell
./.venv/Scripts/python.exe -m compileall -q apple_store examples tests
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

测试包括 URL 校验、HTTP 鉴权、并发与幂等、真实浏览器中的本地模拟商品配置/加购/数量/结账流程，以及加购结果不确定、登录跳转分支；模拟测试拦截所有网络请求，不会产生官网订单。

2026-09-17 已通过浏览器检查官网商品页的型号、镌刻与加购按钮。尚未指定实际目标商品，因此**官网购物袋与结账尚未完成端到端验证**；本地测试通过不代表已成功下单。没有实现 Apple 私有 HTTP 下单协议。
