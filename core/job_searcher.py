"""
校招信息搜索器 — 自动搜索企业校招信息并缓存
搜索优先级：企业官方校招官网 → 招聘平台 → 搜索引擎
"""
import json
import re
import time
import hashlib
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from config import (
    DEFAULT_COMPANIES, JOB_KEYWORDS,
    SEARCH_CACHE_HOURS, SEARCH_REQUEST_DELAY,
)
from data.database import (
    insert_job_info, get_job_info, get_job_info_recent,
    insert_event, get_events_in_range,
)


# ============ 企业官方校招 URL 映射 ============
# 这些是企业官方校园招聘网站的入口 URL，优先从这些页面获取信息

COMPANY_OFFICIAL_URLS = {
    # ==================== 互联网/科技 ====================
    "腾讯": {
        "name": "腾讯校园招聘",
        "url": "https://join.qq.com/",
    },
    "字节跳动": {
        "name": "字节跳动校园招聘",
        "url": "https://jobs.bytedance.com/campus/",
    },
    "阿里巴巴": {
        "name": "阿里巴巴校园招聘",
        "url": "https://talent.alibaba.com/campus/",
    },
    "华为": {
        "name": "华为校园招聘",
        "url": "https://career.huawei.com/reccampportal/campus4_index.html",
    },
    "美团": {
        "name": "美团校园招聘",
        "url": "https://zhaopin.meituan.com/web/campus",
    },
    "百度": {
        "name": "百度校园招聘",
        "url": "https://talent.baidu.com/jobs/campus",
    },
    "京东": {
        "name": "京东校园招聘",
        "url": "https://campus.jd.com/",
    },
    "网易": {
        "name": "网易校园招聘",
        "url": "https://campus.163.com/",
    },
    "小米": {
        "name": "小米校园招聘",
        "url": "https://xiaomi.jobs.f.mioffice.cn/campus/",
    },
    "拼多多": {
        "name": "拼多多校园招聘",
        "url": "https://careers.pinduoduo.com/campus",
    },
    "快手": {
        "name": "快手校园招聘",
        "url": "https://zhaopin.kuaishou.cn/recruit/campus/",
    },
    "小红书": {
        "name": "小红书校园招聘",
        "url": "https://job.xiaohongshu.com/campus",
    },
    "哔哩哔哩": {
        "name": "哔哩哔哩校园招聘",
        "url": "https://jobs.bilibili.com/campus/",
    },
    "滴滴": {
        "name": "滴滴校园招聘",
        "url": "https://talent.didiglobal.com/campus/",
    },
    "蚂蚁集团": {
        "name": "蚂蚁集团校园招聘",
        "url": "https://talent.antgroup.com/campus/",
    },
    # 外企
    "微软": {
        "name": "微软校园招聘",
        "url": "https://careers.microsoft.com/students/",
    },
    "谷歌": {
        "name": "谷歌校园招聘",
        "url": "https://careers.google.com/students/",
    },
    "亚马逊": {
        "name": "亚马逊校园招聘",
        "url": "https://www.amazon.jobs/zh/teams/student-programs",
    },
    "苹果": {
        "name": "苹果校园招聘",
        "url": "https://www.apple.com/careers/cn/students.html",
    },
    "英伟达": {
        "name": "英伟达校园招聘",
        "url": "https://www.nvidia.com/zh-cn/about-nvidia/careers/university-recruiting/",
    },

    # ==================== 三大运营商 ====================
    "中国移动": {
        "name": "中国移动校园招聘",
        "url": "https://job.10086.cn/",
    },
    "中国电信": {
        "name": "中国电信校园招聘",
        "url": "https://zhaopin.chinatelecom.com.cn/",
    },
    "中国联通": {
        "name": "中国联通校园招聘",
        "url": "https://chinaunicom.zhaopin.com/",
    },

    # ==================== 银行/金融 ====================
    "工商银行": {
        "name": "工商银行校园招聘",
        "url": "https://job.icbc.com.cn/",
    },
    "建设银行": {
        "name": "建设银行校园招聘",
        "url": "https://job.ccb.com/",
    },
    "中国银行": {
        "name": "中国银行校园招聘",
        "url": "https://campus.chinahr.com/pages/boc",
    },
    "农业银行": {
        "name": "农业银行校园招聘",
        "url": "https://career.abchina.com/",
    },
    "招商银行": {
        "name": "招商银行校园招聘",
        "url": "https://career.cmbchina.com/",
    },
    "交通银行": {
        "name": "交通银行校园招聘",
        "url": "https://job.bankcomm.com/",
    },
    "邮储银行": {
        "name": "邮储银行校园招聘",
        "url": "https://psbc.zhaopin.com/",
    },
    "中国人寿": {
        "name": "中国人寿校园招聘",
        "url": "https://www.chinalife.com.cn/recruitment/",
    },
    "中国平安": {
        "name": "中国平安校园招聘",
        "url": "https://campus.pingan.com/",
    },
    "中信证券": {
        "name": "中信证券校园招聘",
        "url": "https://careers.citics.com/",
    },

    # ==================== 能源/电力 ====================
    "国家电网": {
        "name": "国家电网校园招聘",
        "url": "https://zhaopin.sgcc.com.cn/",
    },
    "南方电网": {
        "name": "南方电网校园招聘",
        "url": "https://zhaopin.csg.cn/",
    },
    "中国石油": {
        "name": "中国石油校园招聘",
        "url": "https://zhaopin.cnpc.com.cn/",
    },
    "中国石化": {
        "name": "中国石化校园招聘",
        "url": "http://job.sinopec.com/",
    },
    "中国海油": {
        "name": "中国海油校园招聘",
        "url": "https://zhaopin.cnooc.com.cn/",
    },
    "国家能源集团": {
        "name": "国家能源集团校园招聘",
        "url": "https://zhaopin.chnenergy.com.cn/",
    },
    "中核集团": {
        "name": "中核集团校园招聘",
        "url": "https://cnnc.zhiye.com/",
    },

    # ==================== 航天/军工 ====================
    "中国航天科技": {
        "name": "中国航天科技校园招聘",
        "url": "https://www.spacetalent.com.cn/",
    },
    "中国航天科工": {
        "name": "中国航天科工校园招聘",
        "url": "https://zhaopin.casic.cn/",
    },
    "中国航空工业": {
        "name": "中国航空工业校园招聘",
        "url": "https://avic.zhiye.com/",
    },
    "中国电子科技": {
        "name": "中国电子科技校园招聘",
        "url": "https://cetc.zhaopin.com/",
    },
    "中国船舶": {
        "name": "中国船舶校园招聘",
        "url": "https://cssc.zhiye.com/",
    },
    "中国兵器工业": {
        "name": "中国兵器工业校园招聘",
        "url": "https://zhaopin.nhrdc.cn/",
    },

    # ==================== 建筑/基建 ====================
    "中国建筑": {
        "name": "中国建筑校园招聘",
        "url": "https://cscec.zhiye.com/",
    },
    "中国铁建": {
        "name": "中国铁建校园招聘",
        "url": "https://crcc.zhiye.com/",
    },
    "中国中铁": {
        "name": "中国中铁校园招聘",
        "url": "https://www.crecg.com/",
    },
    "中国交建": {
        "name": "中国交建校园招聘",
        "url": "https://www.ccccltd.cn/",
    },
    "中国中车": {
        "name": "中国中车校园招聘",
        "url": "https://www.crrcgc.cc/g15735.aspx",
    },
    "中国电建": {
        "name": "中国电建校园招聘",
        "url": "https://zhaopin.powerchina.cn/",
    },

    # ==================== 综合/制造/其他央企 ====================
    "华润集团": {
        "name": "华润集团校园招聘",
        "url": "https://crc.wintalent.cn/",
    },
    "中信集团": {
        "name": "中信集团校园招聘",
        "url": "https://www.citic.com/",
    },
    "中粮集团": {
        "name": "中粮集团校园招聘",
        "url": "https://www.cofco.com/",
    },
    "中国烟草": {
        "name": "中国烟草校园招聘",
        "url": "https://www.tobacco.gov.cn/",
    },
    "中国邮政": {
        "name": "中国邮政校园招聘",
        "url": "https://chinapost.zhaopin.com/",
    },
    "中国商飞": {
        "name": "中国商飞校园招聘",
        "url": "https://zhaopin.comac.cc/",
    },
    "宝武钢铁": {
        "name": "宝武钢铁校园招聘",
        "url": "https://zhaopin.baowugroup.com/",
    },
    "一汽集团": {
        "name": "一汽集团校园招聘",
        "url": "https://faw-zhaopin.hotjob.cn/",
    },
    "东风汽车": {
        "name": "东风汽车校园招聘",
        "url": "https://dfmc.hotjob.cn/",
    },
    "上汽集团": {
        "name": "上汽集团校园招聘",
        "url": "https://saicgroup.zhiye.com/",
    },
    # ==================== 粮食/农业 ====================
    "中储粮": {
        "name": "中储粮校园招聘",
        "url": "https://zhaopin.sinograin.com.cn/",
    },
    # ==================== 核电/电力 ====================
    "中广核": {
        "name": "中广核校园招聘",
        "url": "https://cgn.hotjob.cn/",
    },
    "国家电投": {
        "name": "国家电投校园招聘",
        "url": "https://zhaopin.spic.com.cn/",
    },
    # ==================== 航运/交通 ====================
    "中国远洋海运": {
        "name": "中国远洋海运校园招聘",
        "url": "https://cosco.zhaopin.com/",
    },
    "招商局集团": {
        "name": "招商局集团校园招聘",
        "url": "https://cmhk.zhiye.com/",
    },
    # ==================== 矿业/材料 ====================
    "中国五矿": {
        "name": "中国五矿校园招聘",
        "url": "https://minmetals.zhiye.com/",
    },
    "中国铝业": {
        "name": "中国铝业校园招聘",
        "url": "https://chalco.zhiye.com/",
    },
    "中国建材": {
        "name": "中国建材校园招聘",
        "url": "https://cnbm.zhiye.com/",
    },
    "中国中化": {
        "name": "中国中化校园招聘",
        "url": "https://sinochem.zhiye.com/",
    },
    "中国稀土": {
        "name": "中国稀土校园招聘",
        "url": "https://zhaopin.cre.net.cn/",
    },
    # ==================== 航空 ====================
    "中国国航": {
        "name": "中国国航校园招聘",
        "url": "https://zhaopin.airchina.com/",
    },
    "中国东航": {
        "name": "中国东航校园招聘",
        "url": "https://job.ceair.com/",
    },
    "中国南航": {
        "name": "中国南航校园招聘",
        "url": "https://job.csair.com/",
    },
    # ==================== 医药/健康 ====================
    "国药集团": {
        "name": "国药集团校园招聘",
        "url": "https://sinopharm.zhiye.com/",
    },
    "华润医药": {
        "name": "华润医药校园招聘",
        "url": "https://crc.wintalent.cn/",
    },
    # ==================== 电信设备 ====================
    "中兴通讯": {
        "name": "中兴通讯校园招聘",
        "url": "https://job.zte.com.cn/campus/",
    },
}

