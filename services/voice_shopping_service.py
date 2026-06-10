# services/voice_shopping_service.py
"""语音购物清单解析服务 — 语音输入 → LLM 结构化 → 自动填入购物清单。"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fallback.llm import get_llm

logger = logging.getLogger(__name__)

# 常见单位映射
UNIT_MAP = {
    "个": "个", "只": "只", "根": "根", "片": "片", "条": "条",
    "克": "克", "千克": "千克", "斤": "斤", "两": "两",
    "毫升": "毫升", "升": "升",
    "包": "包", "袋": "袋", "盒": "盒", "瓶": "瓶", "罐": "罐",
    "把": "把", "颗": "颗", "粒": "粒", "块": "块", "碗": "碗",
}

DEFAULT_UNIT = "个"
DEFAULT_QUANTITY = "1"

# 中文数字 → 阿拉伯数字（覆盖常见购物口语数字）
CN_NUM_MAP = {
    "零": 0, "〇": 0,
    "一": 1, "壹": 1, "二": 2, "贰": 2, "两": 2, "俩": 2,
    "三": 3, "叁": 3, "四": 4, "肆": 4, "五": 5, "伍": 5,
    "六": 6, "陆": 6, "七": 7, "柒": 7, "八": 8, "捌": 8,
    "九": 9, "玖": 9, "十": 10, "拾": 10,
    "半": 0.5,
}


def _cn_number_to_float(text: str) -> Optional[float]:
    """把简单中文数字串（如 一、两、十、十二、二十、二十三、半）转为 float。"""
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    # 优先尝试阿拉伯数字
    try:
        return float(text)
    except ValueError:
        pass
    if text == "半":
        return 0.5
    # 形如 "十"、"十X"、"X十"、"X十Y"
    if "十" in text or "拾" in text:
        t = text.replace("拾", "十")
        if t == "十":
            return 10.0
        if t.startswith("十"):  # 十X
            tail = CN_NUM_MAP.get(t[1:], None)
            return 10.0 + tail if tail is not None else None
        parts = t.split("十", 1)
        head = CN_NUM_MAP.get(parts[0], None)
        if head is None:
            return None
        if not parts[1]:
            return head * 10.0
        tail = CN_NUM_MAP.get(parts[1], None)
        return head * 10.0 + tail if tail is not None else None
    # 单个中文数字
    if len(text) == 1 and text in CN_NUM_MAP:
        return float(CN_NUM_MAP[text])
    return None


# 中文数字字符（用于在正则中匹配数量）
_CN_DIGIT_CHARS = "零〇一壹二贰两俩三叁四肆五伍六陆七柒八捌九玖十拾半"
# 数量匹配片段：阿拉伯数字 或 中文数字串（1~3 个字符，足够覆盖 一/两/十/二十三 等）
NUM_PATTERN = rf"(?:[\d]+(?:\.\d+)?|[{_CN_DIGIT_CHARS}]{{1,3}})"


@dataclass
class ParsedShoppingItem:
    """解析后的购物项。"""
    name: str
    quantity: str = DEFAULT_QUANTITY
    unit: str = DEFAULT_UNIT


def parse_voice_to_shopping_list(
    voice_text: str,
    use_llm: bool = True,
) -> List[ParsedShoppingItem]:
    """
    将语音识别文本解析为购物清单项目。
    
    流程：
    1. 先用规则解析（快速，覆盖常见模式）
    2. 如果规则解析失败或结果为空，调用 LLM 进行智能解析
    """
    voice_text = (voice_text or "").strip()
    if not voice_text:
        return []
    
    # 阶段1：规则解析
    items = _rule_based_parse(voice_text)
    
    # 阶段2：规则解析失败时，调用 LLM
    if (not items or len(items) == 0) and use_llm:
        logger.info("规则解析未命中，调用 LLM 智能解析")
        items = _llm_parse(voice_text)
    
    return items


def _normalize_quantity(q: str) -> str:
    """把中文数字数量统一成阿拉伯数字字符串。"""
    val = _cn_number_to_float(q)
    if val is None:
        return q
    return str(int(val)) if val == int(val) else str(val)


def _rule_based_parse(text: str) -> List[ParsedShoppingItem]:
    """基于规则的快速解析（支持中文数字与阿拉伯数字、可识别多项）。"""
    items = []
    unit_alt = '|'.join(UNIT_MAP.keys())

    # 通用模式：可选动词 + 数量 + 单位 + 食材名（食材名贪婪 2~6 字）
    # 例如：「买两斤猪肉」「3 斤 猪肉」「两个鸡蛋一斤猪肉」「需要 2 个鸡蛋」
    pattern = re.compile(
        r'(?:买|需要|要|准备|加|添加)?\s*'
        r'(' + NUM_PATTERN + r')\s*'
        r'(' + unit_alt + r')\s*'
        r'([\u4e00-\u9fff]{1,6}?)'
        r'(?=(?:' + NUM_PATTERN + r')\s*(?:' + unit_alt + r')|[，,、和及与。.！!？?\s]|$)'
    )
    for m in pattern.finditer(text):
        name = m.group(3).strip()
        if not name:
            continue
        items.append(ParsedShoppingItem(
            name=name,
            quantity=_normalize_quantity(m.group(1)),
            unit=m.group(2),
        ))
    
    # 模式3：逗号/顿号分隔的纯食材名列表
    # 例如：「鸡蛋，番茄，盐，油」
    if not items:
        parts = re.split(r'[，,、和及与]', text)
        for part in parts:
            part = part.strip()
            # 去除「买」「需要」等前缀
            part = re.sub(r'^(?:帮我?买|我需要?|我要?|准备|加)\s*', '', part)
            if part:
                items.append(ParsedShoppingItem(name=part))
    
    return items


def _llm_parse(text: str) -> List[ParsedShoppingItem]:
    """调用 LLM 智能解析语音文本为购物清单。"""
    system_prompt = """你是一个购物清单解析助手。请将用户的语音输入解析为结构化的购物清单。

