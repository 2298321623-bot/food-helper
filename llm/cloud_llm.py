"""Week2 Day14：DeepSeek API（OpenAI 兼容）云端生成。"""
import json
import logging
import urllib.error
import urllib.request
from typing import Generator, List, Optional

from config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    LLM_TOP_P,
)
from llm.base_llm import BaseLLM
from llm.prompts import RECIPE_SYSTEM_PROMPT, build_recipe_user_prompt

logger = logging.getLogger(__name__)


class CloudLLM(BaseLLM):
    """DeepSeek Chat API，本地模型不可用时的兜底。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = (api_key or DEEPSEEK_API_KEY or "").strip()
        self.base_url = (base_url or DEEPSEEK_API_BASE).rstrip("/")
        self.model = model or DEEPSEEK_MODEL

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _chat_completion(
        self,
        messages: List[dict],
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
        top_p: float = LLM_TOP_P,
        stream: bool = False,
    ):
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API 错误 {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"无法连接 DeepSeek API: {e}") from e

        if stream:
            return body
        return body["choices"][0]["message"]["content"].strip()

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
        top_p: float = LLM_TOP_P,
        **_,
    ) -> str:
        if not self.is_available():
            raise RuntimeError(
                "未配置 DeepSeek API Key，请设置环境变量 DEEPSEEK_API_KEY"
            )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._chat_completion(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )

    def stream_generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
        top_p: float = LLM_TOP_P,
        **_,
    ) -> Generator[str, None, None]:
        text = self.generate(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        yield text

    def generate_recipe(
        self,
        user_ingredients: List[str],
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
