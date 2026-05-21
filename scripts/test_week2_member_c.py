"""组员 C 第二周任务自测脚本。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_ingredient_priority_ranking():
    from services.recipe_service import get_recipe_service

    svc = get_recipe_service()
    results = svc.search_by_ingredients(["鸡蛋", "番茄", "盐", "油"], top_k=5)
    assert results, "检索结果为空"
    top = results[0]
    assert top["name"] == "番茄炒蛋", f"期望番茄炒蛋优先，实际 Top1={top['name']}"
    assert not top.get("missing_ingredients"), "齐备食材应排在缺料菜谱之前"
    print(f"[OK] 有限食材优先：Top1={top['name']} 得分={top['match_score']}")


def test_preference_search():
    from services.recipe_service import get_recipe_service

    svc = get_recipe_service()
    results = svc.search_by_preferences(
        diet="减脂餐", cooking_time="15分钟内", difficulty="简单", top_k=5
    )
    assert results, "按需求检索为空"
    names = [r["name"] for r in results]
    assert any("西蓝花" in n or "香菇" in n for n in names), names
    print(f"[OK] 按需求检索 Top1：{results[0]['name']} 得分={results[0]['match_score']}")


def test_dual_engine_factory():
    from fallback.llm import get_llm
    from llm.cloud_llm import CloudLLM
    from llm.local_llm import LocalLLM

    llm = get_llm()
    assert isinstance(llm, (LocalLLM, CloudLLM))
    print(f"[OK] get_llm() -> {type(llm).__name__}")


def test_generate_recipe_local():
    from services.recipe_service import get_recipe_service

    svc = get_recipe_service()
    status = svc.llm_status()
    if status["ready"] != "True":
        print("[SKIP] 无可用 LLM，跳过生成测试")
        return
    text = svc.generate_recipe_text(
        ["鸡蛋", "番茄"],
        recipe_name="番茄炒蛋",
        diet="家常菜",
        cooking_time="15分钟内",
        difficulty="简单",
    )
    assert "##" in text or "菜名" in text or len(text) > 80
    print(f"[OK] 生成菜谱（{status['engine']}）长度={len(text)} 字")


def test_cloud_llm_optional():
    from llm.cloud_llm import CloudLLM

    cloud = CloudLLM()
    if not cloud.is_available():
        print("[SKIP] 未设置 DEEPSEEK_API_KEY，跳过云端 API 实测")
        return
    text = cloud.generate("用一句话说番茄炒蛋的特点。", max_tokens=60)
    assert len(text) > 5
    print(f"[OK] CloudLLM：{text[:80]}...")


def main():
    print("=== 组员 C Week2 自测 ===\n")
    test_ingredient_priority_ranking()
    test_preference_search()
    test_dual_engine_factory()
    test_generate_recipe_local()
    test_cloud_llm_optional()
    print("\n=== Week2 自测完成 ===")


if __name__ == "__main__":
    main()
