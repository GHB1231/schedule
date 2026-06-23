"""
智能解析器 — 使用 Claude API 将中文自然语言解析为结构化日程数据
"""
import json
import re
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL, JOB_KEYWORDS


# 解析 Prompt 模板
PARSE_SYSTEM_PROMPT = """你是一个智能日程解析助手。用户会用中文描述一个日程事件，你需要将其解析为结构化的 JSON 数据。

## 当前时间
{current_datetime}
今天是 {weekday_name}

## 解析规则

1. **时间识别**：
   - 将中文时间表达转换为 ISO 8601 格式（如 "2026-06-28T15:00:00"）
   - "明天"、"后天"、"下周X"、"X天后"、"下周X下午X点" 等都要精确计算
   - "上午" ≈ 9:00，"中午" ≈ 12:00，"下午" ≈ 14:00-15:00（根据语境），"晚上" ≈ 19:00-20:00
   - 如果没有明确时间，根据事件类型推荐一个合理的时间
   - 默认为 1 小时的事件，除非描述中明确说明了时长

2. **事件类型识别** (event_type)：
   - "task": 一般任务、待办事项、学习、写代码、做项目
   - "meeting": 会议、面试、约见、面谈
   - "reminder": 提醒、截止日期、到期、不要忘记
   - "job_search": 求职相关（笔试、面试、投递、校招、企业名称+招聘动作）
   - "learning": 学习、上课、看书、刷题
   - "other": 无法归类

3. **标签提取** (tags)：提取有意义的关键词标签，如企业名、活动类型、人物等

4. **优先级** (priority)：0=普通, 1=低, 2=中, 3=高
   - 面试、笔试、截止日期 → 3
   - 重要会议 → 2
   - 普通任务 → 0

## 输出格式
必须严格输出以下 JSON 格式，不要有任何其他文本：

```json
{{
  "title": "简洁的事件标题",
  "event_type": "task|meeting|reminder|job_search|learning|other",
  "start_time": "2026-06-28T15:00:00",
  "end_time": "2026-06-28T16:00:00",
  "location": "地点（没有则为空字符串）",
  "description": "事件描述",
  "priority": 0,
  "tags": ["标签1", "标签2"],
  "source": "auto"
}}
```"""


