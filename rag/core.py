"""Day7：基础菜谱检索与食材匹配算法。"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np

from config import (
    FULL_MATCH_BONUS,
    INGREDIENT_MATCH_WEIGHT,
    MISSING_INGREDIENT_PENALTY,
    PREFERENCE_FILTER_WEIGHT,
    PREFERENCE_MIN_FILTER_SCORE,
    PREFERENCE_SEMANTIC_WEIGHT,
    RECIPE_TOP_K,
    SAMPLE_RECIPES_JSON,
    SEMANTIC_MATCH_WEIGHT,
)
from rag.embeddings import EmbeddingService, cosine_similarity

logger = logging.getLogger(__name__)


def _normalize_ingredient(name: str) -> str:
    """简单归一化：去空格、统一常见别名。"""
    name = name.strip()
    aliases = {
        "西红柿": "番茄",
        "蕃茄": "番茄",
        "西兰花": "西蓝花",
        "花菜": "菜花",
    }
    return aliases.get(name, name)


def build_recipe_search_text(recipe: Dict[str, Any]) -> str:
    """构建用于向量检索的菜谱描述文本。"""
    ingredients = recipe.get("ingredients") or []
    if isinstance(ingredients, str):
        try:
            ingredients = json.loads(ingredients)
        except json.JSONDecodeError:
            ingredients = [ingredients]
    tags = recipe.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    parts = [
        recipe.get("name", ""),
        " ".join(str(i) for i in ingredients),
        " ".join(str(t) for t in tags),
        str(recipe.get("description", "")),
        str(recipe.get("difficulty", recipe.get("diff", ""))),
        str(recipe.get("cooking_time", recipe.get("time", ""))),
    ]
    return " ".join(p for p in parts if p).strip()


def _ingredient_overlap_score(
    user_ingredients: Set[str], recipe_ingredients: List[str]
) -> float:
    """食材名匹配度：交集 / 菜谱所需食材数。"""
    if not recipe_ingredients:
        return 0.0
    recipe_set = {_normalize_ingredient(i) for i in recipe_ingredients}
    user_set = {_normalize_ingredient(i) for i in user_ingredients}
    matched = recipe_set & user_set
    return len(matched) / len(recipe_set)


def _recipe_tags(recipe: Dict[str, Any]) -> List[str]:
    tags = recipe.get("tags") or []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(t) for t in tags]


def _recipe_time(recipe: Dict[str, Any]) -> str:
    return str(recipe.get("time") or recipe.get("cooking_time") or "").strip()


def _recipe_diff(recipe: Dict[str, Any]) -> str:
    return str(recipe.get("diff") or recipe.get("difficulty") or "").strip()


def _apply_ingredient_rank_boost(item: Dict[str, Any]) -> float:
    """Week2：缺料越少得分越高，食材齐备额外加分。"""
    base = float(item.get("match_score", 0))
    missing = item.get("missing_ingredients") or []
    penalty = len(missing) * MISSING_INGREDIENT_PENALTY
    bonus = FULL_MATCH_BONUS if not missing else 0.0
    final = max(0.0, base - penalty + bonus)
    item["match_score"] = round(final, 4)
    return final


def _preference_filter_score(
    recipe: Dict[str, Any],
    diet: str,
    cooking_time: str,
    difficulty: str,
) -> float:
    """Week2：饮食标签 / 时间 / 难度 硬性偏好匹配（0~1）。"""
    score = 0.0
    tags = _recipe_tags(recipe)
    if diet and diet in tags:
        score += 0.45
    if cooking_time and _recipe_time(recipe) == cooking_time:
        score += 0.3
    if difficulty and _recipe_diff(recipe) == difficulty:
        score += 0.25
    return min(1.0, score)


def _parse_ingredients(recipe: Dict[str, Any]) -> List[str]:
    raw = recipe.get("ingredients") or []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [str(x) for x in parsed]
        except json.JSONDecodeError:
            return [x.strip() for x in re.split(r"[,，、]", raw) if x.strip()]
    return [str(x) for x in raw]


def match_recipes_by_ingredients(
    recipes: List[Dict[str, Any]],
    user_ingredient_names: List[str],
    *,
    top_k: int = RECIPE_TOP_K,
    embedding_service: Optional[EmbeddingService] = None,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    模式1：根据用户冰箱食材检索菜谱。
    综合得分 = 食材匹配度 * 0.7 + 语义相似度 * 0.3
    返回结果按 score 降序，每项附带 match_score、matched_ingredients、missing_ingredients。
    """
    user_set = {_normalize_ingredient(n) for n in user_ingredient_names if n.strip()}
    if not user_set:
        return []

    query_text = " ".join(sorted(user_set))
    query_vec = None
    if embedding_service is not None:
        query_vec = embedding_service.encode(query_text)[0]

    scored: List[Dict[str, Any]] = []
    for recipe in recipes:
        recipe_ings = [_normalize_ingredient(i) for i in _parse_ingredients(recipe)]
        ing_score = _ingredient_overlap_score(user_set, recipe_ings)

        sem_score = 0.0
        if query_vec is not None and embedding_service is not None:
            blob = recipe.get("embedding")
            if blob is not None:
                from rag.embeddings import blob_to_embedding

                vec = blob_to_embedding(blob if isinstance(blob, bytes) else None)
            else:
                text = build_recipe_search_text(recipe)
                vec = embedding_service.encode(text)[0]
            if vec is not None:
                sem_score = max(0.0, cosine_similarity(query_vec, vec))

        total = INGREDIENT_MATCH_WEIGHT * ing_score + SEMANTIC_MATCH_WEIGHT * sem_score
        if total < min_score:
            continue

        recipe_set = set(recipe_ings)
        matched = sorted(recipe_set & user_set)
        missing = sorted(recipe_set - user_set)
        item = dict(recipe)
        item["match_score"] = round(total, 4)
        item["ingredient_match"] = round(ing_score, 4)
        item["semantic_match"] = round(sem_score, 4)
        item["matched_ingredients"] = matched
        item["missing_ingredients"] = missing
        _apply_ingredient_rank_boost(item)
        scored.append(item)

    scored.sort(
        key=lambda x: (
            len(x.get("missing_ingredients") or []),
            -x["match_score"],
        )
    )
    return scored[:top_k]


