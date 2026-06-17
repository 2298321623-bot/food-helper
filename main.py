import logging
import os
import sys

# 打包(exe)运行时，切换工作目录到 exe 所在目录，
# 使 data.db / food.db / data.json / data/ 等相对路径资源定位正确。
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))


def _run_llm_infer_worker() -> int:
    """子进程推理模式：读取输入 JSON 文件，写出结果 JSON 文件。

    打包后无法用 `python 脚本.py` 方式启动子进程，改为重新调用同一个 exe，
    并通过临时文件传递请求/结果，避免 windowed 模式下 stdout 为 None 的问题。
    """
    import json

    args = sys.argv[2:]
    if len(args) < 2:
        return 2
    in_path, out_path = args[0], args[1]
    try:
        with open(in_path, "r", encoding="utf-8") as f:
            req = json.load(f)
        from config import LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P
        from llm.local_llm import LocalLLM

        llm = LocalLLM()
        text = llm.generate_in_process(
            req["prompt"],
            system=req.get("system"),
            max_tokens=req.get("max_tokens") or LLM_MAX_TOKENS,
            temperature=req.get("temperature") if req.get("temperature") is not None else LLM_TEMPERATURE,
            top_p=req.get("top_p") if req.get("top_p") is not None else LLM_TOP_P,
        )
        payload = {"ok": True, "text": text}
        rc = 0
    except Exception as e:  # noqa: BLE001
        payload = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        rc = 1
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True)
    except Exception:  # noqa: BLE001
        return 1
    return rc


if len(sys.argv) >= 2 and sys.argv[1] == "--llm-infer":
    raise SystemExit(_run_llm_infer_worker())


def _prewarm_torch() -> None:
    """在加载 PyQt6 / llama_cpp 之前先初始化 torch，避免 Windows 上
    torch 的 c10.dll 因 OpenMP 运行库加载顺序冲突而初始化失败（WinError 1114），
    该冲突会导致 RAG 语义检索被迫降级为规则匹配。

    打包版（exe）未包含 torch，ImportError 时静默跳过，不影响主程序。
    """
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    try:
        import torch  # noqa: F401
    except Exception:
        pass


_prewarm_torch()


from PyQt6.QtWidgets import QApplication, QMessageBox

from controllers.app_controller import AppController
from ui.styles import GLOBAL_STYLE

logging.basicConfig(level=logging.INFO)


def _ensure_llm_runtime():
    from fallback.llm import get_llm
    from llm.deps import ensure_llama_cpp, format_llm_setup_hint
    from llm.local_llm import LocalLLM

    if LocalLLM().model_path.is_file():
        # 打包后不应尝试 pip 安装（llama-cpp 已随包），仅源码运行时自动补依赖
        ensure_llama_cpp(auto_install=not getattr(sys, "frozen", False))
    try:
        get_llm()
        return None
    except RuntimeError as e:
        return f"{e}\n\n{format_llm_setup_hint()}"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLE)

    llm_err = _ensure_llm_runtime()
    if llm_err:
        QMessageBox.warning(
            None,
            "AI 依赖未就绪",
            llm_err + "\n\n修复后请完全退出并重新启动本程序。",
        )

    controller = AppController()
    sys.exit(app.exec())
