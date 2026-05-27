"""安装本地 LLM 推理依赖（llama-cpp-python）。

务必用「运行 main.py 的同一个 Python」执行本脚本，例如：
  D:\\Python312\\python.exe scripts/install_local_llm_deps.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm.deps import ensure_llama_cpp, format_llm_setup_hint, llama_cpp_import_error


def main():
    print(f"目标解释器: {sys.executable}")
    if ensure_llama_cpp(auto_install=True):
        print("llama-cpp-python 已就绪。")
        return
    err = llama_cpp_import_error()
    print("安装后仍无法导入 llama_cpp:", err or "未知")
    print()
    print(format_llm_setup_hint())
    sys.exit(1)


if __name__ == "__main__":
    main()