请严格按以下 JSON 格式输出，不要输出其他内容：
[
  {"name": "食材名", "quantity": "数量", "unit": "单位"},
  ...
]

单位可选：个、只、根、片、条、克、千克、斤、两、毫升、升、包、袋、盒、瓶、罐、把、颗、粒、块、碗
如果用户没有说数量，默认为 "1"；如果没有说单位，默认为 "个"。
只输出 JSON 数组，不要输出其他解释。"""

    user_prompt = f"请解析以下语音输入为购物清单：\n{text}"

    try:
        llm = get_llm()
        result = llm.generate(user_prompt, system=system_prompt, max_tokens=256)

        # 提取输出中的 JSON 数组（兼容前后有多余文字的情况）
        json_match = re.search(r'\[.*?\]', result, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            items = []
            for item in parsed:
                name = str(item.get("name", "")).strip()
                if name:
                    items.append(ParsedShoppingItem(
                        name=name,
                        quantity=str(item.get("quantity", DEFAULT_QUANTITY)),
                        unit=str(item.get("unit", DEFAULT_UNIT)),
                    ))
            return items
    except Exception as e:
        logger.warning("LLM 解析失败: %s", e)

    return []


def voice_text_to_shopping_items(
    voice_text: str,
    existing_items: List[Dict[str, Any]] = None,
    use_llm: bool = True,
) -> List[Dict[str, Any]]:
    """
    将语音文本转换为购物清单格式（与 UI 兼容）。
    
    返回格式：[{"name": "...", "quantity": "...", "unit": "...", "bought": False}, ...]
    """
    parsed = parse_voice_to_shopping_list(voice_text, use_llm=use_llm)
    
    # 去重：与已有购物清单合并
    existing_names = {
        item["name"] for item in (existing_items or [])
    }
    
    result = []
    for item in parsed:
        if item.name not in existing_names:
            result.append({
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "bought": False,
            })
    
    return result