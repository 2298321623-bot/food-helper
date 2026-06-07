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


def _rule_based_parse(text: str) -> List[ParsedShoppingItem]:
    """基于规则的快速解析。"""
    items = []
    
    # 模式1：「买/需要/要 + 数量 + 单位 + 食材名」
    # 例如：「买 3 斤 猪肉」、「需要 2 个 鸡蛋」、「要 500 克 番茄」
    pattern1 = re.compile(
        r'(?:买|需要|要|准备|加)\s*'
        r'([\d.]+)\s*'
        r'(' + '|'.join(UNIT_MAP.keys()) + r')\s*'
        r'([\u4e00-\u9fff]+(?:[\u4e00-\u9fff]+)?)'
    )
    for m in pattern1.finditer(text):
        items.append(ParsedShoppingItem(
            name=m.group(3).strip(),
            quantity=m.group(1),
            unit=m.group(2),
        ))
    
    # 模式2：「数量 + 单位 + 食材名」（无动词）
    # 例如：「3 斤 猪肉」、「2 个 鸡蛋」
    if not items:
        pattern2 = re.compile(
            r'([\d.]+)\s*'
            r'(' + '|'.join(UNIT_MAP.keys()) + r')\s*'
            r'([\u4e00-\u9fff]+(?:[\u4e00-\u9fff]+)?)'
        )
        for m in pattern2.finditer(text):
            items.append(ParsedShoppingItem(
                name=m.group(3).strip(),
                quantity=m.group(1),
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