# ============ 企业别名/简称映射（用于模糊搜索） ============
COMPANY_ALIASES = {
    # 互联网/科技
    "腾讯": ["腾讯", "tencent", "tx", "鹅厂", "企鹅"],
    "字节跳动": ["字节跳动", "字节", "bytedance", "头条", "抖音"],
    "阿里巴巴": ["阿里巴巴", "阿里", "alibaba", "淘宝", "天猫", "蚂蚁"],
    "华为": ["华为", "huawei", "hw", "菊花厂"],
    "美团": ["美团", "meituan", "mt"],
    "百度": ["百度", "baidu", "bd"],
    "京东": ["京东", "jd", "京东商城"],
    "网易": ["网易", "netease", "163", "网抑云"],
    "小米": ["小米", "xiaomi", "mi"],
    "拼多多": ["拼多多", "pdd", "拼夕夕"],
    "快手": ["快手", "kuaishou", "ks"],
    "小红书": ["小红书", "red", "xh", "红薯"],
    "哔哩哔哩": ["哔哩哔哩", "bilibili", "b站", "B站", "破站"],
    "滴滴": ["滴滴", "didi", "dd"],
    "蚂蚁集团": ["蚂蚁集团", "蚂蚁", "ant"],
    # 外企
    "微软": ["微软", "microsoft", "ms"],
    "谷歌": ["谷歌", "google", "gg", "🐶"],
    "亚马逊": ["亚马逊", "amazon", "aws"],
    "苹果": ["苹果", "apple", "🍎"],
    "英伟达": ["英伟达", "nvidia", "nv", "核弹厂"],
    # 运营商
    "中国移动": ["中国移动", "移动", "cmcc", "中移"],
    "中国电信": ["中国电信", "电信", "ct"],
    "中国联通": ["中国联通", "联通", "cu", "中联"],
    # 银行/金融
    "工商银行": ["工商银行", "工行", "icbc", "宇宙行"],
    "建设银行": ["建设银行", "建行", "ccb"],
    "中国银行": ["中国银行", "中行", "boc"],
    "农业银行": ["农业银行", "农行", "abc"],
    "招商银行": ["招商银行", "招行", "cmb"],
    "交通银行": ["交通银行", "交行", "bcm"],
    "邮储银行": ["邮储银行", "邮储", "psbc"],
    "中国人寿": ["中国人寿", "人寿", "国寿"],
    "中国平安": ["中国平安", "平安", "pingan"],
    "中信证券": ["中信证券", "中信", "citic"],
    # 能源/电力
    "国家电网": ["国家电网", "国网", "sgcc", "电网"],
    "南方电网": ["南方电网", "南网", "csg"],
    "中国石油": ["中国石油", "中石油", "cnpc", "石油"],
    "中国石化": ["中国石化", "中石化", "sinopec", "石化"],
    "中国海油": ["中国海油", "中海油", "cnooc"],
    "国家能源集团": ["国家能源集团", "国家能源", "国能"],
    "中核集团": ["中核集团", "中核", "cnnc", "核工业"],
    # 航天/军工
    "中国航天科技": ["中国航天科技", "航天科技", "casc", "航天"],
    "中国航天科工": ["中国航天科工", "航天科工", "casic"],
    "中国航空工业": ["中国航空工业", "航空工业", "avic", "中航工业"],
    "中国电子科技": ["中国电子科技", "电子科技", "cetc", "中电科", "电科"],
    "中国船舶": ["中国船舶", "船舶", "cssc", "中船"],
    "中国兵器工业": ["中国兵器工业", "兵器工业", "兵器"],
    # 建筑/基建
    "中国建筑": ["中国建筑", "中建", "cscec"],
    "中国铁建": ["中国铁建", "铁建", "crcc"],
    "中国中铁": ["中国中铁", "中铁", "crecg"],
    "中国交建": ["中国交建", "交建", "中交"],
    "中国中车": ["中国中车", "中车", "crrc"],
    "中国电建": ["中国电建", "电建", "中电建"],
    # 综合/制造
    "华润集团": ["华润集团", "华润", "crc"],
    "中信集团": ["中信集团", "中信"],
    "中粮集团": ["中粮集团", "中粮", "cofco"],
    "中国烟草": ["中国烟草", "烟草", "中烟"],
    "中国邮政": ["中国邮政", "邮政", "邮局"],
    "中国商飞": ["中国商飞", "商飞", "comac", "大飞机"],
    "宝武钢铁": ["宝武钢铁", "宝武", "宝钢", "武钢"],
    "一汽集团": ["一汽集团", "一汽", "faw", "红旗"],
    "东风汽车": ["东风汽车", "东风", "dfm"],
    "上汽集团": ["上汽集团", "上汽", "saic"],
    # 粮食/农业
    "中储粮": ["中储粮", "中国储备粮", "sinograin", "储粮"],
    # 核电/电力
    "中广核": ["中广核", "cgn", "广核"],
    "国家电投": ["国家电投", "spic", "电投"],
    # 航运/交通
    "中国远洋海运": ["中国远洋海运", "中远海运", "远洋", "cosco", "中远"],
    "招商局集团": ["招商局集团", "招商局", "cmhk", "招商"],
    # 矿业/材料
    "中国五矿": ["中国五矿", "五矿", "minmetals"],
    "中国铝业": ["中国铝业", "中铝", "chalco"],
    "中国建材": ["中国建材", "建材", "cnbm", "中建材"],
    "中国中化": ["中国中化", "中化", "sinochem"],
    "中国稀土": ["中国稀土", "稀土", "cre"],
    # 航空
    "中国国航": ["中国国航", "国航", "airchina", "中航"],
    "中国东航": ["中国东航", "东航", "ceair", "东方航空"],
    "中国南航": ["中国南航", "南航", "csair", "南方航空"],
    # 医药
    "国药集团": ["国药集团", "国药", "sinopharm"],
    "华润医药": ["华润医药", "华润"],
    # 电信设备
    "中兴通讯": ["中兴通讯", "中兴", "zte", "ZTE"],
}

