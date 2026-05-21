"""本地 Qwen GGUF 模型封装（llama-cpp-python）。"""
import logging
import os
import sys
from pathlib import Path
from typing import Generator, Optional

from config import (
    LLM_CONTEXT_SIZE,
    LLM_MAX_TOKENS,
    LLM_MODEL_FILE,
    LLM_TEMPERATURE,
    LLM_TOP_P,
)
from llm.base_llm import BaseLLM
from llm.prompts import RECIPE_SYSTEM_PROMPT, build_recipe_user_prompt

logger = logging.getLogger(__name__)


def _model_path_for_llama(path: Path) -> str:
    """Windows 下中文路径需使用扩展路径前缀，否则 llama.cpp 可能打不开文件。"""
    resolved = str(path.resolve())
    if sys.platform == "win32" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


class LocalLLM(BaseLLM):
    """Day3-4：加载 Qwen2.5-1.5B-Instruct Q4_0，提供基础推理。"""

    def __init__(self, model_path: Optional[Path] = None, n_ctx: int = LLM_CONTEXT_SIZE):
        self.model_path = Path(model_path or LLM_MODEL_FILE)
        self.n_ctx = n_ctx
        self._llm = None

    def is_available(self) -> bool:
        return self.model_path.is_file()

    def _ensure_loaded(self):
        if self._llm is not None:
            return
        if not self.is_available():
            raise FileNotFoundError(
                f"未找到本地模型文件：{self.model_path}\n"
                "请先运行：python scripts/download_qwen_model.py"
            )
        from llama_cpp import Llama

        logger.info("正在加载本地模型：%s", self.model_path)
        model_file = _model_path_for_llama(self.model_path)
        self._llm = Llama(
            model_path=model_file,
            n_ctx=self.n_ctx,
            verbose=False,
        )
        logger.info("本地模型加载完成")

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
        top_p: float = LLM_TOP_P,
        **_,
    ) -> str:
        self._ensure_loaded()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        out = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        return out["choices"][0]["message"]["content"].strip()

    def stream_generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
        top_p: float = LLM_TOP_P,
        **_,
    ) -> Generator[str, None, None]:
        self._ensure_loaded()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stream=True,
        )
        for chunk in stream:
            delta = chunk["choices"][0]["delta"]
            if "content" in delta and delta["content"]:
                yield delta["content"]

    def generate_recipe(
        self,
        user_ingredients,
        reference_hint: str = "",
        extra_requirements: str = "",
        recipe_name: str = "",
    ) -> str:
        user_prompt = build_recipe_user_prompt(
            user_ingredients,
            reference_hint=reference_hint,
            extra_requirements=extra_requirements,
            recipe_name=recipe_name,
        )
        return self.generate(user_prompt, system=RECIPE_SYSTEM_PROMPT)
