"""在独立子进程中运行本地 LLM，避免 Windows 后台线程调用 llama.cpp 崩溃。"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from config import LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P

ROOT = Path(__file__).resolve().parents[1]
_INFER_SCRIPT = ROOT / "scripts" / "llm_infer_subprocess.py"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _generate_frozen(req: dict, timeout: int) -> str:
    """打包(exe)模式：重新调用同一个 exe（--llm-infer），用临时文件传递请求/结果。"""
    in_fd, in_path = tempfile.mkstemp(suffix="_llm_in.json")
    out_fd, out_path = tempfile.mkstemp(suffix="_llm_out.json")
    os.close(in_fd)
    os.close(out_fd)
    try:
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(req, f, ensure_ascii=True)
        proc = subprocess.run(
            [sys.executable, "--llm-infer", in_path, out_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"本地模型子进程无有效输出（退出码 {proc.returncode}）"
            ) from e
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "本地模型子进程推理失败")
        return str(payload["text"])
    finally:
        for p in (in_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass


def _generate_script(req: dict, timeout: int) -> str:
    """源码模式：用当前解释器执行推理脚本，通过 stdin/stdout 通信。"""
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
    if getattr(sys, "frozen", False):
        return _generate_frozen(req, timeout)
    return _generate_script(req, timeout)