# 构建反向索引: 别名 → 企业名
ALIAS_TO_COMPANY = {}
for _company, _aliases in COMPANY_ALIASES.items():
    for _alias in _aliases:
        ALIAS_TO_COMPANY[_alias.lower()] = _company


# 第三方招聘平台（作为补充信息源）
RECRUITMENT_PLATFORMS = [
    {
        "name": "牛客网校招",
        "url_template": "https://www.nowcoder.com/school/schedule",
        "type": "aggregator",
    },
    {
        "name": "应届生求职网",
        "url_template": "https://www.yingjiesheng.com/",
        "type": "aggregator",
    },
]


# ============ 搜索接口 ============

def search_campus_recruitment(keywords: list[str] = None) -> list[dict]:
    """
    智能搜索校招信息

    策略:
    1. 从关键词中识别企业名 → 只搜这些企业的官网
    2. 通用关键词 → 搜招聘平台 + 热门企业
    3. 最多发 ~8 个 HTTP 请求

    Args:
        keywords: 搜索关键词列表，为空则使用默认关键词

    Returns:
        校招信息列表
    """
    if keywords is None:
        keywords = ["校招"]

    # 频率控制
    kw_str = ",".join(sorted(keywords))
    if not _should_search(kw_str):
        return get_job_info_recent(days=7)

    # === 第1步: 从关键词中模糊识别企业名 ===
    matched_companies = []
    general_keywords = []

    for kw in keywords:
        companies = _fuzzy_match_company(kw)
        if companies:
            matched_companies.extend(companies)
        else:
            general_keywords.append(kw)

    # 去重，保持顺序
    seen = set()
    matched_companies = [c for c in matched_companies if not (c in seen or seen.add(c))]

    # === 第2步: 搜索匹配到的企业官网（最多 5 家） ===
    results = []
    for company in matched_companies[:5]:
        try:
            info = _search_company_campus(company, general_keywords[0] if general_keywords else "校招")
            if info:
                results = _dedup_and_save(info, results)
            time.sleep(1)
        except Exception as e:
            print(f"[WARN] 搜索 {company} 失败: {e}")

    # === 第3步: 未识别到库内企业？当作公司名直接搜索 ===
    if not matched_companies and general_keywords:
        # 从通用关键词中提取可能的公司名
        unknown_companies = [kw for kw in general_keywords if _looks_like_company(kw)]
        other_keywords = [kw for kw in general_keywords if not _looks_like_company(kw)]

        # 对看起来像公司名的词，直接用搜索引擎搜
        for company in unknown_companies[:5]:
            print(f"[搜索] 库外企业 \"{company}\"，搜索引擎搜索...")
            try:
                info = _search_unknown_company(company, other_keywords or ["校招"])
                if info:
                    results = _dedup_and_save(info, results)
                time.sleep(1)
            except Exception as e:
                print(f"[WARN] 搜索 \"{company}\" 失败: {e}")

        # 剩余纯通用词 → 搜平台
        remaining = [kw for kw in general_keywords if not _looks_like_company(kw)]
        if not unknown_companies or len(results) < 2:
            print(f"[搜索] 补充搜索招聘平台...")
            try:
                platform_results = _search_platforms_general(remaining or ["校招"])
                for info in platform_results:
                    results = _dedup_and_save(info, results)
            except Exception as e:
                print(f"[WARN] 平台搜索失败: {e}")

    # === 第4步: 结果太少？补充搜索引擎 ===
    if len(results) < 2:
        targets = matched_companies[:3] if matched_companies else []
        # 把未知公司名也加进去
        if not targets and general_keywords:
            targets = [kw for kw in general_keywords[:3] if _looks_like_company(kw)]
        for target in targets:
            try:
                info = _search_baidu(target, general_keywords[0] if general_keywords else "校招")
                if info:
                    results = _dedup_and_save(info, results)
                time.sleep(1)
            except Exception:
                pass

    # === 兜底: 返回缓存 ===
    if not results:
        results = get_job_info_recent(days=30)

    _update_search_cache(kw_str)
    return results


