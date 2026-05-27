"""确保当前 Python 解释器具备本地 LLM 推理依赖。"""
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WHEEL_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cpu"


def llama_cpp_import_error() -> Optional[str]:
    """尝试导入 llama_cpp；失败时返回错误说明，成功返回 None。"""
    try:
        import llama_cpp  # noqa: F401
        return None
    except ImportError as e:
        return str(e)
    except OSError as e:
        return f"DLL 加载失败: {e}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def llama_cpp_installed() -> bool:
    return llama_cpp_import_error() is None


def pip_install_llama_cpp() -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "llama-cpp-python",
        "--prefer-binary",
        "--extra-index-url",
        WHEEL_INDEX,
    ]
    logger.info("正在为 %s 安装 llama-cpp-python …", sys.executable)
    subprocess.check_call(cmd)


def ensure_llama_cpp(auto_install: bool = True) -> bool:
    """
    保证当前 sys.executable 可 import llama_cpp。
    auto_install 为 True 时，缺失则自动 pip 安装（仅影响当前解释器）。
    """
    if llama_cpp_installed():
        return True
    if not auto_install:
        return False
    try:
        pip_install_llama_cpp()
    except subprocess.CalledProcessError as e:
        logger.error("自动安装 llama-cpp-python 失败: %s", e)
        return False
    return llama_cpp_installed()


def format_llm_setup_hint() -> str:
    py = sys.executable
    script = Path(__file__).resolve().parents[1] / "scripts" / "install_local_llm_deps.py"
    return (
        f"当前 Python：{py}\n\n"
        f"请在该解释器下安装依赖（复制到终端执行）：\n"
        f'"{py}" "{script}"\n\n'
        "或双击项目根目录的「启动应用.bat」。\n\n"
        "或：\n"
        f'"{py}" -m pip install llama-cpp-python --prefer-binary '
        f"--extra-index-url {WHEEL_INDEX}"
    )
