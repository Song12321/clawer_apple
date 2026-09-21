# 串行下单 v2

填写 `config.py` 的联系人、证件后四位、产品和自提配置，然后在仓库根目录运行：

```powershell
venv/Scripts/python.exe v2/main.py
```

运行会加购并在核验通过后提交待支付订单，最后打印并返回订单号，不执行付款。访客隐私弹窗按用户授权自动勾选并继续；浏览器仅负责初始化和生成含 deviceID 的访客表单，表单拦截取消后由 requests 提交。短信初始化、发送及校验由 `sms.py` 使用独立 requests 会话执行。看到“短信已发送到配置的手机号”后，控制台会显示“请输入短信验证码（6 位数字）”，输入后回车提交；输入内容可见。未填写配置时在联网前停止；无自动重试或失败兜底。

仅实现本次 HAR 的单件、自提、个人电子发票、支付宝分支。`order.py` 复用上一版的加购、HTTP 请求和结果查询函数；上一版仅增加 `browser_session(..., include_page=True)`，供 v2 获取当前页面，原入口行为不变。

离线测试：`venv/Scripts/python.exe -m unittest discover -s v2 -p test_order.py`。测试从用户提供的本地 HAR 读取真实响应，模拟访客表单及验证组件，不连接网站。覆盖串行执行、关键提交字段和值、POST+args 初始化、支付宝直接进入 Review、金额不一致禁止创单。HAR 路径集中在测试顶部。该测试没有证明浏览器交互或线上串行执行成功。

原浏览器短信版本已由用户确认取得订单号。纯 requests 短信版本已实测完成新会话 contactVerify 和身份初始化，测试止于短信发送前；真实短信发送、验证码校验及改动后的整链路尚未验收。运行所有离线测试：`venv/Scripts/python.exe -m unittest discover -s v2 -p "test_*.py"`。包含身份会话 ID 更新、验证码拒绝及缺少令牌的测试。

短信契约依据原 HAR 的 344、354、364、365、487：344 的 serviceKey/options 提供身份头；redirect_uri 取结账页 origin；364 响应的 X-Apple-ID-Session-Id 用于发送短信，365 响应更新该头用于校验；487 响应的 X-Apple-Verification-Token 交给原有联系人提交链路。手机号取当前配置，验证码取本次终端输入，不使用历史凭据。初始化偶发 HTTP 541 仍未根治。
