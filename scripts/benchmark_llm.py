"""
AI 模型轻量化优化对比脚本
==========================
针对本地 Qwen2.5-1.5B-Instruct (Q4_0 GGUF)，对比不同配置下的推理速度、
峰值内存、输出长度，并生成 CSV + 柱状图，可直接放进实验报告。

对比维度：
  1. n_threads ∈ {1, 2, 4}        —— CPU 并发线程
  2. n_ctx    ∈ {1024, 2048, 4096} —— 上下文窗口
  3. max_tokens ∈ {128, 256, 512}  —— 输出长度

输出：
  reports/llm_benchmark.csv
  reports/llm_benchmark.png

运行：
  .\.venv\Scripts\python.exe scripts/benchmark_llm.py
"""
from __future__ import annotations

import csv
import gc
import sys
import time
import tracemalloc
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)
CSV_PATH = REPORT_DIR / "llm_benchmark.csv"
PNG_PATH = REPORT_DIR / "llm_benchmark.png"

PROMPT = (
    "请用我冰箱里的鸡蛋、番茄和葱设计一道家常菜，"
    "给出食材用量、烹饪步骤（不超过 6 步）和大致营养估算。"
)
SYSTEM = "你是家庭厨师顾问，回答要简洁实用，使用 Markdown 格式。"


@dataclass
class BenchResult:
    label: str
    n_ctx: int
    n_threads: int
    max_tokens: int
    load_ms: float
    infer_ms: float
    out_chars: int
    chars_per_sec: float
    peak_mem_mb: float


def _build_llama(n_ctx: int, n_threads: int):
    from llama_cpp import Llama
    from config import LLM_MODEL_FILE
    from llm.local_llm import _model_path_for_llama

    model_file = _model_path_for_llama(Path(LLM_MODEL_FILE))
    return Llama(
        model_path=model_file,
        n_ctx=n_ctx,
        n_threads=n_threads,
        use_mmap=False,
        verbose=False,
    )


def _run_case(label: str, n_ctx: int, n_threads: int, max_tokens: int) -> BenchResult:
    print(f"\n>>> {label}  ctx={n_ctx} threads={n_threads} max_tokens={max_tokens}")
    tracemalloc.start()

    t0 = time.perf_counter()
    llm = _build_llama(n_ctx=n_ctx, n_threads=n_threads)
    load_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    out = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROMPT},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
        top_p=0.9,
    )
    infer_ms = (time.perf_counter() - t1) * 1000
    text = out["choices"][0]["message"]["content"].strip()
    out_chars = len(text)
    cps = out_chars / (infer_ms / 1000) if infer_ms > 0 else 0.0

    _, peak = tracemalloc.get_traced_memory()
    peak_mb = peak / (1024 * 1024)
    tracemalloc.stop()

    print(f"    加载 {load_ms:.0f} ms / 推理 {infer_ms:.0f} ms / "
          f"输出 {out_chars} 字 / {cps:.1f} 字/秒 / 峰值内存 {peak_mb:.1f} MB")

    del llm
    gc.collect()

    return BenchResult(
        label=label, n_ctx=n_ctx, n_threads=n_threads, max_tokens=max_tokens,
        load_ms=load_ms, infer_ms=infer_ms, out_chars=out_chars,
        chars_per_sec=cps, peak_mem_mb=peak_mb,
    )


def run_all() -> List[BenchResult]:
    cases = [
        # 控制变量：先固定 ctx=2048 max=256，对比 threads
        ("Threads=1", 2048, 1, 256),
        ("Threads=2", 2048, 2, 256),
        ("Threads=4", 2048, 4, 256),
        # 再固定 threads=4 max=256，对比 ctx
        ("Ctx=1024",  1024, 4, 256),
        ("Ctx=4096",  4096, 4, 256),
        # 再固定 ctx=2048 threads=4，对比 max_tokens
        ("Max=128",   2048, 4, 128),
        ("Max=512",   2048, 4, 512),
    ]
    results: List[BenchResult] = []
    for label, ctx, th, mx in cases:
        try:
            results.append(_run_case(label, ctx, th, mx))
        except Exception as e:
            print(f"!!! {label} 失败：{e}")
    return results


def save_csv(results: List[BenchResult]) -> None:
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    print(f"\n[OK] 结果已保存：{CSV_PATH}")


def save_chart(results: List[BenchResult]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib 未安装，跳过图表生成")
        return

    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False

    labels = [r.label for r in results]
    infer = [r.infer_ms / 1000 for r in results]
    cps = [r.chars_per_sec for r in results]
    mem = [r.peak_mem_mb for r in results]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    axes[0].bar(labels, infer, color="#0d9488")
    axes[0].set_title("推理耗时 (秒，越低越好)")
    axes[0].set_ylabel("seconds")
    axes[0].tick_params(axis="x", rotation=30)

    axes[1].bar(labels, cps, color="#f59e0b")
    axes[1].set_title("吞吐量 (字/秒，越高越好)")
    axes[1].set_ylabel("chars/sec")
    axes[1].tick_params(axis="x", rotation=30)

    axes[2].bar(labels, mem, color="#ef4444")
    axes[2].set_title("Python 侧峰值内存 (MB)")
    axes[2].set_ylabel("MB")
    axes[2].tick_params(axis="x", rotation=30)

    fig.suptitle("Qwen2.5-1.5B-Instruct Q4_0 推理参数对比", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=150, bbox_inches="tight")
    print(f"[OK] 图表已保存：{PNG_PATH}")


def main() -> None:
    print("=" * 60)
    print(" Qwen2.5-1.5B-Instruct (Q4_0) 推理参数对比")
    print("=" * 60)
    results = run_all()
    if not results:
        print("没有任何成功的样例，退出。")
        return
    save_csv(results)
    save_chart(results)
    print("\n=== 结果汇总 ===")
    for r in results:
        print(
            f"{r.label:<10} | {r.infer_ms:>7.0f} ms | "
            f"{r.chars_per_sec:>5.1f} 字/秒 | {r.peak_mem_mb:>6.1f} MB"
        )


if __name__ == "__main__":
    main()
