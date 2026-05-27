import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from controllers.app_controller import AppController
from ui.styles import GLOBAL_STYLE

logging.basicConfig(level=logging.INFO)


def _ensure_llm_runtime():
    from fallback.llm import get_llm
    from llm.deps import ensure_llama_cpp, format_llm_setup_hint
    from llm.local_llm import LocalLLM

    if LocalLLM().model_path.is_file():
        ensure_llama_cpp(auto_install=True)
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
