"""
AI 模型轻量化优化：优化前 vs 优化后 完整对比
============================================
针对本项目使用的本地 LLM（Qwen2.5-1.5B-Instruct，GGUF 格式），
按老师要求做"简单优化 + 优化前后效果对比"，覆盖三个维度：

    1. 推理速度  (秒 / 字符吞吐量)
    2. 内存占用  (Python 侧 tracemalloc 峰值)
    3. 准确率    (在小型领域 QA 集上的关键词召回率)

优化手段（与"未优化基线"对比）：
    - 参数调优：n_threads 1 → 4，n_ctx 4096 → 2048，max_tokens 512 → 256
    - 模型量化：Q4_0 4-bit 量化（vs 理论 FP16 / Q8_0 体积，见 size_compare）
    - 推理选项：use_mmap=False → True（启用内存映射，减少 RAM 复制）

输出：
    reports/optimization_compare.csv          逐项指标
    reports/optimization_compare.png          对比柱状图
    reports/optimization_qa_detail.csv        准确率每题明细
    reports/optimization_size.csv             模型体积理论对比

运行：
    .\.venv\Scripts\python.exe scripts/benchmark_optimization.py
"""
from __future__ import annotations

import csv
import gc
import sys
import time
import tracemalloc
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)
CSV_MAIN = REPORT_DIR / "optimization_compare.csv"
CSV_QA = REPORT_DIR / "optimization_qa_detail.csv"
CSV_SIZE = REPORT_DIR / "optimization_size.csv"
PNG_PATH = REPORT_DIR / "optimization_compare.png"

SYSTEM_PROMPT = "你是家庭厨师顾问，回答要简洁实用，直接给出结论。"

# 领域 QA 测试集：每题给"必含关键词"，命中越多得分越高（关键词召回率）
QA_DATASET: List[Dict[str, Any]] = [
    {
        "id": "Q1",
        "question": "鸡蛋常温能放多久？应该怎么存放最好？",
        "keywords": ["冷藏", "保鲜", "冰箱"],
    },
    {
        "id": "Q2",
        "question": "番茄炒蛋的关键步骤有哪些？请按顺序简述。",
        "keywords": ["打散", "热油", "番茄", "翻炒"],
    },
    {
        "id": "Q3",
        "question": "猪肉冷冻能保存多久？解冻方式哪种最好？",
        "keywords": ["冷藏解冻", "三个月", "冷冻"],
    },
    {
        "id": "Q4",
        "question": "土豆和洋葱可以放在一起储存吗？为什么？",
        "keywords": ["分开", "发芽", "通风"],
    },
    {
        "id": "Q5",
        "question": "用鸡蛋、葱、米饭，能做哪一道简单家常菜？只给菜名。",
        "keywords": ["蛋炒饭"],
    },
    {
        "id": "Q6",
        "question": "绿叶蔬菜（如菠菜）冰箱冷藏一般几天内吃完？",
        "keywords": ["3", "天", "尽快"],
    },
]


# ---------- 配置：未优化基线 vs 优化后 ----------
@dataclass
class RunConfig:
    label: str
    n_ctx: int
    n_threads: int
    max_tokens: int
    use_mmap: bool


BASELINE = RunConfig(
    label="优化前(基线)",
    n_ctx=4096,           # 浪费的大上下文
    n_threads=1,          # 单线程
    max_tokens=512,       # 输出过长
    use_mmap=False,       # 不使用内存映射
)

OPTIMIZED = RunConfig(
    label="优化后",
    n_ctx=2048,           # 适配应用场景
    n_threads=4,          # 多线程
    max_tokens=256,       # 控制输出长度
    use_mmap=True,        # 启用内存映射，减少 RAM 复制
)


@dataclass
class RunResult:
    label: str
    load_ms: float
    total_infer_ms: float
    avg_infer_ms: float
    total_chars: int
    chars_per_sec: float
    peak_mem_mb: float
    accuracy: float          # 关键词召回率（0~1）
    keyword_hits: int
    keyword_total: int
    answers: List[Dict[str, Any]] = field(default_factory=list)


def _build_llama(cfg: RunConfig):
    from llama_cpp import Llama
    from config import LLM_MODEL_FILE
    from llm.local_llm import _model_path_for_llama

    model_file = _model_path_for_llama(Path(LLM_MODEL_FILE))
    return Llama(
        model_path=model_file,
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        use_mmap=cfg.use_mmap,
        verbose=False,
    )


def _score_answer(answer: str, keywords: List[str]) -> tuple[int, int]:
    """返回 (命中关键词数, 关键词总数)。大小写不敏感，子串匹配。"""
    ans = (answer or "").lower()
    hits = sum(1 for kw in keywords if kw.lower() in ans)
    return hits, len(keywords)


