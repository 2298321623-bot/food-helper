"""LLM 抽象基类，供本地模型与云端 API（Week2）统一接口。"""
from abc import ABC, abstractmethod
from typing import Generator, List, Optional

from llm.prompts import RECIPE_SYSTEM_PROMPT, build_recipe_user_prompt


class BaseLLM(ABC):
    """大模型统一接口，组员 A 通过 QThreadPool 在后台调用。"""

    @abstractmethod
    def is_available(self) -> bool:
        """模型是否已就绪（文件存在且可加载）。"""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None, **kwargs) -> str:
        """同步文本生成。"""

    def stream_generate(
        self, prompt: str, system: Optional[str] = None, **kwargs
    ) -> Generator[str, None, None]:
        """流式生成（默认回退为一次性输出）。"""
        yield self.generate(prompt, system=system, **kwargs)

    def generate_recipe(
        self,
        user_ingredients: List[str],
        reference_hint: str = "",
        extra_requirements: str = "",
        recipe_name: str = "",
    ) -> str:
        """根据食材与检索到的参考菜谱生成完整方案。"""
        user_prompt = build_recipe_user_prompt(
            user_ingredients,
            reference_hint=reference_hint,
            extra_requirements=extra_requirements,
            recipe_name=recipe_name,
        )
        return self.generate(user_prompt, system=RECIPE_SYSTEM_PROMPT, max_tokens=360)
