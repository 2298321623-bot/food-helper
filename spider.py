"""菜谱爬虫：xiangha.com 热门菜谱抓取 + 清洗 + 增量去重写入 data.json。

特性：
- requests 带超时 / 失败重试 / User-Agent
- pandas 去重、空值清洗、结构标准化
- 关键节点 try/except + logging，不让异常中断主进程
- 提供 run(...) 函数和进度回调，方便被 UI 后台线程调用
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, List, Dict

import requests
from bs4 import BeautifulSoup

from utils.logger import get_logger

logger = get_logger("spider")

DATA_JSON = Path(__file__).resolve().parent / "data.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT = 8  # 秒
RETRY = 2


def _fetch(url: str) -> str | None:
    """带重试的 GET，失败返回 None。"""
    for attempt in range(RETRY + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning("请求失败 [%s/%s] %s: %s", attempt + 1, RETRY + 1, url, e)
            time.sleep(0.5 * (attempt + 1))
    return None


def _parse_list_page(html: str) -> List[str]:
    """从列表页 HTML 提取菜谱详情页链接。"""
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    for p in soup.find_all("p", attrs={"class": "name kw"}):
        a = p.find("a")
        if a and a.get("href"):
            links.append(a["href"])
    return links


def _parse_detail(html: str) -> Dict | None:
    """从详情页 HTML 提取 {name, ingredients}。失败返回 None。"""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("h2", class_="dish-title")
    if not title:
        return None
    name = title.get_text(strip=True)
    ingredients: List[str] = []
    for cell in soup.find_all("div", class_="cell"):
        classes = cell.get("class", [])
        if "cell" in classes and "kw" not in classes:
            a = cell.find("a")
            if a:
                txt = a.get_text(strip=True)
                if txt:
                    ingredients.append(txt)
    if not name or not ingredients:
        return None
    return {"name": name, "ingredients": ingredients}


def _clean_with_pandas(records: List[Dict]) -> List[Dict]:
    """使用 pandas 去重 + 空值过滤。"""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas 未安装，使用基础去重")
        seen = set()
        cleaned = []
        for r in records:
            key = r.get("name")
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(r)
        return cleaned

    df = pd.DataFrame(records)
    if df.empty:
        return []
    df = df.dropna(subset=["name"])
    df = df.drop_duplicates(subset=["name"], keep="first")
    df = df[df["ingredients"].map(lambda x: isinstance(x, list) and len(x) > 0)]
    df = df.reset_index(drop=True)
    return df.to_dict(orient="records")


def _load_existing() -> List[Dict]:
    if not DATA_JSON.exists():
        return []
    try:
        with open(DATA_JSON, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception as e:
        logger.warning("读取已有 data.json 失败：%s，将以空列表起步", e)
        return []


def _save(records: List[Dict]) -> None:
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def run(pages: int = 3, progress_cb: Callable[[str], None] | None = None) -> Dict:
    """主流程：抓取 N 页热门菜谱，与本地合并去重。

    返回统计字典 {fetched, new, total, failed_pages, failed_details}
    """
    base = "https://www.xiangha.com/caipu/z-recai/hot-{n}"

    def _tip(msg: str) -> None:
        logger.info(msg)
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    existing = _load_existing()
    existing_names = {r.get("name") for r in existing if isinstance(r, dict)}
    fetched: List[Dict] = []
    failed_pages = 0
    failed_details = 0

    for n in range(pages):
        _tip(f"正在抓取列表页 {n + 1}/{pages}…")
        html = _fetch(base.format(n=n))
        if not html:
            failed_pages += 1
            continue
        links = _parse_list_page(html)
        _tip(f"列表页 {n + 1} 解析得 {len(links)} 条菜谱链接")
        for i, link in enumerate(links, 1):
            detail_html = _fetch(link)
            if not detail_html:
                failed_details += 1
                continue
            item = _parse_detail(detail_html)
            if item:
                fetched.append(item)
            else:
                failed_details += 1
            if i % 5 == 0:
                _tip(f"  └ 已处理 {i}/{len(links)}")

    _tip(f"抓取完成，原始 {len(fetched)} 条，开始清洗…")
    cleaned_new = _clean_with_pandas(fetched)
    merged = existing + [r for r in cleaned_new if r.get("name") not in existing_names]
    merged = _clean_with_pandas(merged)

    try:
        _save(merged)
    except Exception as e:
        logger.exception("保存 data.json 失败")
        raise RuntimeError(f"保存失败：{e}")

    stats = {
        "fetched": len(fetched),
        "new": len(merged) - len(existing),
        "total": len(merged),
        "failed_pages": failed_pages,
        "failed_details": failed_details,
    }
    _tip(
        f"完成：新增 {stats['new']} 条，总计 {stats['total']} 条；"
        f"失败列表页 {failed_pages}，失败详情页 {failed_details}"
    )
    return stats


if __name__ == "__main__":
    print(run(pages=2))