def run_one(cfg: RunConfig) -> RunResult:
    print(f"\n{'=' * 60}")
    print(f"  {cfg.label}: ctx={cfg.n_ctx} threads={cfg.n_threads} "
          f"max_tokens={cfg.max_tokens} use_mmap={cfg.use_mmap}")
    print("=" * 60)

    tracemalloc.start()

    t0 = time.perf_counter()
    llm = _build_llama(cfg)
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"[load] {load_ms:.0f} ms")

    total_infer_ms = 0.0
    total_chars = 0
    hits_sum = 0
    kw_sum = 0
    answers: List[Dict[str, Any]] = []

    for item in QA_DATASET:
        t1 = time.perf_counter()
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": item["question"]},
            ],
            max_tokens=cfg.max_tokens,
            temperature=0.3,
            top_p=0.8,
        )
        dt = (time.perf_counter() - t1) * 1000
        text = out["choices"][0]["message"]["content"].strip()
        hits, kw_total = _score_answer(text, item["keywords"])
        total_infer_ms += dt
        total_chars += len(text)
        hits_sum += hits
        kw_sum += kw_total
        accuracy_q = hits / kw_total if kw_total else 0.0
        print(f"  {item['id']} {dt:>6.0f} ms | {len(text):>3} 字 | "
              f"命中 {hits}/{kw_total} ({accuracy_q*100:.0f}%)")
        answers.append({
            "config": cfg.label,
            "id": item["id"],
            "question": item["question"],
            "answer": text,
            "infer_ms": dt,
            "hits": hits,
            "kw_total": kw_total,
            "accuracy": accuracy_q,
        })

    _, peak = tracemalloc.get_traced_memory()
    peak_mb = peak / (1024 * 1024)
    tracemalloc.stop()

    n = len(QA_DATASET)
    cps = total_chars / (total_infer_ms / 1000) if total_infer_ms > 0 else 0.0
    accuracy = hits_sum / kw_sum if kw_sum else 0.0

    print(f"[summary] 平均推理 {total_infer_ms / n:.0f} ms/题 | "
          f"吞吐 {cps:.1f} 字/秒 | 峰值内存 {peak_mb:.0f} MB | "
          f"准确率 {accuracy * 100:.1f}%")

    del llm
    gc.collect()

    return RunResult(
        label=cfg.label,
        load_ms=load_ms,
        total_infer_ms=total_infer_ms,
        avg_infer_ms=total_infer_ms / n,
        total_chars=total_chars,
        chars_per_sec=cps,
        peak_mem_mb=peak_mb,
        accuracy=accuracy,
        keyword_hits=hits_sum,
        keyword_total=kw_sum,
        answers=answers,
    )


