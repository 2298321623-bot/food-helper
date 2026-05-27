"""食材库存：数量解析、名称匹配、做菜后扣减。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

def _normalize_ingredient(name: str) -> str:
    name = (name or "").strip()
    aliases = {
        "西红柿": "番茄",
        "蕃茄": "番茄",
        "西兰花": "西蓝花",
        "花菜": "菜花",
    }
    return aliases.get(name, name)


@dataclass
class DeductionRow:
    """扣减计划中的一行。"""

    recipe_ingredient: str
    pantry_index: Optional[int] = None
    pantry_name: str = ""
    deduct_amount: float = 0.0
    unit: str = ""
    current_amount: float = 0.0
    remaining_after: float = 0.0
    matched: bool = False
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class DeductionSummary:
    deducted_count: int = 0
    removed_count: int = 0
    skipped_count: int = 0


def match_ingredient_name(pantry_name: str, recipe_name: str) -> bool:
    return _normalize_ingredient(pantry_name) == _normalize_ingredient(recipe_name)


def format_amount_display(amount: float, unit: str) -> str:
    if amount == int(amount):
        amount_str = str(int(amount))
    else:
        amount_str = f"{amount:g}"
    return f"{amount_str} {unit}".strip()


def parse_amount_text(text: str) -> float:
    """解析用户输入的数量字符串。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("数量不能为空")
    value = float(text)
    if value <= 0:
        raise ValueError("数量必须大于 0")
    return value


def parse_legacy_quantity(text: str) -> Tuple[float, str]:
    """将旧版「数量/单位」合并字符串解析为 (amount, unit)。"""
    text = (text or "").strip()
    if not text:
        return 1.0, "个"
    m = re.match(r"^([\d.]+)\s*(.*)$", text)
    if m:
        amount = float(m.group(1))
        unit = (m.group(2) or "个").strip() or "个"
        return amount, unit
    return 1.0, text


def normalize_pantry_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """确保食材条目含 amount / unit（兼容旧 quantity 字段）。"""
    if "amount" in item and "unit" in item:
        return item
    if "quantity" in item:
        amount, unit = parse_legacy_quantity(str(item["quantity"]))
        item = {**item, "amount": amount, "unit": unit}
        item.pop("quantity", None)
    return item


def find_pantry_index(pantry: List[Dict[str, Any]], recipe_name: str) -> Optional[int]:
    for i, item in enumerate(pantry):
        if match_ingredient_name(item.get("name", ""), recipe_name):
            return i
    return None


def _parse_recipe_ingredient_names(recipe: Dict[str, Any]) -> List[str]:
    raw = recipe.get("ingredients") or []
    names: List[str] = []
    for ing in raw:
        if isinstance(ing, str):
            names.append(ing.strip())
        elif isinstance(ing, dict):
            names.append(str(ing.get("name", "")).strip())
    return [n for n in names if n]


def plan_deductions(
    recipe_ingredient_names: List[str],
    pantry: List[Dict[str, Any]],
    servings: float,
    default_per_ingredient: float = 1.0,
) -> List[DeductionRow]:
    """
    生成扣减计划。同名菜谱食材合并为一行；每种冰箱食材只匹配一次。
    默认扣减 = default_per_ingredient × servings。
    """
    pantry = [normalize_pantry_item(dict(p)) for p in pantry]
    servings = max(0.0, float(servings))
    default_deduct = default_per_ingredient * servings

    # 合并同名菜谱食材（归一化后）
    merged: Dict[str, float] = {}
    for name in recipe_ingredient_names:
        key = _normalize_ingredient(name)
        if not key:
            continue
        merged[key] = merged.get(key, 0.0) + default_deduct

    # 保留展示用原名
    display_names: Dict[str, str] = {}
    for name in recipe_ingredient_names:
        key = _normalize_ingredient(name)
        if key and key not in display_names:
            display_names[key] = name

    used_pantry: set = set()
    rows: List[DeductionRow] = []

    for key, total_deduct in merged.items():
        display = display_names.get(key, key)
        idx = None
        for i, item in enumerate(pantry):
            if i in used_pantry:
                continue
            if _normalize_ingredient(item.get("name", "")) == key:
                idx = i
                break

        if idx is None:
            rows.append(
                DeductionRow(
                    recipe_ingredient=display,
                    matched=False,
                    skipped=True,
                    skip_reason="冰箱无此食材",
                )
            )
            continue

        used_pantry.add(idx)
        item = pantry[idx]
        amount = float(item.get("amount", 0))
        unit = str(item.get("unit", "个"))
        deduct = min(total_deduct, amount) if total_deduct > 0 else 0.0
        remaining = max(0.0, amount - total_deduct)

        rows.append(
            DeductionRow(
                recipe_ingredient=display,
                pantry_index=idx,
                pantry_name=item.get("name", ""),
                deduct_amount=total_deduct,
                unit=unit,
                current_amount=amount,
                remaining_after=remaining,
                matched=True,
            )
        )

    return rows


def apply_deductions(
    pantry: List[Dict[str, Any]],
    plan: List[DeductionRow],
) -> Tuple[List[Dict[str, Any]], DeductionSummary]:
    """按确认后的计划扣减库存；扣到 0 及以下则删除。"""
    pantry = [normalize_pantry_item(dict(p)) for p in pantry]
    summary = DeductionSummary()
    indices_to_remove: List[int] = []

    for row in plan:
        if not row.matched or row.skipped or row.pantry_index is None:
            if row.skipped or not row.matched:
                summary.skipped_count += 1
            continue
        if row.deduct_amount <= 0:
            continue

        idx = row.pantry_index
        if idx < 0 or idx >= len(pantry):
            continue

        item = pantry[idx]
        current = float(item.get("amount", 0))
        new_amount = current - row.deduct_amount

        if new_amount <= 1e-9:
            indices_to_remove.append(idx)
            summary.removed_count += 1
        else:
            item["amount"] = round(new_amount, 4)
            summary.deducted_count += 1

    for idx in sorted(set(indices_to_remove), reverse=True):
        del pantry[idx]

    return pantry, summary


def recipe_ingredients_from_dict(recipe: Optional[Dict[str, Any]]) -> List[str]:
    if not recipe:
        return []
    return _parse_recipe_ingredient_names(recipe)