def match_recipes_by_preferences(
    recipes: List[Dict[str, Any]],
    *,
    diet: str = "",
    cooking_time: str = "",
    difficulty: str = "",
    top_k: int = RECIPE_TOP_K,
    embedding_service: Optional[EmbeddingService] = None,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Week2 模式2：按饮食偏好、烹饪时间、难度检索（想吃某类菜）。
    综合得分 = 偏好匹配 * 0.6 + 语义相似 * 0.4
    """
    diet = (diet or "").strip()
    cooking_time = (cooking_time or "").strip()
    difficulty = (difficulty or "").strip()
    if not any([diet, cooking_time, difficulty]):
        return []

    query_parts = [p for p in [diet, cooking_time, difficulty, "家常菜谱"] if p]
    query_text = " ".join(query_parts)
    query_vec = None
    if embedding_service is not None:
        query_vec = embedding_service.encode(query_text)[0]

    scored: List[Dict[str, Any]] = []
    for recipe in recipes:
        filter_score = _preference_filter_score(recipe, diet, cooking_time, difficulty)
        if filter_score < PREFERENCE_MIN_FILTER_SCORE:
            continue

        sem_score = 0.0
        if query_vec is not None and embedding_service is not None:
            blob = recipe.get("embedding")
            if blob is not None:
                from rag.embeddings import blob_to_embedding

                vec = blob_to_embedding(blob if isinstance(blob, bytes) else None)
            else:
                vec = embedding_service.encode(build_recipe_search_text(recipe))[0]
            if vec is not None:
                sem_score = max(0.0, cosine_similarity(query_vec, vec))

        total = (
            PREFERENCE_FILTER_WEIGHT * filter_score
            + PREFERENCE_SEMANTIC_WEIGHT * sem_score
        )
        if total < min_score:
            continue

        item = dict(recipe)
        item["match_score"] = round(total, 4)
        item["preference_match"] = round(filter_score, 4)
        item["semantic_match"] = round(sem_score, 4)
        item["filter_diet"] = diet
        item["filter_time"] = cooking_time
        item["filter_diff"] = difficulty
        scored.append(item)

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:top_k]


class RecipeRetriever:
    """菜谱检索器：支持 JSON 样例与后续 db.py 对接。"""

    def __init__(
        self,
        recipes: Optional[List[Dict[str, Any]]] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.recipes = recipes or []
        self.embedding_service = embedding_service or EmbeddingService()
        self._embeddings_ready = False
        self._embedding_failed_reason = ""

    @classmethod
    def from_json(cls, path: Path = SAMPLE_RECIPES_JSON) -> "RecipeRetriever":
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        recipes = data if isinstance(data, list) else data.get("recipes", [])
        retriever = cls(recipes=recipes)
        retriever._try_build_embeddings()
        return retriever

    def load_recipes(self, recipes: List[Dict[str, Any]], rebuild_embeddings: bool = True):
        self.recipes = recipes
        self._embeddings_ready = False
        self._embedding_failed_reason = ""
        if rebuild_embeddings:
            self._try_build_embeddings()

    def _try_build_embeddings(self):
        """尽力构建向量；失败时自动降级为仅食材/偏好匹配，不中断主流程。"""
        if self._embeddings_ready or not self.recipes:
            return
        try:
            self.build_embeddings()
            self._embedding_failed_reason = ""
        except Exception as e:
            self._embeddings_ready = False
            self._embedding_failed_reason = str(e)
            logger.warning("向量检索不可用，降级为规则匹配：%s", e)

    def build_embeddings(self):
        """为菜谱预计算向量（可写入 DB BLOB）。"""
        if not self.recipes:
            return
        texts = [build_recipe_search_text(r) for r in self.recipes]
        vectors = self.embedding_service.encode(texts)
        for recipe, vec in zip(self.recipes, vectors):
            from rag.embeddings import embedding_to_blob

            recipe["embedding"] = embedding_to_blob(vec)
        self._embeddings_ready = True
        logger.info("已为 %d 条菜谱构建向量", len(self.recipes))

    def search_by_ingredients(
        self,
        ingredient_names: List[str],
        top_k: int = RECIPE_TOP_K,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """对外主接口：根据食材名称列表检索菜谱。"""
        if not self._embeddings_ready and self.recipes:
            self._try_build_embeddings()
        return match_recipes_by_ingredients(
            self.recipes,
            ingredient_names,
            top_k=top_k,
            embedding_service=self.embedding_service if self._embeddings_ready else None,
            min_score=min_score,
        )

    def search_fully_available(
        self, ingredient_names: List[str], top_k: int = RECIPE_TOP_K
    ) -> List[Dict[str, Any]]:
        """仅返回食材完全齐备的菜谱（subset 匹配）。"""
        results = self.search_by_ingredients(ingredient_names, top_k=len(self.recipes))
        full = [r for r in results if not r.get("missing_ingredients")]
        return full[:top_k]

    def search_by_preferences(
        self,
        diet: str = "",
        cooking_time: str = "",
        difficulty: str = "",
        top_k: int = RECIPE_TOP_K,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Week2：按需求做菜检索。"""
        if not self._embeddings_ready and self.recipes:
            self._try_build_embeddings()
        return match_recipes_by_preferences(
            self.recipes,
            diet=diet,
            cooking_time=cooking_time,
            difficulty=difficulty,
            top_k=top_k,
            embedding_service=self.embedding_service if self._embeddings_ready else None,
            min_score=min_score,
        )
