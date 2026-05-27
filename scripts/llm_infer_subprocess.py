"""子进程内执行本地 LLM 推理（供主进程在 Windows/后台线程调用）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        req = json.loads(sys.stdin.read())
        from llm.local_llm import LocalLLM

        llm = LocalLLM()
        from config import LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P

        text = llm.generate_in_process(
            req["prompt"],
            system=req.get("system"),
            max_tokens=req.get("max_tokens") or LLM_MAX_TOKENS,
            temperature=req.get("temperature") if req.get("temperature") is not None else LLM_TEMPERATURE,
            top_p=req.get("top_p") if req.get("top_p") is not None else LLM_TOP_P,
        )
        sys.stdout.write(json.dumps({"ok": True, "text": text}, ensure_ascii=True))
        return 0
    except Exception as e:
        sys.stdout.write(
            json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=True)
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
