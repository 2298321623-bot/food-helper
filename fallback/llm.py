"""
LLM 工厂与双引擎切换（Week2 Day14）。
组员 A/B 通过 get_llm() / generate_recipe_with_fallback() 获取实例。
"""
import logging
from typing import List, Optional

from llm.base_llm import BaseLLM
from llm.cloud_llm import CloudLLM
from llm.local_llm import LocalLLM, local_llm_unavailable_reason

logger = logging.getLogger(__name__)


def get_llm(prefer_local: bool = True) -> BaseLLM:
    """
    获取可用 LLM：默认优先本地 GGUF；不可用时使用 DeepSeek API。
    """
    local = LocalLLM()
    cloud = CloudLLM()
    if prefer_local and local.is_available():
        return local
    if cloud.is_available():
        return cloud
    if local.is_available():
        return local
    hints = []
    local_reason = local_llm_unavailable_reason()
    if local_reason:
        hints.append(local_reason)
    if not cloud.is_available():
        hints.append("未配置云端：请设置环境变量 DEEPSEEK_API_KEY")
    raise RuntimeError(
        "无可用大模型：\n" + "\n".join(hints)
        if hints
        else "请下载本地 GGUF 或配置 DEEPSEEK_API_KEY"
    )


def generate_recipe_with_fallback(
    user_ingredients: List[str],
    reference_hint: str = "",
    extra_requirements: str = "",
    recipe_name: str = "",
    prefer_local: bool = True,
) -> str:
    """生成菜谱：本地失败时自动切换云端。"""
    errors = []
    order: List[BaseLLM] = []
    local = LocalLLM()
    cloud = CloudLLM()
    if prefer_local and local.is_available():
        order.append(local)
    if cloud.is_available():
        order.append(cloud)
    if not order and local.is_available():
        order.append(local)

    if not order:
        hints = []
        local_reason = local_llm_unavailable_reason()
        if local_reason:
            hints.append(local_reason)
        if not cloud.is_available():
            hints.append("未配置云端：请设置环境变量 DEEPSEEK_API_KEY")
        raise RuntimeError(
            "无可用大模型：\n" + "\n".join(hints)
            if hints
            else "请下载本地 GGUF 或配置 DEEPSEEK_API_KEY"
        )

    for llm in order:
        try:
            return llm.generate_recipe(
                user_ingredients,
                reference_hint=reference_hint,
                extra_requirements=extra_requirements,
                recipe_name=recipe_name,
            )
        except Exception as e:
            logger.warning("%s 生成失败，尝试下一引擎: %s", type(llm).__name__, e)
            errors.append(f"{type(llm).__name__}: {e}")

    raise RuntimeError("所有 LLM 均失败：\n" + "\n".join(errors))
