"""在独立子进程中运行本地 LLM，避免 Windows 后台线程调用 llama.cpp 崩溃。"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config import LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P

ROOT = Path(__file__).resolve().parents[1]
_INFER_SCRIPT = ROOT / "scripts" / "llm_infer_subprocess.py"


def generate_via_subprocess(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    timeout: int = 300,
) -> str:
    req = {
        "prompt": prompt,
        "system": system,
        "max_tokens": max_tokens if max_tokens is not None else LLM_MAX_TOKENS,
        "temperature": temperature if temperature is not None else LLM_TEMPERATURE,
        "top_p": top_p if top_p is not None else LLM_TOP_P,
    }
    proc = subprocess.run(
        [sys.executable, str(_INFER_SCRIPT)],
        input=json.dumps(req, ensure_ascii=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
        encoding="utf-8",
        errors="replace",
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        err = (proc.stderr or "").strip() or f"子进程退出码 {proc.returncode}"
        raise RuntimeError(f"本地模型子进程无输出：{err}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"本地模型子进程返回异常：{raw[:500]}") from e
    if not payload.get("ok"):
        raise RuntimeError(payload.get("error") or "本地模型子进程推理失败")
    return str(payload["text"])