def _dedup_and_save(info: dict, existing_results: list) -> list:
    """去重并保存到数据库"""
    company = info.get("company", "")
    url = info.get("url", "")

    # 检查本次结果中是否已存在
    for r in existing_results:
        if r.get("url") == url:
            return existing_results

    # 检查数据库中是否已存在
    existing = get_job_info(company=company, days=30)
    existing_urls = {e.get("url", "") for e in existing}
    if url in existing_urls:
        for e in existing:
            if e.get("url") == url:
                existing_results.append(e)
                return existing_results

    # 保存新信息
    try:
        jid = insert_job_info(info)
        info["id"] = jid
    except Exception:
        pass
    existing_results.append(info)
    return existing_results


def _fuzzy_match_company(keyword: str) -> list[str]:
    """
    模糊匹配企业名

    三层匹配策略:
    1. 别名精确匹配（含英文名、昵称、缩写）
    2. 企业名双向子串匹配（"腾讯校招" → 腾讯，"工行招聘" → 工商银行）
    3. jieba 分词匹配（"我想去鹅厂" → 分词"鹅厂" → 腾讯）

    Returns:
        匹配到的企业名列表（按匹配精度排序）
    """
    kw_lower = keyword.lower().strip()
    if not kw_lower:
        return []

    matches = []  # [(company, score), ...]

    # 第一层: 别名表精确查找
    for alias, company in ALIAS_TO_COMPANY.items():
        if alias == kw_lower or alias in kw_lower:
            # 别名越长，匹配越精准
            score = len(alias) / len(kw_lower) if kw_lower else 1
            matches.append((company, score + 2.0))  # +2 保证别名匹配优先级最高

    # 第二层: 企业名双向子串匹配
    for company in COMPANY_OFFICIAL_URLS:
        # 关键词包含企业名（如 "腾讯2026校招"）
        if company in keyword:
            score = len(company) / len(keyword) if keyword else 1
            if (company, score + 1.0) not in [(m[0], m[1]) for m in matches]:
                matches.append((company, score + 1.0))
        # 关键词是企业名的子串（如 "工行" → "工商银行"）
        elif len(kw_lower) >= 2 and kw_lower in company:
            score = len(kw_lower) / len(company) if company else 0.5
            if (company, score + 0.5) not in [(m[0], m[1]) for m in matches]:
                matches.append((company, score + 0.5))

    # 第三层: jieba 分词后逐个匹配别名
    if not matches:
        try:
            import jieba
            tokens = list(jieba.cut(keyword))
            for token in tokens:
                token_lower = token.lower().strip()
                if len(token_lower) < 2:
                    continue
                # 在别名表中查找
                for alias, company in ALIAS_TO_COMPANY.items():
                    if token_lower == alias or token_lower in alias:
                        matches.append((company, 1.5))
                        break
                # 子串匹配企业名
                if not any(m[0] == company for m in matches for company in [c for c in COMPANY_OFFICIAL_URLS]):
                    for company in COMPANY_OFFICIAL_URLS:
                        if token_lower in company or company in token_lower:
                            matches.append((company, 1.0))
                            break
        except ImportError:
            pass

    # 去重并按分数排序
    seen = set()
    unique = []
    for company, score in sorted(matches, key=lambda x: -x[1]):
        if company not in seen:
            seen.add(company)
            unique.append(company)

    if unique:
        print(f"[模糊匹配] \"{keyword}\" → {unique}")

    return unique


