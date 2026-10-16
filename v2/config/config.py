"""运行前填写：账号级配置写在 ACCOUNTS，运行级开关写在 RUN。

RUN 是全局策略；ACCOUNTS 里每个账号一份商品、门店、联系人、资料目录与调试端口。
一个账号必须对应一个独立的浏览器资料目录和一个独立的调试端口。
"""
from pathlib import Path

from v2.config.iphone18_all_configs import IPHONE_18_CONFIGS

BASE_DIR = Path(__file__).resolve().parent

RUN = {
    # 仅商品页入口持续等待；轮转为请求前检查，0 表示入口不轮转。
    "入口重试间隔秒": 2,
    "入口轮转间隔秒": 5,
    # session.py 和 main.py 共用："all" 表示全部；指定账号用列表，如 ["a138"]。
    "参与账号": ["a178"],
    # 结账入口被判为访客会话时：False 停在原地等你登录（推荐），True 才走访客表单+短信验证。
    "允许访客结账": False,
    # Python 和 Chrome 共用毛熊 VPN 的 HTTP 代理；启动前先打开代理软件。
    "代理地址": "http://127.0.0.1:17890",
    # 与上述显式代理互斥，当前保持 False。
    "使用抓包代理": False,
    # 各账号并行；确认缺货后等待这些秒数再查询，不叠加同一账号的请求。
    "缺货轮询间隔秒": 45,#两个账号相加70 保存，单账号同！ 25安全！
    "选店网络重试次数": 15,  # 首次失败后最多额外尝试次数，0 表示不重试
    "选店网络重试间隔秒": 15,
    # 每个账号库存等待期间结账过期或选店 541 的累计恢复次数；0 表示不恢复，不重试创单。
    "结账恢复次数": 15,
    # 每个账号的运行结果追加写入该文件，一行一条 JSON。
    "结果文件": str(BASE_DIR / "results.jsonl"),
}

# 抢购 iPhone Duo：将目标账号的 **IPHONE_18_CONFIGS[...] 一行替换为例如：
# **IPHONE_18_CONFIGS["iPhone Duo 256GB 星光白色"],
# Duo 全部 8 种颜色/容量组合见 iphone18_all_configs.py；按实际购买意愿选择。
ACCOUNTS = [
    {
        "账号": "a178",
        # 沿用 v2/chrome-profile：这是已有登录态所在目录，不要与其它账号共用。
        "资料目录": str(BASE_DIR / "chrome-profile-a178-401"),
        "调试端口": 9401,
        # iPhone 18 Pro Max 256GB 冰川蓝色（familyType/颜色/容量取自官网选配数据）
        **IPHONE_18_CONFIGS["iPhone Duo 256GB 星光白色"],
        "自提门店": "R575", "自提门店名称": "Apple 武汉", "搜索地区": "湖北 武汉 江汉区",
        "省": "湖北", "市": "武汉", "区": "江汉区",
        # "自提门店": "R448", "自提门店名称": "Apple 王府井", "搜索地区": "北京 北京 朝阳区",
        # "省": "北京", "市": "北京", "区": "朝阳区",
        "姓": "梁", "名": "青松", "手机号": "17862852279", "邮箱": "17862852279@163.com",
        "证件后四位": "669X", "发票类型": "e_personal_fdf", "支付方式": "ALIPAY",
    },
    # 新增账号：复制上面一份，至少改四项——账号、资料目录、调试端口、商品与门店配置。
    # {"账号": "b", "资料目录": str(BASE_DIR / "profiles" / "b"), "调试端口": 9334, ...},

    {
        "账号": "customer-vx-Navy-new9555",
        # 沿用 v2/chrome-profile：这是已有登录态所在目录，不要与其它账号共用。
        "资料目录": str(BASE_DIR / "chrome-profile-customer-vx-Navy-fresh9559"),
        "调试端口": 9559,
        # iPhone 18 Pro Max 256GB 冰川蓝色（familyType/颜色/容量取自官网选配数据）
        **IPHONE_18_CONFIGS["iPhone 18 Pro Max 512GB 银色"],
        "自提门店": "R575", "自提门店名称": "Apple 武汉", "搜索地区": "湖北 武汉 江汉区",
        "省": "湖北", "市": "武汉", "区": "江汉区",
        # "自提门店": "R448", "自提门店名称": "Apple 王府井", "搜索地区": "北京 北京 朝阳区",
        # "省": "北京", "市": "北京", "区": "朝阳区",
        "姓": "Navy", "名": "Navy", "手机号": "15166806353", "邮箱": "1119446670@qq.com",
        "证件后四位": "2935", "发票类型": "e_personal_fdf", "支付方式": "ALIPAY",
    },
    {
        "账号": "test",
        # 沿用 v2/chrome-profile：这是已有登录态所在目录，不要与其它账号共用。
        "资料目录": str(BASE_DIR / "chrome-profile-customer-vx-Navy-fresh9558"),
        "调试端口": 9558,
        # iPhone 18 Pro Max 256GB 冰川蓝色（familyType/颜色/容量取自官网选配数据）
        **IPHONE_18_CONFIGS["iPhone 18 Pro Max 256GB 银色"],
        "自提门店": "R575", "自提门店名称": "Apple 武汉", "搜索地区": "湖北 武汉 江汉区",
        "省": "湖北", "市": "武汉", "区": "江汉区",
        # "自提门店": "R448", "自提门店名称": "Apple 王府井", "搜索地区": "北京 北京 朝阳区",
        # "省": "北京", "市": "北京", "区": "朝阳区",
        "姓": "sa", "名": "asd", "手机号": "15176806353", "邮箱": "70@qq.com",
        "证件后四位": "7471", "发票类型": "e_personal_fdf", "支付方式": "ALIPAY",
    },
]


def selected_accounts():
    """两个入口共用同一份参与账号配置；非法选择在启动前报错。"""
    names = [account["账号"] for account in ACCOUNTS]
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("ACCOUNTS 不能为空，账号名必须是非空字符串")
    if len(names) != len(set(names)):
        raise ValueError("ACCOUNTS 中账号名不能重复")
    selected = RUN["参与账号"]
    if selected == "all":
        return ACCOUNTS
    if not isinstance(selected, list) or not selected or any(
            not isinstance(name, str) or not name.strip() for name in selected):
        raise ValueError('RUN[参与账号] 必须是 "all" 或非空账号名列表，如 ["a138"]')
    if len(selected) != len(set(selected)):
        raise ValueError("RUN[参与账号] 不能重复")
    unknown = [name for name in selected if name not in names]
    if unknown:
        raise ValueError("参与账号未在 ACCOUNTS 中配置：" + "、".join(unknown))
    return [account for account in ACCOUNTS if account["账号"] in selected]
