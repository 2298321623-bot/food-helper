"""
菜谱检索与生成服务（组员 C Week1–Week2 对外接口）。
组员 A：QThreadPool 调用 search_* / generate_recipe_text。
组员 B：load_from_db(recipes) 注入数据库菜谱。
"""
import logging
from typing import Any, Dict, List, Optional

from fallback.llm import generate_recipe_with_fallback, get_llm
from rag.core import RecipeRetriever

logger = logging.getLogger(__name__)

_instance: Optional["RecipeService"] = None


def _to_ui_recipe(r: Dict[str, Any]) -> Dict[str, Any]:
    """统一为 UI 可用的字段结构。"""
    return {
        "name": r.get("name", ""),
        "tags": r.get("tags", []),
        "time": r.get("time", r.get("cooking_time", "")),
        "diff": r.get("diff", r.get("difficulty", "")),
        "ingredients": r.get("ingredients", []),
        "description": r.get("description", ""),
        "steps": r.get("steps", []),
        "match_score": r.get("match_score"),
        "matched_ingredients": r.get("matched_ingredients", []),
        "missing_ingredients": r.get("missing_ingredients", []),
        "preference_match": r.get("preference_match"),
        "_raw": r,
    }


class RecipeService:
    def __init__(self):
        self.retriever = RecipeRetriever.from_json()

    def search_by_ingredients(
        self,
        ingredient_names: List[str],
        top_k: int = 10,
        min_score: float = 0.1,
        prefer_fully_available: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        模式1：用现有食材做菜（Week2 增强缺料优先排序）。
        prefer_fully_available=True 时仅返回食材齐备的菜谱。
        """
        if prefer_fully_available:
            raw = self.retriever.search_fully_available(ingredient_names, top_k=top_k)
        else:
            raw = self.retriever.search_by_ingredients(
                ingredient_names, top_k=top_k, min_score=min_score
            )
        return [_to_ui_recipe(r) for r in raw if r.get("name")]

    def search_by_preferences(
        self,
        diet: str = "",
        cooking_time: str = "",
        difficulty: str = "",
        top_k: int = 10,
        min_score: float = 0.2,
    ) -> List[Dict[str, Any]]:
        """模式2：按需求做菜（Week2）。"""
        raw = self.retriever.search_by_preferences(
            diet=diet,
            cooking_time=cooking_time,
            difficulty=difficulty,
            top_k=top_k,
            min_score=min_score,
        )
        return [_to_ui_recipe(r) for r in raw if r.get("name")]

    def load_from_db(self, recipes: List[Dict[str, Any]]):
        """组员 B：从 db.py 查询结果注入后重建向量。"""
        self.retriever.load_recipes(recipes, rebuild_embeddings=True)

    def generate_recipe_text(
        self,
        ingredient_names: List[str],
        extra_requirements: str = "",
        recipe_name: str = "",
        diet: str = "",
        cooking_time: str = "",
        difficulty: str = "",
    ) -> str:
        """
        Week2：RAG 检索 + 双引擎生成完整菜谱（本地优先，失败切 DeepSeek）。
        """
        requirements_parts = []
        if diet:
            requirements_parts.append(f"饮食偏好：{diet}")
        if cooking_time:
            requirements_parts.append(f"烹饪时间：{cooking_time}")
        if difficulty:
            requirements_parts.append(f"难度：{difficulty}")
        if extra_requirements:
            requirements_parts.append(extra_requirements)
        merged_req = "；".join(requirements_parts) if requirements_parts else ""

        matches = self.search_by_ingredients(ingredient_names, top_k=3)
        hint = ""
        name = recipe_name
        if matches:
            top = matches[0]
            if not name:
                name = top.get("name", "")
            steps = top.get("steps") or []
            steps_text = "；".join(steps[:5]) if steps else ""
            hint = (
                f"参考菜名：{top.get('name')}；"
                f"简介：{top.get('description', '')}；"
                f"参考步骤：{steps_text}"
            )

        return generate_recipe_with_fallback(
            ingredient_names,
            reference_hint=hint,
            extra_requirements=merged_req,
            recipe_name=name,
        )

    def llm_status(self) -> Dict[str, str]:
        """返回当前可用引擎，供 UI 展示。"""
        from llm.cloud_llm import CloudLLM
        from llm.local_llm import LocalLLM

        local = LocalLLM()
        cloud = CloudLLM()
        if local.is_available():
            engine = "local"
        elif cloud.is_available():
            engine = "cloud"
        else:
            engine = "none"
        try:
            get_llm()
            ready = True
        except RuntimeError:
            ready = False
        return {
            "engine": engine,
            "local": str(local.is_available()),
            "cloud": str(cloud.is_available()),
            "ready": str(ready),
        }


def get_recipe_service() -> RecipeService:
    global _instance
    if _instance is None:
        _instance = RecipeService()
    return _instance