def _call_claude_api(system_prompt: str, user_message: str) -> str:
    """调用 Claude API"""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "未配置 ANTHROPIC_API_KEY。请设置环境变量 ANTHROPIC_API_KEY 或创建 config.local.json 文件。\n"
            "在 config.local.json 中写入: {\"anthropic_api_key\": \"your-api-key\"}"
        )

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "temperature": 0.1,  # 低温度以获得更一致的输出
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message}
        ],
        # 禁用 thinking/reasoning 模式 (DeepSeek/Anthropic 均支持)
        # 日程解析任务不需要深度推理, 直接输出 JSON 更稳定
        "thinking": {"type": "disabled"},
    }

    resp = requests.post(
        f"{ANTHROPIC_BASE_URL}/v1/messages",
        headers=headers,
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # 提取文本内容 — 兼容多种 API 响应格式
    # Anthropic API: content[0] 直接是 {"type":"text", "text":"..."}
    # DeepSeek API: content[0] 可能是 {"type":"thinking", ...}, content[1] 是 {"type":"text", ...}
    content_blocks = data.get("content", [])

    # 优先找 type="text" 的块
    text_parts = []
    for block in content_blocks:
        if block.get("type") == "text" and "text" in block:
            text_parts.append(block["text"])

    if text_parts:
        return "".join(text_parts)

    # 如果没有 text 块，尝试从其他块兜底
    if content_blocks:
        first = content_blocks[0]
        if "text" in first:
            return first["text"]
        # DeepSeek thinking 模式: 只有 thinking 块, 尝试从中提取 JSON
        if first.get("type") == "thinking" and "thinking" in first:
            thinking_text = first["thinking"]
            # thinking 内容中可能包含 JSON 片段, 尝试提取
            import re as _re
            json_match = _re.search(r'\{[^{}]*"title"[^{}]*\}', thinking_text, _re.DOTALL)
            if not json_match:
                json_match = _re.search(r'\{[^{}]+\}', thinking_text, _re.DOTALL)
            if json_match:
                return json_match.group(0)
            # 如果提取不到JSON, 返回thinking内容本身
            return thinking_text
        # 其他可能的字段
        for key in ("content", "message", "output"):
            if key in first:
                return str(first[key])

    raise ValueError(
        f"无法从 API 响应中提取文本内容。\n"
        f"响应 content 块类型: {[b.get('type') for b in content_blocks]}\n"
        f"原始响应片段: {str(data)[:300]}"
    )


def _extract_json(text: str) -> dict:
    """从 Claude 响应中提取 JSON"""
    # 尝试直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试找到 {} 包裹的 JSON
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")


def _build_few_shot_text(samples: list) -> str:
    """将 few-shot 样本转换为提示文本"""
    if not samples:
        return ""

    lines = ["\n## 历史学习样本（请参考以下修正记录来改进解析）\n"]
    for i, sample in enumerate(samples, 1):
        raw = sample.get("raw_input", "")
        parsed = sample.get("parsed_result", {})
        correction = sample.get("user_correction")

        lines.append(f"### 样本 {i}")
        lines.append(f"原始输入: {raw}")
        lines.append(f"系统解析: {json.dumps(parsed, ensure_ascii=False)}")
        if correction:
            lines.append(f"用户修正为: {json.dumps(correction, ensure_ascii=False)}")
            lines.append(f"→ 请学习这个修正，优先参考用户修正的结果")
        lines.append("")

    return "\n".join(lines)


def parse(text: str, current_time: datetime,
          few_shot_samples: list = None) -> dict:
    """
    智能解析用户输入

    Args:
        text: 用户输入的自然语言文本
        current_time: 当前时间
        few_shot_samples: few-shot 学习样本列表

    Returns:
        解析后的结构化事件数据
    """
    if few_shot_samples is None:
        few_shot_samples = []

    # 构建当前时间描述
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_name = weekdays[current_time.weekday()]
    current_str = current_time.strftime("%Y年%m月%d日 %H:%M") + f" {weekday_name}"

    # 构建系统提示
    system_prompt = PARSE_SYSTEM_PROMPT.format(
        current_datetime=current_str,
        weekday_name=weekday_name,
    )

    # 附加 few-shot 样本
    few_shot_text = _build_few_shot_text(few_shot_samples)
    if few_shot_text:
        system_prompt += few_shot_text

    # 构建用户消息
    user_message = f"请解析以下日程描述：\n\n{text}"

    # 调用 Claude API
    try:
        response = _call_claude_api(system_prompt, user_message)
        result = _extract_json(response)

        # 确保必要字段存在
        result.setdefault("title", text[:50])
        result.setdefault("event_type", "other")
        result.setdefault("start_time", current_time.strftime("%Y-%m-%dT%H:%M:%S"))
        result.setdefault("end_time", None)
        result.setdefault("location", "")
        result.setdefault("description", text)
        result.setdefault("priority", 0)
        result.setdefault("tags", [])
        result.setdefault("source", "auto")

        return result

    except Exception as e:
        # 出错时进行本地基本解析作为兜底
        print(f"[WARN] Claude API 解析失败，使用本地兜底: {e}")
        return _fallback_parse(text, current_time)


def _fallback_parse(text: str, current_time: datetime) -> dict:
    """本地规则兜底解析 — 提取日期、时间、事件类型（不依赖 API）"""
    import jieba

    # === 1. 提取日期范围 ===
    start_dt, end_dt = _extract_date_range(text, current_time)

    # === 2. 提取具体时间点 ===
    hour, minute = _extract_time(text)
    if start_dt:
        start_dt = start_dt.replace(hour=hour, minute=minute)
    else:
        start_dt = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if end_dt:
        end_dt = end_dt.replace(hour=18, minute=0)  # 结束日默认18:00
    else:
        end_dt = start_dt.replace(hour=start_dt.hour + 1)

    # === 3. 事件类型推断 ===
    event_type = "other"
    job_indicators = JOB_KEYWORDS + ["面试", "笔试", "网申", "投递", "校招", "offer", "内推"]
    company_names = ["腾讯", "阿里", "字节", "华为", "美团", "百度", "京东", "网易",
                     "小米", "拼多多", "快手", "小红书", "哔哩哔哩", "滴滴", "蚂蚁"]

    if any(w in text for w in company_names):
        event_type = "job_search"
    elif any(w in text for w in ["面试", "笔试", "投递", "offer"]):
        event_type = "job_search"
    elif any(w in text for w in ["会议", "开会", "讨论", "见面"]):
        event_type = "meeting"
    elif any(w in text for w in ["学习", "看书", "上课", "课程", "刷题"]):
        event_type = "learning"
    elif any(w in text for w in ["截止", "不要忘", "提醒", "到期"]):
        event_type = "reminder"
    elif any(w in text for w in ["实习", "实训", "培训"]):
        event_type = "task"
    elif any(w in text for w in ["做", "写", "完成", "整理"]):
        event_type = "task"

    # === 4. 清理标题（去掉日期时间部分） ===
    title = _clean_title(text)

    # === 5. 优先级 ===
    priority = 0
    if event_type == "job_search" and any(w in text for w in ["面试", "笔试", "截止"]):
        priority = 3
    elif event_type == "meeting":
        priority = 2

    # === 6. 标签 ===
    words = list(jieba.cut(text))
    stopwords = {"的", "了", "在", "是", "我", "要", "去", "和", "与", "这", "那", "吗", "呢", "吧",
                 "进行", "一下", "参加", "记得", "需要", "可以"}
    tags = [w for w in words if len(w) >= 2 and w not in stopwords]
    tags = list(set(tags))[:8]

    return {
        "title": title[:50],
        "event_type": event_type,
        "start_time": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_time": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "location": "",
        "description": text,
        "priority": priority,
        "tags": tags,
        "source": "auto",
    }


def _extract_date_range(text: str, current_time: datetime) -> tuple:
    """
    从文本中提取日期范围

    支持格式:
    - "7.13-7.24" / "7.13-24" → (7/13, 7/24)
    - "7/14-7/23" / "7月14日-7月23日"
    - "6.25" → (6/25, None)
    - "下周三" / "明天" / "后天"
    - "周五前" / "本周五"

    Returns:
        (start_datetime, end_datetime) 或 (None, None)
    """
    yy = current_time.year

    # 1. 点分日期范围: "7.13-7.24" 或 "7.13-24"
    m = re.search(r'(\d{1,2})\.(\d{1,2})\s*[-~～至到]\s*(\d{1,2})\.(\d{1,2})', text)
    if m:
        m1, d1, m2, d2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (datetime(yy, m1, d1), datetime(yy, m2, d2))

    # 2. 同月点分日期: "7.13-24"
    m = re.search(r'(\d{1,2})\.(\d{1,2})\s*[-~～至到]\s*(\d{1,2})(?!\d*\.)', text)
    if m:
        month, d1, d2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (datetime(yy, month, d1), datetime(yy, month, d2))

    # 3. 斜杠日期范围: "7/14-7/23"
    m = re.search(r'(\d{1,2})/(\d{1,2})\s*[-~～至到]\s*(\d{1,2})/(\d{1,2})', text)
    if m:
        m1, d1, m2, d2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (datetime(yy, m1, d1), datetime(yy, m2, d2))

    # 4. 中文日期范围: "7月14日至7月23日" / "7月14日到7月23日"
    m = re.search(r'(\d{1,2})月(\d{1,2})[日号]?\s*(?:至|到|[-~～])\s*(\d{1,2})月(\d{1,2})[日号]?', text)
    if m:
        m1, d1, m2, d2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (datetime(yy, m1, d1), datetime(yy, m2, d2))

    # 5. 单日: "6.25" / "7/14"
    m = re.search(r'(?<!\d)(\d{1,2})[\./](\d{1,2})(?![\d\./])', text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (datetime(yy, month, day), None)

    # 6. 中文单日: "7月14日" / "7月14号"
    m = re.search(r'(\d{1,2})月(\d{1,2})[日号]', text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (datetime(yy, month, day), None)

    # 7. 相对日期: "明天" / "后天" / "大后天"
    relative_days = {
        "今天": 0, "明天": 1, "明日": 1, "后天": 2, "后日": 2,
        "大后天": 3, "大后日": 3,
    }
    for word, offset in relative_days.items():
        if word in text:
            return (current_time + timedelta(days=offset), None)

    # 8. 星期几: "下周三" / "本周五" / "周五"
    weekdays = {
        "周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6,
        "星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3, "星期五": 4, "星期六": 5, "星期日": 6,
    }
    for wd_name, wd_num in weekdays.items():
        if wd_name in text:
            # 判断是本周还是下周
            if "下" + wd_name in text or "下个" + wd_name in text:
                prefix = "下"
            elif "上" + wd_name in text or "上个" + wd_name in text:
                prefix = "上"
            elif "本" + wd_name in text:
                prefix = "本"
            else:
                prefix = "本"  # "周五" 默认本周

            current_wd = current_time.weekday()
            days_ahead = (wd_num - current_wd) % 7
            if prefix == "本":
                if days_ahead == 0:
                    days_ahead = 0  # 今天就是
            elif prefix == "下":
                days_ahead += 7  # 下周: 至少 +7 天
            else:  # 上
                days_ahead = days_ahead - 7  # 上周: 往前退
            target = current_time + timedelta(days=days_ahead)
            return (target, None)

    return (None, None)


def _extract_time(text: str) -> tuple:
    """
    从文本中提取具体时间

    Returns:
        (hour, minute) 默认 (9, 0)
    """
    # "下午3点" / "15:00" / "3pm" / "晚上8点"
    m = re.search(r'(上午|早上|中午|下午|傍晚|晚上|凌晨)?\s*(\d{1,2})[点:：](\d{1,2})?', text)
    if m:
        period = m.group(1) or ""
        hour = int(m.group(2))
        minute = int(m.group(3)) if m.group(3) else 0

        if "下午" in period and hour < 12:
            hour += 12
        elif "晚上" in period and hour < 12:
            hour += 12
        elif "中午" in period and hour < 12:
            hour = 12 if hour == 0 else hour
        elif "凌晨" in period:
            pass  # keep as-is

        return (hour, minute)

    # 纯数字时间: "15:30"
    m = re.search(r'(\d{1,2}):(\d{2})', text)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    return (9, 0)


def _clean_title(text: str) -> str:
    """从输入文本中清理出纯标题"""
    # 去除日期时间表达式
    cleaned = text
    # 去掉日期范围: "7.13-7.24" / "7/14-7/23" / "7月14日-7月23日"
    cleaned = re.sub(r'\d{1,2}[\./]\d{1,2}\s*[-~～至到]\s*\d{1,2}[\./]\d{1,2}', '', cleaned)
    cleaned = re.sub(r'\d{1,2}[\./]\d{1,2}\s*[-~～至到]\s*\d{1,2}(?!\d)', '', cleaned)
    cleaned = re.sub(r'\d{1,2}月\d{1,2}[日号]?\s*(?:至|到|[-~])\s*\d{1,2}月\d{1,2}[日号]?', '', cleaned)
    # 去掉单日: "6.25" / "7/14"
    cleaned = re.sub(r'(?<!\d)\d{1,2}[\./]\d{1,2}(?!\d)', '', cleaned)
    cleaned = re.sub(r'\d{1,2}月\d{1,2}[日号]', '', cleaned)
    # 去掉时间: "下午3点" / "15:00"
    cleaned = re.sub(r'(上午|早上|中午|下午|傍晚|晚上|凌晨)?\s*\d{1,2}[点:：]\d{0,2}[分]?', '', cleaned)
    cleaned = re.sub(r'\d{1,2}:\d{2}', '', cleaned)
    # 去掉相对日期词（含"前"后缀）
    cleaned = re.sub(r'(今天|明天|明日|后天|大后天|下个月)', '', cleaned)
    cleaned = re.sub(r'(下?个?\s*(?:周[一二三四五六日]|星期[一二三四五六日]|周一|周二|周三|周四|周五|周六|周日))\s*前?', '', cleaned)
    # 去掉前缀连接词
    cleaned = re.sub(r'^(进行|参加|记得|需要|去|要|做|开始)\s*', '', cleaned)
    # 压缩空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned if cleaned else text[:50]


def classify_event_type(text: str) -> str:
    """快速分类事件类型（本地规则，无需 API）"""
    import jieba
    words = set(jieba.cut(text))

    company_words = {"腾讯", "阿里", "字节", "华为", "美团", "百度", "京东", "网易",
                     "小米", "拼多多", "快手", "小红书", "哔哩哔哩", "滴滴", "蚂蚁", "微软", "谷歌"}
    job_words = {"校招", "面试", "笔试", "offer", "投递", "内推", "网申", "春招", "秋招"}

    if words & company_words or words & job_words:
        return "job_search"
    if words & {"会议", "开会", "讨论", "见面", "约"}:
        return "meeting"
    if words & {"学习", "看书", "上课", "课程", "刷题"}:
        return "learning"
    if words & {"截止", "提醒", "到期", "不要忘"}:
        return "reminder"

    return "task"
