"""库存扣减逻辑轻量测试。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util

_name = "inventory_service_test"
_spec = importlib.util.spec_from_file_location(
    _name, ROOT / "services" / "inventory_service.py"
)
_inv = importlib.util.module_from_spec(_spec)
sys.modules[_name] = _inv
_spec.loader.exec_module(_inv)
apply_deductions = _inv.apply_deductions
plan_deductions = _inv.plan_deductions


def test_plan_and_apply_two_servings():
    pantry = [
        {"name": "鸡蛋", "amount": 3.0, "unit": "个"},
        {"name": "番茄", "amount": 2.0, "unit": "个"},
    ]
    plan = plan_deductions(["鸡蛋", "番茄"], pantry, servings=2)
    assert len(plan) == 2
    assert all(r.matched for r in plan)
    assert plan[0].deduct_amount == 2.0

    pantry, summary = apply_deductions(pantry, plan)
    assert len(pantry) == 1
    assert pantry[0]["name"] == "鸡蛋"
    assert pantry[0]["amount"] == 1.0
    assert summary.removed_count == 1
    assert summary.deducted_count == 1


def test_unmatched_ingredient():
    pantry = [{"name": "鸡蛋", "amount": 1.0, "unit": "个"}]
    plan = plan_deductions(["鸡蛋", "龙虾"], pantry, servings=1)
    assert any(not r.matched for r in plan)
    pantry, summary = apply_deductions(pantry, plan)
    assert len(pantry) == 0
    assert summary.removed_count == 1


if __name__ == "__main__":
    test_plan_and_apply_two_servings()
    test_unmatched_ingredient()
    print("OK")
