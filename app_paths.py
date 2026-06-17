"""统一的运行时基准目录：源码运行用项目根，打包(exe)运行用 exe 所在目录。"""
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """返回放置可读写资源（数据库、日志、models/、data/）的基准目录。

    - 源码运行：本文件所在的项目根目录。
    - PyInstaller 打包后：exe 所在目录（与 models/、data/ 同级）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
