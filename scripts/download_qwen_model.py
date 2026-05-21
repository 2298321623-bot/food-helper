"""下载 Qwen2.5-1.5B-Instruct Q4_0 GGUF 模型（组员 C Day3-4）。"""
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import LLM_MODEL_DIR, LLM_MODEL_FILE

# HuggingFace 直链
MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
    "resolve/main/qwen2.5-1.5b-instruct-q4_0.gguf"
)


def download(url: str = MODEL_URL, dest: Path = LLM_MODEL_FILE):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"模型已存在，跳过下载：{dest}")
        return dest

    print(f"开始下载（约 1GB）→ {dest}")
    print(f"来源：{url}")

    def report(block_num, block_size, total_size):
        if total_size <= 0:
            return
        downloaded = block_num * block_size
        pct = min(100, downloaded * 100 / total_size)
        print(f"\r进度：{pct:.1f}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=report)
    print(f"\n下载完成：{dest}")
    return dest


if __name__ == "__main__":
    download()
