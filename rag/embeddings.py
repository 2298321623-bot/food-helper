"""Day5-6：文本向量化与相似度计算。"""
import json
import logging
import os
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

from config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)
_DEBUG_LOG_FILE = Path(__file__).resolve().parents[1] / "debug-52002d.log"
_DEBUG_SESSION_ID = "52002d"


def _debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[dict] = None,
    run_id: str = "run1",
):
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    with _DEBUG_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


class EmbeddingService:
    """基于 sentence-transformers/all-MiniLM-L6-v2 的句向量服务。"""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return

        # region agent log
        _debug_log(
            "H1",
            "rag/embeddings.py:_ensure_loaded:entry",
            "Preparing to import SentenceTransformer",
            {
                "python": sys.executable,
                "pythonVersion": sys.version,
                "platform": platform.platform(),
                "cwd": os.getcwd(),
                "modelName": self.model_name,
            },
        )
        # endregion
        try:
            from sentence_transformers import SentenceTransformer
            # region agent log
            _debug_log(
                "H2",
                "rag/embeddings.py:_ensure_loaded:import_ok",
                "sentence_transformers import succeeded",
                {
                    "hasTorchInModules": "torch" in sys.modules,
                },
            )
            # endregion
        except Exception as e:
            # region agent log
            _debug_log(
                "H3",
                "rag/embeddings.py:_ensure_loaded:import_fail",
                "sentence_transformers import failed",
                {
                    "errorType": type(e).__name__,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "pathHasMsys": "msys64" in os.environ.get("PATH", "").lower(),
                },
            )
            # endregion
            raise

        logger.info("正在加载嵌入模型：%s", self.model_name)
        try:
            self._model = SentenceTransformer(self.model_name)
            # region agent log
            _debug_log(
                "H4",
                "rag/embeddings.py:_ensure_loaded:model_ok",
                "SentenceTransformer model loaded",
                {"modelName": self.model_name},
            )
            # endregion
        except Exception as e:
            # region agent log
            _debug_log(
                "H5",
                "rag/embeddings.py:_ensure_loaded:model_fail",
                "SentenceTransformer model init failed",
                {
                    "errorType": type(e).__name__,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
            # endregion
            raise
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
