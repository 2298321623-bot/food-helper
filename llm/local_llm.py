"""本地 Qwen GGUF 模型封装（llama-cpp-python）。"""

import logging

import os

import sys

import threading

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



_process_lock = threading.Lock()

# Windows 下 llama.cpp 在 QThreadPool 等非主线程调用易 access violation，统一走子进程

_USE_SUBPROCESS = sys.platform == "win32"





def llama_cpp_installed() -> bool:

    from llm.deps import llama_cpp_installed as _installed



    return _installed()





def local_llm_unavailable_reason(model_path: Optional[Path] = None) -> Optional[str]:

    """返回本地 LLM 不可用的原因；可用时返回 None。"""

    path = Path(model_path or LLM_MODEL_FILE)

    if not path.is_file():

        return (

            f"未找到本地模型：{path}\n"

            "请运行：python scripts/download_qwen_model.py"

        )

    if not llama_cpp_installed():

        from llm.deps import format_llm_setup_hint, llama_cpp_import_error



        detail = llama_cpp_import_error() or "未知原因"

        return (

            f"当前解释器无法加载 llama-cpp-python（{detail}）。\n"

            f"{format_llm_setup_hint()}"

        )

    return None





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



    def _build_llama(self):

        from llama_cpp import Llama



        model_file = _model_path_for_llama(self.model_path)

        cpu = os.cpu_count() or 4

        n_threads = max(2, min(cpu - 1, 8))

        return Llama(

            model_path=model_file,

            n_ctx=self.n_ctx,

            n_threads=n_threads,

            n_batch=256,

            use_mmap=False,

            verbose=False,

        )



    def is_available(self) -> bool:

        return local_llm_unavailable_reason(self.model_path) is None



    def _ensure_loaded(self):

        if self._llm is not None:

            return

        if not self.is_available():

            raise FileNotFoundError(

                f"未找到本地模型文件：{self.model_path}\n"

                "请先运行：python scripts/download_qwen_model.py"

            )

        logger.info("正在加载本地模型：%s", self.model_path)

        self._llm = self._build_llama()

        logger.info("本地模型加载完成")



    def generate_in_process(

        self,

        prompt: str,

        system: Optional[str] = None,

        max_tokens: int = LLM_MAX_TOKENS,

        temperature: float = LLM_TEMPERATURE,

        top_p: float = LLM_TOP_P,

    ) -> str:

        """仅在当前进程主线程内调用 llama.cpp（子进程入口使用）。"""

        with _process_lock:

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

                repeat_penalty=1.25,

                frequency_penalty=0.4,

                presence_penalty=0.2,

            )

            return out["choices"][0]["message"]["content"].strip()



    def generate(

        self,

        prompt: str,

        system: Optional[str] = None,

        max_tokens: int = LLM_MAX_TOKENS,

        temperature: float = LLM_TEMPERATURE,

        top_p: float = LLM_TOP_P,

        **_,

    ) -> str:

        if _USE_SUBPROCESS and threading.current_thread() is not threading.main_thread():

            from llm.subprocess_generate import generate_via_subprocess



            logger.info("后台线程调用本地模型，使用子进程推理")

            return generate_via_subprocess(

                prompt,

                system=system,

                max_tokens=max_tokens,

                temperature=temperature,

                top_p=top_p,

            )

        return self.generate_in_process(

            prompt,

            system=system,

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

