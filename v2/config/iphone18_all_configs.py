# -*- coding: utf-8 -*-
# iPhone 18 系列全部配置（苹果中国大陆官网，2026-09-25）
# 来源：https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjy94ch/a
# 官网当前 18 系列为 Pro / Pro Max，共 32 项；购买目录未列出 18 标准版、Plus 或 18e。
# 两款均为：勃艮第酒红色、冰川蓝色、银色、黑色 × 256GB、512GB、1TB、2TB。
# 每项五个字段可复制到 v2/config.py 的账号配置中，数量统一设为 1。
# URL 均与官网页面链接核对；选配字段来自 productSelectionData.products。
# 这是选配枚举，不代表实时库存或结账可用性。

IPHONE_18_CONFIGS = {
    # MJT94CH/A
    "iPhone 18 Pro 256GB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjt94ch/a",
        "机型": "iphone18pro", "颜色": "burgundy", "容量": "256gb", "数量": 1,
    },
    # MJTE4CH/A
    "iPhone 18 Pro 512GB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjte4ch/a",
        "机型": "iphone18pro", "颜色": "burgundy", "容量": "512gb", "数量": 1,
    },
    # MJTJ4CH/A
    "iPhone 18 Pro 1TB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtj4ch/a",
        "机型": "iphone18pro", "颜色": "burgundy", "容量": "1tb", "数量": 1,
    },
    # MJTN4CH/A
    "iPhone 18 Pro 2TB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtn4ch/a",
        "机型": "iphone18pro", "颜色": "burgundy", "容量": "2tb", "数量": 1,
    },
    # MJTA4CH/A
    "iPhone 18 Pro 256GB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjta4ch/a",
        "机型": "iphone18pro", "颜色": "glacier", "容量": "256gb", "数量": 1,
    },
    # MJTF4CH/A
    "iPhone 18 Pro 512GB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtf4ch/a",
        "机型": "iphone18pro", "颜色": "glacier", "容量": "512gb", "数量": 1,
    },
    # MJTK4CH/A
    "iPhone 18 Pro 1TB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtk4ch/a",
        "机型": "iphone18pro", "颜色": "glacier", "容量": "1tb", "数量": 1,
    },
    # MJTP4CH/A
    "iPhone 18 Pro 2TB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtp4ch/a",
        "机型": "iphone18pro", "颜色": "glacier", "容量": "2tb", "数量": 1,
    },
    # MJT84CH/A
    "iPhone 18 Pro 256GB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjt84ch/a",
        "机型": "iphone18pro", "颜色": "silver", "容量": "256gb", "数量": 1,
    },
    # MJTD4CH/A
    "iPhone 18 Pro 512GB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtd4ch/a",
        "机型": "iphone18pro", "颜色": "silver", "容量": "512gb", "数量": 1,
    },
    # MJTH4CH/A
    "iPhone 18 Pro 1TB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjth4ch/a",
        "机型": "iphone18pro", "颜色": "silver", "容量": "1tb", "数量": 1,
    },
    # MJTM4CH/A
    "iPhone 18 Pro 2TB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtm4ch/a",
        "机型": "iphone18pro", "颜色": "silver", "容量": "2tb", "数量": 1,
    },
    # MJT74CH/A
    "iPhone 18 Pro 256GB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjt74ch/a",
        "机型": "iphone18pro", "颜色": "black", "容量": "256gb", "数量": 1,
    },
    # MJTC4CH/A
    "iPhone 18 Pro 512GB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtc4ch/a",
        "机型": "iphone18pro", "颜色": "black", "容量": "512gb", "数量": 1,
    },
    # MJTG4CH/A
    "iPhone 18 Pro 1TB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtg4ch/a",
        "机型": "iphone18pro", "颜色": "black", "容量": "1tb", "数量": 1,
    },
    # MJTL4CH/A
    "iPhone 18 Pro 2TB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtl4ch/a",
        "机型": "iphone18pro", "颜色": "black", "容量": "2tb", "数量": 1,
    },
    # MJY84CH/A
    "iPhone 18 Pro Max 256GB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjy84ch/a",
        "机型": "iphone18promax", "颜色": "burgundy", "容量": "256gb", "数量": 1,
    },
    # MJYD4CH/A
    "iPhone 18 Pro Max 512GB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyd4ch/a",
        "机型": "iphone18promax", "颜色": "burgundy", "容量": "512gb", "数量": 1,
    },
    # MJYH4CH/A
    "iPhone 18 Pro Max 1TB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyh4ch/a",
        "机型": "iphone18promax", "颜色": "burgundy", "容量": "1tb", "数量": 1,
    },
    # MJYM4CH/A
    "iPhone 18 Pro Max 2TB 勃艮第酒红色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjym4ch/a",
        "机型": "iphone18promax", "颜色": "burgundy", "容量": "2tb", "数量": 1,
    },
    # MJY94CH/A
    "iPhone 18 Pro Max 256GB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjy94ch/a",
        "机型": "iphone18promax", "颜色": "glacier", "容量": "256gb", "数量": 1,
    },
    # MJYE4CH/A
    "iPhone 18 Pro Max 512GB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjye4ch/a",
        "机型": "iphone18promax", "颜色": "glacier", "容量": "512gb", "数量": 1,
    },
    # MJYJ4CH/A
    "iPhone 18 Pro Max 1TB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyj4ch/a",
        "机型": "iphone18promax", "颜色": "glacier", "容量": "1tb", "数量": 1,
    },
    # MJYN4CH/A
    "iPhone 18 Pro Max 2TB 冰川蓝色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyn4ch/a",
        "机型": "iphone18promax", "颜色": "glacier", "容量": "2tb", "数量": 1,
    },
    # MJY74CH/A
    "iPhone 18 Pro Max 256GB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjy74ch/a",
        "机型": "iphone18promax", "颜色": "silver", "容量": "256gb", "数量": 1,
    },
    # MJYC4CH/A
    "iPhone 18 Pro Max 512GB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyc4ch/a",
        "机型": "iphone18promax", "颜色": "silver", "容量": "512gb", "数量": 1,
    },
    # MJYG4CH/A
    "iPhone 18 Pro Max 1TB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyg4ch/a",
        "机型": "iphone18promax", "颜色": "silver", "容量": "1tb", "数量": 1,
    },
    # MJYL4CH/A
    "iPhone 18 Pro Max 2TB 银色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyl4ch/a",
        "机型": "iphone18promax", "颜色": "silver", "容量": "2tb", "数量": 1,
    },
    # MJY64CH/A
    "iPhone 18 Pro Max 256GB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjy64ch/a",
        "机型": "iphone18promax", "颜色": "black", "容量": "256gb", "数量": 1,
    },
    # MJYA4CH/A
    "iPhone 18 Pro Max 512GB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjya4ch/a",
        "机型": "iphone18promax", "颜色": "black", "容量": "512gb", "数量": 1,
    },
    # MJYF4CH/A
    "iPhone 18 Pro Max 1TB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyf4ch/a",
        "机型": "iphone18promax", "颜色": "black", "容量": "1tb", "数量": 1,
    },
    # MJYK4CH/A
    "iPhone 18 Pro Max 2TB 黑色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjyk4ch/a",
        "机型": "iphone18promax", "颜色": "black", "容量": "2tb", "数量": 1,
    },

    # iPhone Duo（2026-10-15 核对）：https://www.apple.com.cn/shop/buy-iphone/iphone-duo
    # 2026-10-16 20:00 预购，2026-10-23 发售；参数来自 productSelectionData.products。
    # MK2M4CH/A
    "iPhone Duo 256GB 星光白色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2m4ch/a",
        "机型": "iphoneduo", "颜色": "starwhite", "容量": "256gb", "数量": 1,
    },
    # MK2P4CH/A
    "iPhone Duo 512GB 星光白色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2p4ch/a",
        "机型": "iphoneduo", "颜色": "starwhite", "容量": "512gb", "数量": 1,
    },
    # MK2T4CH/A
    "iPhone Duo 1TB 星光白色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2t4ch/a",
        "机型": "iphoneduo", "颜色": "starwhite", "容量": "1tb", "数量": 1,
    },
    # MK2V4CH/A
    "iPhone Duo 2TB 星光白色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2v4ch/a",
        "机型": "iphoneduo", "颜色": "starwhite", "容量": "2tb", "数量": 1,
    },
    # MK2N4CH/A
    "iPhone Duo 256GB 夜空色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2n4ch/a",
        "机型": "iphoneduo", "颜色": "nightsky", "容量": "256gb", "数量": 1,
    },
    # MK2Q4CH/A
    "iPhone Duo 512GB 夜空色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2q4ch/a",
        "机型": "iphoneduo", "颜色": "nightsky", "容量": "512gb", "数量": 1,
    },
    # MK2U4CH/A
    "iPhone Duo 1TB 夜空色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2u4ch/a",
        "机型": "iphoneduo", "颜色": "nightsky", "容量": "1tb", "数量": 1,
    },
    # MK2W4CH/A
    "iPhone Duo 2TB 夜空色": {
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo/mk2w4ch/a",
        "机型": "iphoneduo", "颜色": "nightsky", "容量": "2tb", "数量": 1,
    },
}
