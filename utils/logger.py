"""统一日志工具：控制台 + 滚动文件，模块全局复用。"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app_paths import BASE_DIR

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

_initialized = False


def _init_root() -> None:
    """初始化根 logger，幂等。"""
    global _initialized
    if _initialized:
        return
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(_FMT, datefmt="%Y-%m-%d %H:%M:%S")

    # 控制台
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # 滚动文件 1MB × 5
    fh = RotatingFileHandler(
        LOG_FILE, maxBytes=1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    # 避免重复 handler
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(ch)
    root.addHandler(fh)

    _initialized = True


def get_logger(name: str | None = None) -> logging.Logger:
    """获取统一配置的 logger。"""
    _init_root()
    return logging.getLogger(name or "food-helper")
