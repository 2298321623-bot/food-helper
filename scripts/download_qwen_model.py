"""下载 Qwen2.5-1.5B-Instruct GGUF 模型，支持 q4_0 / q8_0 与断点续传。"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import LLM_MODEL_DIR, LLM_MODEL_FILE

MODEL_VARIANTS = {
    "q4_0": {
        "filename": "qwen2.5-1.5b-instruct-q4_0.gguf",
        "url": (
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
            "resolve/main/qwen2.5-1.5b-instruct-q4_0.gguf"
        ),
    },
    "q8_0": {
        "filename": "qwen2.5-1.5b-instruct-q8_0.gguf",
        "url": (
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
            "resolve/main/qwen2.5-1.5b-instruct-q8_0.gguf"
        ),
    },
}

CHUNK = 1024 * 256


def _remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.headers.get("Content-Length", 0))


def resolve_variant_dest(variant: str) -> Path:
    if variant not in MODEL_VARIANTS:
        raise ValueError(f"不支持的模型变体：{variant}")
    if variant == "q4_0":
        return Path(LLM_MODEL_FILE)
    return Path(LLM_MODEL_DIR) / MODEL_VARIANTS[variant]["filename"]


def download(*, variant: str = "q4_0", url: str | None = None, dest: Path | None = None) -> Path:
    if variant not in MODEL_VARIANTS:
        raise ValueError(f"不支持的模型变体：{variant}")

    meta = MODEL_VARIANTS[variant]
    url = url or meta["url"]
    dest = Path(dest) if dest else resolve_variant_dest(variant)
    dest.parent.mkdir(parents=True, exist_ok=True)

    total_size = _remote_size(url)
    if total_size <= 0:
        raise RuntimeError("无法获取模型文件大小，请检查网络或 HuggingFace 是否可访问。")

    downloaded = dest.stat().st_size if dest.exists() else 0
    if downloaded >= total_size:
        print(f"{variant} 模型已完整存在（{downloaded / (1024**2):.1f} MB）：{dest}")
        return dest

    if downloaded > total_size:
        print(f"本地文件异常偏大，将重新下载：{dest}")
        dest.unlink()
        downloaded = 0

    if downloaded > 0:
        print(
            f"{variant} 断点续传：已有 "
            f"{downloaded / (1024**2):.1f} MB / {total_size / (1024**2):.1f} MB"
        )
    else:
        print(f"开始下载 {variant}（约 {total_size / (1024**3):.2f} GB）→ {dest}")
    print(f"来源：{url}")

    req = urllib.request.Request(url)
    if downloaded > 0:
        req.add_header("Range", f"bytes={downloaded}-")

    with urllib.request.urlopen(req, timeout=120) as resp:
        mode = "ab" if resp.status == 206 else "wb"
        if mode == "wb" and downloaded > 0:
            print("服务器不支持续传，从头重新下载…")
            downloaded = 0

        with dest.open(mode) as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                pct = min(100.0, downloaded * 100 / total_size)
                print(f"\r进度：{pct:.1f}% ({downloaded / (1024**2):.1f} MB)", end="", flush=True)

    final = dest.stat().st_size
    if final < total_size:
        raise RuntimeError(
            f"下载未完成：{final} / {total_size} 字节。请重新运行本脚本继续下载。"
        )

    print(f"\n下载完成：{dest}（{final / (1024**2):.1f} MB）")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=sorted(MODEL_VARIANTS.keys()), default="q4_0")
    parser.add_argument("--dest")
    args = parser.parse_args()

    dest = Path(args.dest) if args.dest else None
    download(variant=args.variant, dest=dest)


if __name__ == "__main__":
    main()