def _looks_like_company(keyword: str) -> bool:
    """
    判断关键词是否像一个公司名（而非通用词如'校招'、'面试'）

    规则:
    - 纯中文且 2-8 个字符
    - 不是通用求职关键词
    - 不含明显的非公司词（如: 的、了、在、去、我、要）
    """
    kw = keyword.strip()
    if len(kw) < 2 or len(kw) > 12:
        return False

    # 通用求职关键词，不是公司名
    generic_words = {
        "校招", "校园招聘", "应届生", "实习生", "培训生",
        "笔试", "面试", "网申", "投递", "内推",
        "秋招", "春招", "补录", "offer", "招聘",
        "2026", "2027", "2025", "2026届", "2027届",
        "实习", "工作", "求职", "找工作", "暑假实习",
    }
    if kw.lower() in {w.lower() for w in generic_words}:
        return False

    # 明显不是公司名的模式
    non_company_patterns = [
        "的", "了", "在", "是", "去", "我", "要", "想",
        "什么", "怎么", "如何", "哪些", "哪个", "有没有",
        "请问", "求问", "问一下",
    ]
    if any(p in kw for p in non_company_patterns):
        return False

    # 中文为主（至少含一个中文字符），长度 2-8 很可能是公司名/简称
    import re
    chinese_chars = len(re.findall(r'[一-鿿]', kw))
    if chinese_chars >= 2:
        return True

    # 纯英文 2-10 字符可能是英文公司名/缩写
    if re.match(r'^[a-zA-Z]{2,10}$', kw):
        return True

    return False


