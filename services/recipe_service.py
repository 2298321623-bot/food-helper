"""
菜谱检索与生成服务（组员 C Week1–Week2 对外接口）。
组员 A：QThreadPool 调用 search_* / generate_recipe_text。
组员 B：load_from_db(recipes) 注入数据库菜谱。
"""
import json
import logging
import re
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

    def brainstorm_recipe_ideas(
        self,
        ingredient_names: List[str],
        diet: str = "",
        cooking_time: str = "",
        difficulty: str = "",
        exclude: List[str] = None,
        top_k: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        让 LLM 在 RAG 命中之外，再创意推荐若干道菜（仅返回简要信息），
        用于在菜谱列表中补充不局限于本地菜谱库的新颖选择。
        """
        ingredients_txt = "、".join(ingredient_names) if ingredient_names else "不限"
        exclude_txt = "、".join(exclude) if exclude else "无"
        prefs = []
        if diet:
            prefs.append(f"偏好：{diet}")
        if cooking_time:
            prefs.append(f"耗时：{cooking_time}")
        if difficulty:
            prefs.append(f"难度：{difficulty}")
        pref_txt = "；".join(prefs) if prefs else "无特殊偏好"

        system_prompt = (
            "你是一名经验丰富的家常菜厨师，擅长根据用户现有食材给出有创意又落地的菜谱推荐。"
            "请严格按 JSON 数组返回，不要输出其它内容。"
        )
        user_prompt = (
            f"请基于以下食材给出 {top_k} 道菜谱推荐（要求每道菜的主料尽量来自给定食材，"
            "可以适量补充常见调味料；避免与下面要排除的食材冲突；菜名要简洁有食欲；"
            "并尽量在风味/做法上彼此不同，提供多样选择）。\n"
            f"现有食材：{ingredients_txt}\n"
            f"排除食材：{exclude_txt}\n"
            f"用户偏好：{pref_txt}\n\n"
            "请严格按以下 JSON 数组格式返回，不要输出其它说明文字：\n"
            "[\n"
            '  {"name": "菜名", "description": "一句话简介",'
            ' "ingredients": ["主料1", "主料2"], "tags": ["标签"]},\n'
            "  ...\n"
            "]"
        )
        try:
            llm = get_llm()
            raw = llm.generate(user_prompt, system=system_prompt, max_tokens=512)
        except Exception as e:
            logger.warning("LLM brainstorm 失败: %s", e)
            return []

        match = re.search(r"\[.*\]", raw or "", re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group())
        except Exception as e:
            logger.warning("brainstorm JSON 解析失败: %s\n原文: %s", e, raw)
            return []

        results: List[Dict[str, Any]] = []
        for it in parsed:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            results.append({
                "name": name,
                "description": str(it.get("description", "")).strip(),
                "ingredients": [str(x).strip() for x in (it.get("ingredients") or []) if str(x).strip()],
                "tags": [str(x).strip() for x in (it.get("tags") or []) if str(x).strip()],
                "time": cooking_time,
                "diff": difficulty,
                "steps": [],
                "ai_generated": True,
            })
        return results

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