def save_main_csv(results: List[RunResult]) -> None:
    fields = ["label", "load_ms", "total_infer_ms", "avg_infer_ms",
              "total_chars", "chars_per_sec", "peak_mem_mb",
              "accuracy", "keyword_hits", "keyword_total"]
    with open(CSV_MAIN, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            row = {k: getattr(r, k) for k in fields}
            writer.writerow(row)
    print(f"\n[OK] 主对比已保存：{CSV_MAIN}")


def save_qa_csv(results: List[RunResult]) -> None:
    rows = []
    for r in results:
        rows.extend(r.answers)
    if not rows:
        return
    with open(CSV_QA, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] 准确率明细已保存：{CSV_QA}")


def save_size_csv() -> None:
    """量化收益的体积对比（基于 1.5B 参数量估算）。"""
    from config import LLM_MODEL_FILE
    p = Path(LLM_MODEL_FILE)
    actual_mb = p.stat().st_size / (1024 * 1024) if p.is_file() else 0.0

    # 1.5B 参数在不同精度下的典型体积（理论估算 + 实际 GGUF 经验值）
    rows = [
        {"format": "FP32(原始)",      "bits_per_param": 32, "size_mb": 1.5e9 * 4 / 1024 / 1024},
        {"format": "FP16(半精度)",    "bits_per_param": 16, "size_mb": 1.5e9 * 2 / 1024 / 1024},
        {"format": "Q8_0(8bit量化)",  "bits_per_param": 8,  "size_mb": 1.5e9 * 1 / 1024 / 1024},
        {"format": "Q4_0(4bit量化-实测)", "bits_per_param": 4,
         "size_mb": actual_mb if actual_mb else 1.5e9 * 0.5 / 1024 / 1024},
    ]
    fp32 = rows[0]["size_mb"]
    for r in rows:
        r["compress_ratio"] = round(fp32 / r["size_mb"], 2)
        r["size_mb"] = round(r["size_mb"], 1)

    with open(CSV_SIZE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] 量化体积对比已保存：{CSV_SIZE}")


def save_chart(results: List[RunResult]) -> None:
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
    avg_infer = [r.avg_infer_ms / 1000 for r in results]
    cps = [r.chars_per_sec for r in results]
    mem = [r.peak_mem_mb for r in results]
    acc = [r.accuracy * 100 for r in results]

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    colors = ["#94a3b8", "#0d9488"]   # 灰色基线 / 蓝绿优化

    def _bar(ax, values, title, ylabel, fmt="{:.1f}"):
        bars = ax.bar(labels, values, color=colors)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylabel(ylabel)
        for b, v in zip(bars, values):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    fmt.format(v), ha="center", va="bottom", fontsize=10)
        ax.set_ylim(0, max(values) * 1.18 if max(values) > 0 else 1)

    _bar(axes[0, 0], avg_infer, "平均推理耗时 (秒/题，越低越好)", "seconds")
    _bar(axes[0, 1], cps, "吞吐量 (字/秒，越高越好)", "chars/sec")
    _bar(axes[1, 0], mem, "Python 侧峰值内存 (MB)", "MB", fmt="{:.0f}")
    _bar(axes[1, 1], acc, "准确率 (关键词召回率 %)", "%", fmt="{:.1f}%")

    # 在子图下方加百分比改善标签
    if len(results) == 2:
        base, opt = results
        impr_speed = (base.avg_infer_ms - opt.avg_infer_ms) / base.avg_infer_ms * 100
        impr_cps = (opt.chars_per_sec - base.chars_per_sec) / base.chars_per_sec * 100
        impr_mem = (base.peak_mem_mb - opt.peak_mem_mb) / base.peak_mem_mb * 100 \
            if base.peak_mem_mb else 0
        impr_acc = (opt.accuracy - base.accuracy) * 100
        fig.suptitle(
            f"Qwen2.5-1.5B-Instruct Q4_0  优化前 vs 优化后\n"
            f"提速 {impr_speed:+.1f}% | 吞吐 {impr_cps:+.1f}% | "
            f"内存 {impr_mem:+.1f}% | 准确率 {impr_acc:+.1f}pp",
            fontsize=13, fontweight="bold",
        )

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(PNG_PATH, dpi=150, bbox_inches="tight")
    print(f"[OK] 对比图表已保存：{PNG_PATH}")


def print_summary(results: List[RunResult]) -> None:
    print("\n" + "=" * 72)
    print(" 优化前 vs 优化后 总览")
    print("=" * 72)
    header = f"{'配置':<14} {'平均推理':>10} {'吞吐':>10} {'峰值内存':>10} {'准确率':>10}"
    print(header)
    print("-" * 72)
    for r in results:
        print(f"{r.label:<14} "
              f"{r.avg_infer_ms / 1000:>8.2f} 秒 "
              f"{r.chars_per_sec:>8.1f} 字/秒 "
              f"{r.peak_mem_mb:>8.0f} MB "
              f"{r.accuracy * 100:>8.1f} %")

    if len(results) == 2:
        base, opt = results
        print("-" * 72)
        speed_x = base.avg_infer_ms / opt.avg_infer_ms if opt.avg_infer_ms else 0
        print(f"  → 提速     ：{speed_x:.2f}×  "
              f"({(base.avg_infer_ms - opt.avg_infer_ms) / base.avg_infer_ms * 100:+.1f}%)")
        print(f"  → 吞吐提升 ：{(opt.chars_per_sec - base.chars_per_sec) / base.chars_per_sec * 100:+.1f}%")
        if base.peak_mem_mb:
            print(f"  → 内存变化 ：{(opt.peak_mem_mb - base.peak_mem_mb) / base.peak_mem_mb * 100:+.1f}%")
        print(f"  → 准确率   ：{(opt.accuracy - base.accuracy) * 100:+.1f} 个百分点")


def main() -> None:
    print("=" * 72)
    print(" AI 模型轻量化优化对比  (按老师要求：优化前/后 + 速度/内存/准确率)")
    print("=" * 72)

    results: List[RunResult] = []
    for cfg in (BASELINE, OPTIMIZED):
        try:
            results.append(run_one(cfg))
        except Exception as e:
            print(f"!!! {cfg.label} 失败：{e}")

    if not results:
        print("没有任何成功的样例，退出。")
        return

    save_main_csv(results)
    save_qa_csv(results)
    save_size_csv()
    save_chart(results)
    print_summary(results)


if __name__ == "__main__":
    main()
