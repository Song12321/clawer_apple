"""运行前填写：账号级配置写在 ACCOUNTS，运行级开关写在 RUN。

RUN 是全局策略；ACCOUNTS 里每个账号一份商品、门店、联系人、资料目录与调试端口。
一个账号必须对应一个独立的浏览器资料目录和一个独立的调试端口。
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

RUN = {
    # 结账入口被判为访客会话时：False 停在原地等你登录（推荐），True 才走访客表单+短信验证。
    "允许访客结账": False,
    # 是否让 Python 请求经过 Reqable 抓包代理。实测该代理会间歇性卡住请求，默认直连保稳定；
    # 需要抓包分析时改成 True（浏览器始终直连，不受此开关影响）。
    "使用抓包代理": False,
    # 账号之间的串行间隔（秒）：同一 IP 连续下单，留出间隔降低风控压力。
    "账号间隔秒": 30,
    # 每个账号的运行结果追加写入该文件，一行一条 JSON。
    "结果文件": str(BASE_DIR / "results.jsonl"),
}

ACCOUNTS = [
    {
        "账号": "a",
        # 沿用 v2/chrome-profile：这是已有登录态所在目录，不要与其它账号共用。
        "资料目录": str(BASE_DIR / "chrome-profile"),
        "调试端口": 9333,
        # iPhone 18 Pro Max 256GB 冰川蓝色（familyType/颜色/容量取自官网选配数据）
        # "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjy94ch/a",
        # "机型": "iphone18promax", "颜色": "glacier", "容量": "256gb", "数量": 1,
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-17/mg714ch/a",
        "机型": "iphone17",
        "颜色": "sage",
        "容量": "256gb",
        "数量": 1,
        "自提门店": "R448", "自提门店名称": "Apple 王府井", "搜索地区": "北京 北京 朝阳区",
        "省": "北京", "市": "北京", "区": "朝阳区",
        "姓": "xing", "名": "ming", "手机号": "17862852279", "邮箱": "17862852279@163.com",
        "证件后四位": "1374", "发票类型": "e_personal_fdf", "支付方式": "ALIPAY",
    },
    # 新增账号：复制上面一份，至少改四项——账号、资料目录、调试端口、商品与门店配置。
    # {"账号": "b", "资料目录": str(BASE_DIR / "profiles" / "b"), "调试端口": 9334, ...},
]
