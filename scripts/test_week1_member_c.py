"""组员 C 第一周任务自测脚本。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_llama_cpp_import():
    import llama_cpp  # noqa: F401

    print("[OK] llama-cpp-python 已安装")


def test_embedding_and_similarity():
    from rag.embeddings import EmbeddingService, cosine_similarity

    svc = EmbeddingService()
    v1 = svc.encode("番茄 鸡蛋")[0]
    v2 = svc.encode("西红柿炒蛋")[0]
    sim = cosine_similarity(v1, v2)
    assert sim > 0.3, f"相似度过低: {sim}"
    print(f"[OK] 向量维度={len(v1)}，番茄/西红柿炒蛋 相似度={sim:.4f}")


def test_recipe_retrieval():
    from services.recipe_service import get_recipe_service

    svc = get_recipe_service()
    # 模拟冰箱：有鸡蛋、番茄，缺盐油 → 应匹配番茄炒蛋、西红柿鸡蛋汤等
    results = svc.search_by_ingredients(["鸡蛋", "番茄"], top_k=5)
    assert results, "检索结果为空"
    names = [r["name"] for r in results]
    assert any("番茄" in n or "西红柿" in n for n in names), names
    top = results[0]
    print(f"[OK] 检索 Top1：{top['name']} 得分={top['match_score']}")
    print(f"     已匹配食材：{top.get('matched_ingredients')}")
    print(f"     缺少食材：{top.get('missing_ingredients')}")


def test_local_llm():
    from llm.local_llm import LocalLLM

    llm = LocalLLM()
    if not llm.is_available():
        print("[SKIP] 本地 GGUF 未下载，运行 python scripts/download_qwen_model.py")
        return
    text = llm.generate("用一句话介绍番茄炒蛋。", max_tokens=80)
    assert len(text) > 5
    print(f"[OK] LocalLLM 生成：{text[:120]}...")


def main():
    print("=== 组员 C Week1 自测 ===\n")
    test_llama_cpp_import()
    test_embedding_and_similarity()
    test_recipe_retrieval()
    test_local_llm()
    print("\n=== 全部必测项通过（LLM 未下载则跳过最后一项）===")


if __name__ == "__main__":
    main()
