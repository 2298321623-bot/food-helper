"""Day5-6：文本向量化与相似度计算。"""
import logging
from typing import List, Optional, Union

import numpy as np

from config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)


class EmbeddingService:
    """基于 sentence-transformers/all-MiniLM-L6-v2 的句向量服务。"""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        logger.info("正在加载嵌入模型：%s", self.model_name)
        self._model = SentenceTransformer(self.model_name)
        logger.info("嵌入模型加载完成")

    def encode(
        self,
        texts: Union[str, List[str]],
        normalize: bool = True,
    ) -> np.ndarray:
        """将文本编码为向量，返回 shape (n, dim)。"""
        self._ensure_loaded()
        if isinstance(texts, str):
            texts = [texts]
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        vectors = np.asarray(vectors, dtype=np.float32)
        if normalize and len(vectors) > 0:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            vectors = vectors / norms
        return vectors


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个向量的余弦相似度（假定已归一化）。"""
    a = np.asarray(a, dtype=np.float32).flatten()
    b = np.asarray(b, dtype=np.float32).flatten()
    if a.shape != b.shape:
        raise ValueError(f"向量维度不一致: {a.shape} vs {b.shape}")
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def embedding_to_blob(vector: np.ndarray) -> bytes:
    """将向量序列化为 BLOB，供 recipes 表存储（组员 B 对接）。"""
    arr = np.asarray(vector, dtype=np.float32).flatten()
    if arr.size != EMBEDDING_DIM:
        raise ValueError(f"期望维度 {EMBEDDING_DIM}，实际 {arr.size}")
    return arr.tobytes()


def blob_to_embedding(blob: Optional[bytes], dim: int = EMBEDDING_DIM) -> Optional[np.ndarray]:
    if not blob:
        return None
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.size != dim:
        return None
    return arr.reshape(dim)
