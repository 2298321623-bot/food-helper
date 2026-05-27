"""下载 Qwen2.5-1.5B-Instruct Q4_0 GGUF 模型（组员 C Day3-4），支持断点续传。"""
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import LLM_MODEL_FILE

MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
    "resolve/main/qwen2.5-1.5b-instruct-q4_0.gguf"
)

CHUNK = 1024 * 256


def _remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.headers.get("Content-Length", 0))


def download(url: str = MODEL_URL, dest: Path = LLM_MODEL_FILE):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    total_size = _remote_size(url)
    if total_size <= 0:
        raise RuntimeError("无法获取模型文件大小，请检查网络或 HuggingFace 是否可访问。")

    downloaded = dest.stat().st_size if dest.exists() else 0
    if downloaded >= total_size:
        print(f"模型已完整存在（{downloaded / (1024**2):.1f} MB）：{dest}")
        return dest

    if downloaded > total_size:
        print(f"本地文件异常偏大，将重新下载：{dest}")
        dest.unlink()
        downloaded = 0

    if downloaded > 0:
        print(f"断点续传：已有 {downloaded / (1024**2):.1f} MB / {total_size / (1024**2):.1f} MB")
    else:
        print(f"开始下载（约 {total_size / (1024**3):.1f} GB）→ {dest}")
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


if __name__ == "__main__":
    download()
