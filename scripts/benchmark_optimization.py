"""
真实 LLM 轻量化对比：Q8_0 基线 vs Q4_0 量化
=========================================

本脚本只做真正的轻量级 LLM 量化对比，不再混入其它模型。

对比对象：
1. Qwen2.5-1.5B-Instruct Q8_0（8-bit，作为优化前基线）
2. Qwen2.5-1.5B-Instruct Q4_0（4-bit，作为优化后轻量化模型）

两者使用同一套测试集、同一套推理参数，实测：
- 模型文件体积
- 加载时间
- 平均推理耗时
- tokens/s
- 进程级 RSS 内存
- 问答准确率（概念组命中率）

运行：
    python scripts/benchmark_optimization.py --download-missing
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)

CSV_MAIN = REPORT_DIR / "optimization_compare.csv"
CSV_QA = REPORT_DIR / "optimization_qa_detail.csv"
CSV_SIZE = REPORT_DIR / "optimization_size.csv"
PNG_PATH = REPORT_DIR / "optimization_compare.png"

SYSTEM_PROMPT = "你是家庭厨师顾问，回答要简洁实用，直接给出结论。"


def _mb(num_bytes: float) -> float:
    return num_bytes / (1024 * 1024)


def _round(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


class MemorySampler:
    """采样真实进程 RSS，覆盖 llama.cpp 原生内存。"""

    def __init__(self, interval_s: float = 0.02):
        import psutil

        self.interval_s = interval_s
        self.process = psutil.Process(os.getpid())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_rss = self.sample_once()

    def sample_once(self) -> int:
        return int(self.process.memory_info().rss)

    def start(self) -> None:
        if self._thread is not None:
            return

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.peak_rss = max(self.peak_rss, self.sample_once())
                except Exception:
                    pass
                time.sleep(self.interval_s)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        try:
            self.peak_rss = max(self.peak_rss, self.sample_once())
        except Exception:
            pass


QA_DATASET: List[Dict[str, Any]] = [
    {
        "id": "Q1",
        "question": "鸡蛋常温能放多久？应该怎么存放最好？",
        "target_groups": [
            ["冷藏", "冰箱", "冷藏室"],
            ["保鲜", "保存", "存放"],
        ],
    },
    {
        "id": "Q2",
        "question": "番茄炒蛋的关键步骤有哪些？请按顺序简述。",
        "target_groups": [
            ["打散", "搅散", "搅匀"],
            ["热油", "锅热", "下油", "倒油"],
            ["番茄", "西红柿"],
            ["翻炒", "炒匀", "快炒"],
        ],
    },
    {
        "id": "Q3",
        "question": "猪肉冷冻能保存多久？解冻方式哪种最好？",
        "target_groups": [
            ["三个月", "3个月", "90天", "3-6个月", "六个月"],
            ["冷藏解冻", "冰箱解冻", "冷藏室解冻", "冷藏慢慢解冻"],
            ["冷冻"],
        ],
    },
    {
        "id": "Q4",
        "question": "土豆和洋葱可以放在一起储存吗？为什么？",
        "target_groups": [
            ["分开", "不要放在一起", "不建议一起", "最好分开"],
            ["发芽", "催熟", "加快变质"],
            ["通风", "阴凉", "干燥"],
        ],
    },
    {
        "id": "Q5",
        "question": "用鸡蛋、葱、米饭，能做哪一道简单家常菜？只给菜名。",
        "target_groups": [
            ["蛋炒饭", "鸡蛋炒饭", "葱花蛋炒饭", "炒饭"],
        ],
    },
    {
        "id": "Q6",
        "question": "绿叶蔬菜（如菠菜）冰箱冷藏一般几天内吃完？",
        "target_groups": [
            ["2-3天", "3天", "三天", "2天", "3到5天", "3-5天"],
            ["尽快", "尽早", "及时"],
        ],
    },
]


@dataclass
class ModelRunConfig:
    label: str
    quantization: str
    model_path: str
    n_ctx: int
    n_threads: int
    max_tokens: int
    use_mmap: bool


@dataclass
class ModelRunResult:
    label: str
    quantization: str
    model_path: str
    model_size_mb: float
    n_ctx: int
    n_threads: int
    max_tokens: int
    use_mmap: bool
    load_ms: float
    total_infer_ms: float
    avg_infer_ms: float
    total_tokens: int
    avg_tokens_per_answer: float
    tokens_per_sec: float
    ms_per_token: float
    total_chars: int
    chars_per_sec: float
    rss_before_mb: float
    rss_after_load_mb: float
    peak_rss_mb: float
    peak_delta_mb: float
    infer_peak_rss_mb: float
    infer_peak_delta_mb: float
    accuracy: float
    keyword_hits: int
    keyword_total: int
    answers: List[Dict[str, Any]] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower().replace(" ", "")


def _score_answer(answer: str, target_groups: Sequence[Sequence[str]]) -> tuple[int, int]:
    normalized = _normalize_text(answer)
    hits = 0
    for group in target_groups:
        if any(_normalize_text(alias) in normalized for alias in group):
            hits += 1
    return hits, len(target_groups)


def _run_subprocess(args: List[str], description: str) -> None:
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{description} 失败\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )


def _build_model_specs() -> List[ModelRunConfig]:
    from config import LLM_MODEL_DIR, LLM_MODEL_FILE

    model_dir = Path(LLM_MODEL_DIR)
    q4_path = Path(LLM_MODEL_FILE)
    q8_path = model_dir / "qwen2.5-1.5b-instruct-q8_0.gguf"
    common = {
        "n_ctx": 2048,
        "n_threads": min(4, os.cpu_count() or 4),
        "max_tokens": 256,
        "use_mmap": True,
    }
    return [
        ModelRunConfig(
            label="优化前-Q8_0",
            quantization="Q8_0",
            model_path=str(q8_path),
            **common,
        ),
        ModelRunConfig(
            label="优化后-Q4_0",
            quantization="Q4_0",
            model_path=str(q4_path),
            **common,
        ),
    ]


def _ensure_models(download_missing: bool) -> List[ModelRunConfig]:
    specs = _build_model_specs()
    missing = [spec for spec in specs if not Path(spec.model_path).is_file()]
    if not missing:
        return specs

    if not download_missing:
        names = "、".join(f"{spec.quantization}:{spec.model_path}" for spec in missing)
        raise FileNotFoundError(
            f"缺少基准模型：{names}\n"
            "请先运行 `python scripts/download_qwen_model.py --variant q8_0`，"
            "或给本脚本加上 `--download-missing`。"
        )

    for spec in missing:
        variant = spec.quantization.lower()
        print(f"[download] 缺少 {spec.quantization}，开始自动下载…")
        _run_subprocess(
            [sys.executable, str(ROOT / "scripts" / "download_qwen_model.py"), "--variant", variant],
            f"下载 {spec.quantization}",
        )
    return specs


def _worker(config_path: Path, output_path: Path) -> None:
    from llama_cpp import Llama
    from llm.local_llm import _model_path_for_llama

    cfg = ModelRunConfig(**json.loads(config_path.read_text(encoding="utf-8")))
    model_path = Path(cfg.model_path)
    if not model_path.is_file():
        raise FileNotFoundError(f"模型不存在：{model_path}")

    sampler = MemorySampler()
    sampler.start()
    rss_before = sampler.sample_once()

    t0 = time.perf_counter()
    llm = Llama(
        model_path=_model_path_for_llama(model_path),
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        use_mmap=cfg.use_mmap,
        verbose=False,
    )
    load_ms = (time.perf_counter() - t0) * 1000
    rss_after_load = sampler.sample_once()
    gc.collect()
    infer_base_rss = sampler.sample_once()
    overall_peak_before_infer = sampler.peak_rss
    sampler.peak_rss = infer_base_rss

    total_infer_ms = 0.0
    total_tokens = 0
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
            temperature=0.2,
            top_p=0.8,
        )
        infer_ms = (time.perf_counter() - t1) * 1000
        text = out["choices"][0]["message"]["content"].strip()
        usage = out.get("usage") or {}
        completion_tokens = int(usage.get("completion_tokens") or 0)
        hits, kw_total = _score_answer(text, item["target_groups"])
        acc = hits / kw_total if kw_total else 0.0

        total_infer_ms += infer_ms
        total_tokens += completion_tokens
        total_chars += len(text)
        hits_sum += hits
        kw_sum += kw_total
        answers.append(
            {
                "config": cfg.label,
                "quantization": cfg.quantization,
                "id": item["id"],
                "question": item["question"],
                "answer": text,
                "infer_ms": _round(infer_ms, 3),
                "completion_tokens": completion_tokens,
                "hits": hits,
                "kw_total": kw_total,
                "accuracy": _round(acc, 4),
            }
        )

    sampler.stop()
    infer_peak_rss = sampler.peak_rss
    peak_rss = max(overall_peak_before_infer, infer_peak_rss)

    result = ModelRunResult(
        label=cfg.label,
        quantization=cfg.quantization,
        model_path=str(model_path),
        model_size_mb=_round(_mb(model_path.stat().st_size), 1),
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        max_tokens=cfg.max_tokens,
        use_mmap=cfg.use_mmap,
        load_ms=_round(load_ms, 3),
        total_infer_ms=_round(total_infer_ms, 3),
        avg_infer_ms=_round(total_infer_ms / len(QA_DATASET), 3),
        total_tokens=total_tokens,
        avg_tokens_per_answer=_round(total_tokens / len(QA_DATASET), 3),
        tokens_per_sec=_round(total_tokens / (total_infer_ms / 1000) if total_infer_ms else 0.0, 4),
        ms_per_token=_round(total_infer_ms / total_tokens if total_tokens else 0.0, 4),
        total_chars=total_chars,
        chars_per_sec=_round(total_chars / (total_infer_ms / 1000) if total_infer_ms else 0.0, 4),
        rss_before_mb=_round(_mb(rss_before)),
        rss_after_load_mb=_round(_mb(rss_after_load)),
        peak_rss_mb=_round(_mb(peak_rss)),
        peak_delta_mb=_round(_mb(peak_rss - rss_before)),
        infer_peak_rss_mb=_round(_mb(infer_peak_rss)),
        infer_peak_delta_mb=_round(_mb(infer_peak_rss - infer_base_rss)),
        accuracy=_round(hits_sum / kw_sum if kw_sum else 0.0, 4),
        keyword_hits=hits_sum,
        keyword_total=kw_sum,
        answers=answers,
    )

    del llm
    gc.collect()
    output_path.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding="utf-8")


def run_experiment(specs: Sequence[ModelRunConfig]) -> List[ModelRunResult]:
    print("\n" + "=" * 80)
    print(" [实验] Q8_0 基线 vs Q4_0 量化模型（真实 GGUF 对比）")
    print("=" * 80)

    results: List[ModelRunResult] = []
    for cfg in specs:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            output_path = Path(tmp_dir) / "result.json"
            config_path.write_text(json.dumps(asdict(cfg), ensure_ascii=False), encoding="utf-8")
            print(
                f"\n>>> {cfg.label} | model={Path(cfg.model_path).name} | "
                f"ctx={cfg.n_ctx} threads={cfg.n_threads} max_tokens={cfg.max_tokens}"
            )
            _run_subprocess(
                [sys.executable, str(Path(__file__)), "--worker", str(config_path), str(output_path)],
                cfg.label,
            )
            result = ModelRunResult(**json.loads(output_path.read_text(encoding="utf-8")))
            print(
                f"    体积 {result.model_size_mb:.1f} MB | 加载 {result.load_ms:.0f} ms | "
                f"平均推理 {result.avg_infer_ms:.0f} ms/题 | {result.ms_per_token:.1f} ms/token | "
                f"{result.tokens_per_sec:.2f} tokens/s | "
                f"推理峰值增量 {result.infer_peak_delta_mb:.1f} MB | "
                f"准确率 {result.accuracy * 100:.1f}%"
            )
            results.append(result)
    return results


def save_csv(results: Sequence[ModelRunResult]) -> None:
    if not results:
        return

    fields = [
        "label",
        "quantization",
        "model_path",
        "model_size_mb",
        "n_ctx",
        "n_threads",
        "max_tokens",
        "use_mmap",
        "load_ms",
        "total_infer_ms",
        "avg_infer_ms",
        "total_tokens",
        "avg_tokens_per_answer",
        "tokens_per_sec",
        "ms_per_token",
        "total_chars",
        "chars_per_sec",
        "rss_before_mb",
        "rss_after_load_mb",
        "peak_rss_mb",
        "peak_delta_mb",
        "infer_peak_rss_mb",
        "infer_peak_delta_mb",
        "accuracy",
        "keyword_hits",
        "keyword_total",
    ]
    with CSV_MAIN.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow({key: getattr(result, key) for key in fields})

    qa_rows: List[Dict[str, Any]] = []
    for result in results:
        qa_rows.extend(result.answers)
    with CSV_QA.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(qa_rows[0].keys()))
        writer.writeheader()
        writer.writerows(qa_rows)

    print(f"[OK] 已保存：{CSV_MAIN}")
    print(f"[OK] 已保存：{CSV_QA}")


def save_size_csv(results: Sequence[ModelRunResult]) -> None:
    if not results:
        return
    base_size = max(result.model_size_mb for result in results)
    rows = []
    for result in results:
        rows.append(
            {
                "label": result.label,
                "quantization": result.quantization,
                "model_path": result.model_path,
                "size_mb": result.model_size_mb,
                "compress_ratio_vs_largest": _round(base_size / result.model_size_mb, 3),
            }
        )

    with CSV_SIZE.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] 已保存：{CSV_SIZE}")


def _setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt

    return plt


def save_chart(results: Sequence[ModelRunResult]) -> None:
    if len(results) < 1:
        return
    try:
        plt = _setup_matplotlib()
    except ImportError:
        print("matplotlib 未安装，跳过图表生成")
        return

    labels = [r.label for r in results]
    infer_sec = [r.ms_per_token for r in results]
    tps = [r.tokens_per_sec for r in results]
    size_mb = [r.model_size_mb for r in results]
    acc = [r.accuracy * 100 for r in results]
    colors = ["#94a3b8", "#0d9488"]

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))

    def _bar(ax, values, title, ylabel, fmt="{:.2f}"):
        bars = ax.bar(labels, values, color=colors[: len(values)])
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylabel(ylabel)
        upper = max(values) * 1.18 if max(values) > 0 else 1
        ax.set_ylim(0, upper)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                fmt.format(value),
                ha="center",
                va="bottom",
                fontsize=10,
            )

    _bar(axes[0, 0], infer_sec, "单位 token 耗时（ms/token，越低越好）", "ms/token")
    _bar(axes[0, 1], tps, "吞吐量（tokens/s，越高越好）", "tokens/s")
    _bar(axes[1, 0], size_mb, "模型体积（MB，越低越好）", "MB", fmt="{:.1f}")
    _bar(axes[1, 1], acc, "准确率（概念组召回 %）", "%", fmt="{:.1f}%")

    if len(results) == 2:
        base, opt = results
        speed_up = base.ms_per_token / opt.ms_per_token if opt.ms_per_token else 0.0
        size_change = (opt.model_size_mb - base.model_size_mb) / base.model_size_mb * 100 if base.model_size_mb else 0.0
        fig.suptitle(
            "Qwen2.5-1.5B-Instruct GGUF 真实量化对比\n"
            f"Q8_0 -> Q4_0 | 单位 token 提速 {speed_up:.2f}x | 体积变化 {size_change:+.1f}% | "
            f"准确率变化 {(opt.accuracy - base.accuracy) * 100:+.1f}pp",
            fontsize=13,
            fontweight="bold",
        )

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(PNG_PATH, dpi=150, bbox_inches="tight")
    print(f"[OK] 已保存：{PNG_PATH}")


def print_summary(results: Sequence[ModelRunResult]) -> None:
    if not results:
        return
    print("\n" + "-" * 80)
    print(" Q8_0 vs Q4_0 真实量化总览")
    print("-" * 80)
    for result in results:
        print(
            f"{result.label:<14} | {result.model_size_mb:>7.1f} MB | "
            f"{result.ms_per_token:>7.1f} ms/token | {result.tokens_per_sec:>6.2f} tokens/s | "
            f"{result.infer_peak_delta_mb:>7.1f} MB | {result.accuracy * 100:>6.1f}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-missing", action="store_true")
    parser.add_argument("--worker", nargs=2, metavar=("CONFIG", "OUTPUT"))
    args = parser.parse_args()

    if args.worker:
        _worker(Path(args.worker[0]), Path(args.worker[1]))
        return

    print("=" * 84)
    print(" AI 模型轻量化优化对比（真实 Q8_0 vs Q4_0 量化模型）")
    print("=" * 84)

    try:
        specs = _ensure_models(download_missing=args.download_missing)
        results = run_experiment(specs)
        save_csv(results)
        save_size_csv(results)
        save_chart(results)
        print_summary(results)
    except Exception as exc:
        print(f"!!! 实验失败：{exc}")


if __name__ == "__main__":
    main()