def _search_unknown_company(company_name: str, keywords: list[str]) -> dict | None:
    """
    搜索库外企业（不在 COMPANY_OFFICIAL_URLS 中的企业）

    直接用百度搜索引擎搜索 "{company_name} 校招"，提取结果
    """
    search_query = f"{company_name} 校招 2026"
    print(f"  -> 百度搜索: {search_query}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        encoded_query = requests.utils.quote(search_query)
        resp = requests.get(
            f"https://www.baidu.com/s?wd={encoded_query}",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        search_results = soup.select(".result")

        best_info = None
        for result in search_results[:5]:
            title_el = result.select_one("h3 a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")

            abstract_el = result.select_one(".c-abstract")
            abstract = abstract_el.get_text(strip=True) if abstract_el else ""

            combined = title + abstract

            # 检查是否与校招/招聘相关
            is_job_related = any(
                kw in combined for kw in
                ["校招", "校园招聘", "应届", "招聘", "2026", "2027",
                 "秋招", "春招", "网申", "投递", "笔试", "面试"]
            )

            if is_job_related or not best_info:
                deadline = _extract_deadline(combined)
                info = {
                    "company": company_name,
                    "title": title[:100],
                    "description": abstract[:500],
                    "deadline": deadline,
                    "url": link,
                    "source": f"搜索引擎 (库外企业)",
                }
                if is_job_related:
                    return info  # 找到校招相关结果，直接返回
                best_info = info   # 保留最好的结果作为兜底

        return best_info

    except Exception as e:
        print(f"  -> 库外企业搜索失败: {e}")
        return None


def _search_platforms_general(keywords: list[str]) -> list[dict]:
    """搜索招聘平台获取校招信息"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    # 牛客网校招日程
    try:
        resp = requests.get(
            "https://www.nowcoder.com/school/schedule",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text()

        # 提取页面中出现的已知企业
        found_companies = []
        for company in COMPANY_OFFICIAL_URLS:
            if company in full_text:
                found_companies.append(company)

        # 对找到的企业（限制 8 家），尝试获取官网信息
        for company in found_companies[:8]:
            try:
                info = _search_company_campus(company, keywords[0] if keywords else "校招")
                if info:
                    results.append(info)
                time.sleep(1)
            except Exception:
                continue

    except Exception as e:
        print(f"[WARN] 牛客网访问失败: {e}")

    return results


def get_cached_job_info() -> list[dict]:
    """获取缓存的校招信息"""
    return get_job_info_recent(days=30)


def create_job_events(job_info_list: list[dict]) -> list[int]:
    """
    将校招截止日期创建为日历事件

    Returns:
        创建的事件 ID 列表
    """
    event_ids = []

    for job in job_info_list:
        deadline_str = job.get("deadline", "")
        if not deadline_str:
            continue

        try:
            deadline = datetime.fromisoformat(deadline_str)
        except (ValueError, TypeError):
            continue

        # 如果已经过期，跳过
        if deadline < datetime.now():
            continue

        # 创建提醒事件
        event_data = {
            "title": f"📅 {job['company']} - {job.get('title', '校招截止')}",
            "description": f"校招投递截止：{job.get('company')}\n{job.get('description', '')}\n{job.get('url', '')}",
            "event_type": "job_search",
            "start_time": deadline.strftime("%Y-%m-%dT09:00:00"),
            "end_time": deadline.strftime("%Y-%m-%dT10:00:00"),
            "location": "",
            "priority": 3,
            "tags": json.dumps(["校招", "截止", job.get("company", "")], ensure_ascii=False),
            "source": "job_search",
        }

        # 检查是否重复
        day_start = deadline.strftime("%Y-%m-%d") + "T00:00:00"
        day_end = deadline.strftime("%Y-%m-%d") + "T23:59:59"
        existing = get_events_in_range(day_start, day_end)
        duplicate = any(
            e["title"] == event_data["title"] for e in existing
        )

        if not duplicate:
            event_id = insert_event(event_data)
            event_ids.append(event_id)

    return event_ids


# ============ 搜索实现 ============

def _search_company_campus(company: str, keyword: str) -> dict | None:
    """
    搜索特定企业的校招信息

    优先级：企业官方校招官网 → 第三方招聘平台 → 百度搜索
    """
    print(f"[搜索] {company} + {keyword} ...")

    # 1. 优先尝试企业官方校招网站
    if company in COMPANY_OFFICIAL_URLS:
        print(f"  -> 尝试官方校招官网: {COMPANY_OFFICIAL_URLS[company]['url']}")
        try:
            info = _search_official_site(company, keyword)
            if info:
                print(f"  -> [OK] 从官网获取到信息")
                return info
        except Exception as e:
            print(f"  -> [WARN] 官网搜索失败: {e}")

    # 2. 尝试第三方招聘平台
    print(f"  -> 尝试第三方招聘平台...")
    try:
        info = _search_platforms(company, keyword)
        if info:
            print(f"  -> [OK] 从招聘平台获取到信息")
            return info
    except Exception as e:
        print(f"  -> [WARN] 平台搜索失败: {e}")

    # 3. 最后兜底：百度搜索
    print(f"  -> 百度搜索兜底...")
    try:
        info = _search_baidu(company, keyword)
        if info:
            print(f"  -> [OK] 从搜索引擎获取到信息")
            return info
    except Exception as e:
        print(f"  -> [WARN] 搜索引擎搜索失败: {e}")

    return None


def _search_official_site(company: str, keyword: str) -> dict | None:
    """
    直接访问企业官方校招网站，提取招聘信息

    策略：
    1. 直接请求官网 URL
    2. 解析页面内容，提取：
       - 招聘状态（是否开放申请）
       - 截止日期
       - 招聘岗位关键词
    3. 如果官网无法访问或被拦截，返回 None 触发降级搜索
    """
    if company not in COMPANY_OFFICIAL_URLS:
        return None

    site_info = COMPANY_OFFICIAL_URLS[company]
    url = site_info["url"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Referer": "https://www.google.com/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()

        # 自动检测编码
        try:
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception:
            resp.encoding = "utf-8"

        html = resp.text

        # 如果页面内容太短，可能是 JS 渲染页面，requests 无法获取到有效内容
        if len(html) < 500:
            # 尝试从页面元信息和 URL 本身构建基本信息
            return _build_fallback_info(company, url)

        soup = BeautifulSoup(html, "lxml")

        # 提取页面标题
        title_text = ""
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)

        # 提取 meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")
        if not meta_desc:
            meta_tag = soup.find("meta", attrs={"name": "Description"})
            if meta_tag:
                meta_desc = meta_tag.get("content", "")

        # 获取页面全部可见文本（前3000字符）
        body = soup.find("body")
        full_text = body.get_text(separator=" ", strip=True)[:3000] if body else ""

        # 提取截止日期（从全文中搜索）
        combined_text = f"{title_text} {meta_desc} {full_text}"
        deadline = _extract_deadline(combined_text)

        # 提取招聘状态关键词
        status_keywords = _extract_status_keywords(combined_text)

        # 构建标题
        if keyword and keyword in combined_text:
            display_title = f"{company} {keyword}"
        elif "2027" in combined_text:
            display_title = f"{company} 2027届校园招聘"
        elif "2026" in combined_text:
            display_title = f"{company} 2026届校园招聘"
        elif "暑期实习" in combined_text:
            display_title = f"{company} 暑期实习生招聘"
        else:
            display_title = f"{company} 校园招聘"

        # 构建描述
        desc_parts = []
        if status_keywords:
            desc_parts.append(f"状态: {'、'.join(status_keywords[:3])}")
        if meta_desc:
            desc_parts.append(meta_desc[:200])
        elif full_text:
            # 截取前200字符作为描述
            desc_parts.append(full_text[:200])

        description = " | ".join(desc_parts) if desc_parts else title_text

        return {
            "company": company,
            "title": display_title[:100],
            "description": description[:500],
            "deadline": deadline,
            "url": url,  # 使用官方 URL，不是搜索引擎结果
            "source": f"官方校招官网 ({site_info['name']})",
        }

    except requests.exceptions.Timeout:
        print(f"  -> 官网 {url} 访问超时")
    except requests.exceptions.ConnectionError:
        print(f"  -> 官网 {url} 无法连接")
    except requests.exceptions.HTTPError as e:
        print(f"  -> 官网 {url} HTTP错误: {e}")
    except Exception as e:
        print(f"  -> 官网 {url} 解析异常: {e}")

    # 官网访问失败，尝试用 URL+标题构建基本信息
    return _build_fallback_info(company, url)


def _build_fallback_info(company: str, url: str) -> dict | None:
    """
    当官网是纯 JS 渲染页面无法解析时，用已知信息构建基本记录
    至少让用户知道有这样一个官方入口可以查看
    """
    return {
        "company": company,
        "title": f"{company} 校园招聘官网",
        "description": f"{company}官方校招入口。该页面可能为动态加载，请点击链接在浏览器中查看最新招聘岗位、截止日期和申请方式。",
        "deadline": "",  # JS 渲染页面无法提取，用户需手动查看
        "url": url,
        "source": f"官方校招官网",
    }


def _search_platforms(company: str, keyword: str) -> dict | None:
    """
    在第三方招聘平台上搜索校招信息
    """
    # 尝试牛客网
    try:
        info = _search_nowcoder(company, keyword)
        if info:
            return info
    except Exception:
        pass

    return None


def _search_nowcoder(company: str, keyword: str) -> dict | None:
    """
    在牛客网搜索校招日程
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.nowcoder.com/",
    }

    try:
        # 牛客网校招日程页面
        resp = requests.get(
            "https://www.nowcoder.com/school/schedule",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # 查找包含企业名的元素
        full_text = soup.get_text()

        if company in full_text:
            # 尝试提取相关信息
            return {
                "company": company,
                "title": f"{company} 校招信息（牛客网）",
                "description": f"在牛客网校招日程中找到 {company} 的相关记录，请访问网站查看详情",
                "deadline": _extract_deadline(full_text),
                "url": f"https://www.nowcoder.com/school/schedule",
                "source": "牛客网校招日程",
            }
    except Exception:
        pass

    return None


def _search_baidu(company: str, keyword: str) -> dict | None:
    """
    百度搜索作为兜底方案
    """
    search_query = f"{company} {keyword} 2026"
    encoded_query = requests.utils.quote(search_query)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    resp = requests.get(
        f"https://www.baidu.com/s?wd={encoded_query}",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    results = soup.select(".result")
    for result in results[:5]:
        title_el = result.select_one("h3 a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        link = title_el.get("href", "")

        abstract_el = result.select_one(".c-abstract")
        abstract = abstract_el.get_text(strip=True) if abstract_el else ""

        combined = title + abstract
        is_campus = any(
            kw in combined for kw in
            ["校招", "校园招聘", "应届", "实习生", "2026", "2027", "秋招", "春招"]
        )

        if is_campus:
            deadline = _extract_deadline(combined)
            return {
                "company": company,
                "title": title[:100],
                "description": abstract[:500],
                "deadline": deadline,
                "url": link,
                "source": "搜索引擎",
            }

    return None


def _extract_status_keywords(text: str) -> list[str]:
    """
    从页面文本中提取招聘状态关键词
    """
    statuses = []
    patterns = [
        (r"网申.*?开放", "网申开放中"),
        (r"(?:已|已经|正在|正式)开启", "已开启"),
        (r"即将截止", "即将截止"),
        (r"倒计时", "倒计时中"),
        (r"面试.*?进行中", "面试进行中"),
        (r"笔试.*?通知", "笔试通知中"),
        (r"(?:提前批|正式批|补录|春招|秋招)", None),  # 作为标签而非状态
        (r"offer.*?发放", "Offer发放中"),
    ]

    for pattern, label in patterns:
        if re.search(pattern, text):
            if label:
                statuses.append(label)
            else:
                m = re.search(pattern, text)
                if m:
                    statuses.append(m.group(1))

    return list(set(statuses))[:5]


def _search_general_campus(keyword: str) -> list[dict]:
    """
    通用校招搜索（不针对特定企业）
    优先搜索第三方招聘平台，再兜底百度
    """
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    # 1. 尝试牛客网校招日程
    try:
        resp = requests.get(
            "https://www.nowcoder.com/school/schedule",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text()

        # 对每个默认企业，检查是否在页面中
        for company in DEFAULT_COMPANIES[:15]:
            if company in full_text:
                deadline = _extract_deadline(full_text)
                results.append({
                    "company": company,
                    "title": f"{company} 校招信息",
                    "description": f"在牛客网校招日程中找到 {company}。详情请访问网站。",
                    "deadline": deadline,
                    "url": "https://www.nowcoder.com/school/schedule",
                    "source": "牛客网",
                })

        if results:
            return results
    except Exception:
        pass

    # 2. 兜底：百度搜索
    search_query = f"2026届 校园招聘 {keyword}"
    encoded_query = requests.utils.quote(search_query)

    try:
        resp = requests.get(
            f"https://www.baidu.com/s?wd={encoded_query}",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        search_results = soup.select(".result")

        for result in search_results[:8]:
            title_el = result.select_one("h3 a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")

            abstract_el = result.select_one(".c-abstract")
            abstract = abstract_el.get_text(strip=True) if abstract_el else ""

            combined = title + abstract

            company = ""
            for c in DEFAULT_COMPANIES:
                if c in combined:
                    company = c
                    break
            if not company:
                company = title[:8]

            deadline = _extract_deadline(combined)

            results.append({
                "company": company,
                "title": title[:100],
                "description": abstract[:500],
                "deadline": deadline,
                "url": link,
                "source": "搜索引擎",
            })

    except Exception:
        pass

    return results


# ============ 工具函数 ============

def _extract_deadline(text: str) -> str:
    """
    从文本中提取截止日期

    返回 ISO 8601 格式日期字符串，无法提取则返回空字符串
    """
    import re

    # 常见截止日期模式
    patterns = [
        r"截止[日期]?[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})",
        r"网申[截止]?[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})",
        r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?截止",
        r"截止时间[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})",
        r"deadline[：:]?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return f"{year:04d}-{month:02d}-{day:02d}T23:59:59"
            except (ValueError, IndexError):
                continue

    return ""


def _should_search(keyword_hash: str) -> bool:
    """
    频率控制：检查是否应执行搜索
    """
    from data.database import get_preference, set_preference

    cache_key = f"search_cache_{_hash_key(keyword_hash)}"
    last_search = get_preference(cache_key)

    if last_search:
        try:
            last_time = datetime.fromisoformat(last_search)
            if datetime.now() - last_time < timedelta(hours=SEARCH_CACHE_HOURS):
                return False
        except (ValueError, TypeError):
            pass

    return True


def _update_search_cache(keyword: str):
    """更新搜索缓存时间"""
    from data.database import set_preference

    cache_key = f"search_cache_{_hash_key(keyword)}"
    set_preference(cache_key, datetime.now().isoformat())


def _hash_key(text: str) -> str:
    """生成短哈希"""
    return hashlib.md5(text.encode()).hexdigest()[:12]
