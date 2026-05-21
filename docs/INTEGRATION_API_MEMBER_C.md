# 组员 C — 模块接口说明（供 A/B 联调）

## 目录结构

| 模块 | 路径 | 说明 |
|------|------|------|
| 配置 | `config.py` | 模型路径、检索权重、DeepSeek API |
| LLM 基类 | `llm/base_llm.py` | `BaseLLM`、`generate_recipe()` |
| 提示词 | `llm/prompts.py` | Week2 Markdown 输出规范 |
| 本地模型 | `llm/local_llm.py` | `LocalLLM`（Qwen GGUF） |
| 云端模型 | `llm/cloud_llm.py` | `CloudLLM`（DeepSeek API） |
| 工厂 | `fallback/llm.py` | `get_llm()`、`generate_recipe_with_fallback()` |
| 向量 | `rag/embeddings.py` | `EmbeddingService`、`cosine_similarity` |
| 检索 | `rag/core.py` | 食材检索、按需求筛选 |
| 服务门面 | `services/recipe_service.py` | **推荐 A/B 只依赖此文件** |

## 组员 A（UI / 多线程）

```python
from services.recipe_service import get_recipe_service

svc = get_recipe_service()

# 模式1：用现有食材做菜（Week2：缺料越少越靠前）
results = svc.search_by_ingredients(["鸡蛋", "番茄", "盐", "油"])

# 模式2：按需求做菜（Week2）
results = svc.search_by_preferences(
    diet="减脂餐", cooking_time="15分钟内", difficulty="简单"
)

# Week2：在 QRunnable 中生成完整菜谱（本地优先，失败自动切云端）
text = svc.generate_recipe_text(
    ["鸡蛋", "番茄"],
    recipe_name="番茄炒蛋",
    diet="家常菜",
    cooking_time="15分钟内",
    difficulty="简单",
)
```

返回字段（每条菜谱）：

- `name`, `ingredients`, `tags`, `time`, `diff`, `description`, `steps`
- `match_score`：综合匹配分（0~1）
- `matched_ingredients` / `missing_ingredients`：模式1 专用

UI 已集成：`ui/main_window.py` 中「生成智能食谱」「AI 生成详细步骤」。

## 组员 B（数据库）

1. `recipes` 表建议增加 `embedding BLOB` 字段（384 维 float32）。
2. 写入菜谱后计算向量（见 Week1 文档）。
3. 启动或登录后注入：

```python
from services.recipe_service import get_recipe_service
get_recipe_service().load_from_db(recipe_dict_list)
```

字段需包含：`name`, `ingredients`, `tags`, `time`/`cooking_time`, `diff`/`difficulty`, `description`, `steps`（可选）。

## 环境准备

```powershell
cd d:\food-helper
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Week1 自测
python scripts/test_week1_member_c.py

# Week2 自测
python scripts/test_week2_member_c.py

# 本地模型（可选）
python scripts/download_qwen_model.py

# 云端兜底：复制 .env.example 为 .env 并填写 DEEPSEEK_API_KEY
```

## Week1 / Week2 交付对照

| 阶段 | 任务 | 对应代码 |
|------|------|----------|
| W1 Day1-7 | 本地 LLM + 向量 + 食材检索 | `llm/`, `rag/`, `services/` |
| W2 Day8-9 | 有限食材优先匹配 | `rag/core.py` `_apply_ingredient_rank_boost` |
| W2 Day10-11 | 按需求筛选 | `search_by_preferences` |
| W2 Day12-13 | 提示词与输出格式 | `llm/prompts.py` |
| W2 Day14 | CloudLLM + 双引擎 | `llm/cloud_llm.py`, `fallback/llm.py` |
