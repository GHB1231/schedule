"""
配置文件 — 管理 API Key、搜索关键词等配置项
"""
import os
import json

# 项目根目录（兼容 PyInstaller 打包）
import sys as _sys
if getattr(_sys, 'frozen', False):
    BASE_DIR = os.path.dirname(_sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据库路径（云端部署时可用环境变量覆盖）
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "storage"))
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE_PATH = os.path.join(DATA_DIR, "schedule.db")

# Claude API 配置
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# 校招搜索配置
SEARCH_CACHE_HOURS = 24  # 搜索结果缓存时间（小时）
SEARCH_REQUEST_DELAY = 2  # 搜索请求间隔（秒）

# 校招目标企业列表（默认）
DEFAULT_COMPANIES = [
    # === 互联网/科技 ===
    "腾讯", "阿里巴巴", "字节跳动", "华为", "美团",
    "百度", "京东", "网易", "小米", "拼多多",
    "快手", "小红书", "哔哩哔哩", "滴滴", "蚂蚁集团",
    "微软", "谷歌", "亚马逊", "苹果", "英伟达",
    # === 运营商 ===
    "中国移动", "中国电信", "中国联通",
    # === 金融/银行 ===
    "工商银行", "建设银行", "中国银行", "农业银行",
    "招商银行", "交通银行", "邮储银行",
    "中国人寿", "中国平安", "中信证券",
    # === 能源/电力 ===
    "国家电网", "南方电网", "中国石油", "中国石化",
    "中国海油", "国家能源集团", "中核集团",
    # === 航天/军工 ===
    "中国航天科技", "中国航天科工", "中国航空工业",
    "中国电子科技", "中国船舶", "中国兵器工业",
    # === 建筑/基建 ===
    "中国建筑", "中国铁建", "中国中铁", "中国交建",
    "中国中车", "中国电建",
    # === 综合/其他 ===
    "华润集团", "中信集团", "中粮集团", "中国烟草",
    "中国邮政", "中国商飞", "宝武钢铁",
    "一汽集团", "东风汽车", "上汽集团",
    # === 粮食/农业 ===
    "中储粮",
    # === 核电/电力 ===
    "中广核", "国家电投",
    # === 航运/交通 ===
    "中国远洋海运", "招商局集团",
    # === 矿业/材料 ===
    "中国五矿", "中国铝业", "中国建材", "中国中化", "中国稀土",
    # === 航空 ===
    "中国国航", "中国东航", "中国南航",
    # === 医药 ===
    "国药集团", "华润医药",
    # === 电信设备 ===
    "中兴通讯",
]

# 校招搜索关键词（触发搜索的输入关键词）
JOB_KEYWORDS = [
    "校招", "校园招聘", "应届生", "实习生", "培训生",
    "笔试", "面试", "网申", "投递", "内推",
    "秋招", "春招", "补录", "offer"
]

# 事件类型及其颜色映射
EVENT_TYPE_COLORS = {
    "task":       "#4A90D9",  # 蓝色 — 一般任务
    "meeting":    "#E8845C",  # 橙色 — 会议
    "reminder":   "#7B68EE",  # 紫色 — 提醒
    "job_search": "#E85D75",  # 红色 — 求职相关
    "learning":   "#50C878",  # 绿色 — 学习
    "other":      "#95A5A6",  # 灰色 — 其他
}


def load_local_config():
    """加载本地配置文件（若存在），覆盖默认配置"""
    config_file = os.path.join(BASE_DIR, "config.local.json")
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# 加载本地配置
_local = load_local_config()
if _local:
    if "anthropic_api_key" in _local:
        ANTHROPIC_API_KEY = _local["anthropic_api_key"]
    if "anthropic_model" in _local:
        ANTHROPIC_MODEL = _local["anthropic_model"]
