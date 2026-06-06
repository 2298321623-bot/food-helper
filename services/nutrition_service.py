"""冰箱库存营养估算服务。

数据按常见食材每 100g 粗略估算，适合家庭库存统计和课程演示，
不是医疗或精确配餐依据。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from services.inventory_service import format_amount_display, normalize_pantry_item


# 每 100g 可食部估算：热量 kcal、蛋白质 g、碳水 g、脂肪 g。
NUTRITION_PER_100G: Dict[str, Dict[str, float]] = {
    "鸡蛋": {"calories": 143, "protein": 13.0, "carbs": 1.1, "fat": 9.5},
    "番茄": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2},
    "西红柿": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2},
    "土豆": {"calories": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1},
    "牛肉": {"calories": 250, "protein": 26.0, "carbs": 0.0, "fat": 15.0},
    "猪肉": {"calories": 242, "protein": 27.0, "carbs": 0.0, "fat": 14.0},
    "鸡肉": {"calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6},
    "虾仁": {"calories": 99, "protein": 24.0, "carbs": 0.2, "fat": 0.3},
    "三文鱼": {"calories": 208, "protein": 20.0, "carbs": 0.0, "fat": 13.0},
    "西蓝花": {"calories": 34, "protein": 2.8, "carbs": 6.6, "fat": 0.4},
    "胡萝卜": {"calories": 41, "protein": 0.9, "carbs": 9.6, "fat": 0.2},
    "青菜": {"calories": 15, "protein": 1.5, "carbs": 2.7, "fat": 0.2},
    "生菜": {"calories": 15, "protein": 1.4, "carbs": 2.9, "fat": 0.2},
    "牛油果": {"calories": 160, "protein": 2.0, "carbs": 8.5, "fat": 14.7},
    "豆腐": {"calories": 76, "protein": 8.0, "carbs": 1.9, "fat": 4.8},
    "米饭": {"calories": 116, "protein": 2.6, "carbs": 25.9, "fat": 0.3},
    "面条": {"calories": 137, "protein": 4.5, "carbs": 25.0, "fat": 2.1},
    "白菜": {"calories": 17, "protein": 1.5, "carbs": 3.2, "fat": 0.1},
    "黄瓜": {"calories": 16, "protein": 0.7, "carbs": 3.6, "fat": 0.1},
    "洋葱": {"calories": 40, "protein": 1.1, "carbs": 9.3, "fat": 0.1},
    "蒜": {"calories": 149, "protein": 6.4, "carbs": 33.1, "fat": 0.5},
    "葱": {"calories": 32, "protein": 1.8, "carbs": 7.3, "fat": 0.2},
    "姜": {"calories": 80, "protein": 1.8, "carbs": 17.8, "fat": 0.8},
}


# 未知食材按单位估重；已知食材会优先使用 PIECE_WEIGHTS。
UNIT_TO_GRAMS: Dict[str, float] = {
    "克": 1.0,
    "千克": 1000.0,
    "斤": 500.0,
    "两": 50.0,
    "毫升": 1.0,
    "升": 1000.0,
    "个": 100.0,
    "只": 100.0,
    "根": 80.0,
    "片": 15.0,
    "条": 120.0,
    "份": 200.0,
    "包": 250.0,
    "袋": 250.0,
    "盒": 300.0,
    "瓶": 500.0,
    "罐": 350.0,
}


PIECE_WEIGHTS: Dict[str, float] = {
    "鸡蛋": 50.0,
    "番茄": 150.0,
    "西红柿": 150.0,
    "土豆": 200.0,
    "胡萝卜": 120.0,
    "黄瓜": 180.0,
    "洋葱": 180.0,
    "牛油果": 170.0,
}


ALIASES: Dict[str, str] = {
    "西红柿": "番茄",
    "小青菜": "青菜",
    "虾": "虾仁",
    "蒜头": "蒜",
    "大蒜": "蒜",
}


def normalize_food_name(name: str) -> str:
    cleaned = (name or "").strip()
    return ALIASES.get(cleaned, cleaned)


def estimate_weight_grams(name: str, amount: float, unit: str) -> Tuple[float, str]:
    canonical = normalize_food_name(name)
    if unit in {"个", "只", "根", "条"} and canonical in PIECE_WEIGHTS:
        return amount * PIECE_WEIGHTS[canonical], f"按每{unit}约 {PIECE_WEIGHTS[canonical]:g}g 估算"
    factor = UNIT_TO_GRAMS.get(unit)
    if factor is None:
        return amount * 100.0, f"未知单位「{unit}」，按每单位 100g 估算"
    if unit in {"个", "只", "根", "片", "条", "份", "包", "袋", "盒", "瓶", "罐"}:
        return amount * factor, f"按每{unit}约 {factor:g}g 估算"
    return amount * factor, ""


def estimate_ingredient_nutrition(item: dict) -> dict:
    pantry_item = normalize_pantry_item(dict(item))
    name = pantry_item["name"]
    amount = float(pantry_item.get("amount", 0) or 0)
    unit = str(pantry_item.get("unit", "个") or "个")
    canonical = normalize_food_name(name)
    grams, weight_note = estimate_weight_grams(canonical, amount, unit)
    per100 = NUTRITION_PER_100G.get(canonical)

    row = {
        "name": name,
        "canonical_name": canonical,
        "amount_display": format_amount_display(amount, unit),
        "grams": round(grams, 1),
        "calories": 0.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 0.0,
        "recognized": per100 is not None,
        "note": weight_note,
    }
    if per100 is None:
        row["note"] = (weight_note + "；" if weight_note else "") + "缺少营养数据"
        return row

    multiplier = grams / 100.0
    for key in ("calories", "protein", "carbs", "fat"):
        row[key] = round(float(per100[key]) * multiplier, 1)
    return row


def summarize_pantry_nutrition(ingredients: Iterable[dict]) -> dict:
    rows: List[dict] = [estimate_ingredient_nutrition(item) for item in ingredients]
    totals = {
        "grams": round(sum(row["grams"] for row in rows), 1),
        "calories": round(sum(row["calories"] for row in rows), 1),
        "protein": round(sum(row["protein"] for row in rows), 1),
        "carbs": round(sum(row["carbs"] for row in rows), 1),
        "fat": round(sum(row["fat"] for row in rows), 1),
    }
    recognized_count = sum(1 for row in rows if row["recognized"])
    return {
        "totals": totals,
        "rows": rows,
        "recognized_count": recognized_count,
        "unrecognized_count": len(rows) - recognized_count,
    }
