"""项目路径与 AI 模块配置（组员 C）。"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# 本地 GGUF 模型（Day3-4：需运行 scripts/download_qwen_model.py 下载）
# 可通过环境变量 FOOD_HELPER_MODEL 指定无中文路径的模型文件（Windows 推荐）
_env_model = os.environ.get("FOOD_HELPER_MODEL")
LLM_MODEL_DIR = PROJECT_ROOT / "models"
LLM_MODEL_FILE = Path(_env_model) if _env_model else LLM_MODEL_DIR / "qwen2.5-1.5b-instruct-q4_0.gguf"

# 句向量模型（首次使用会自动从 HuggingFace 缓存）
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# 默认菜谱样例（组员 B 数据库就绪前用于联调）
SAMPLE_RECIPES_JSON = PROJECT_ROOT / "data" / "sample_recipes.json"

# LLM 生成参数
LLM_TEMPERATURE = 0.3
LLM_TOP_P = 0.8
LLM_MAX_TOKENS = 512
LLM_CONTEXT_SIZE = 2048

# 检索默认返回条数
RECIPE_TOP_K = 10
INGREDIENT_MATCH_WEIGHT = 0.7
SEMANTIC_MATCH_WEIGHT = 0.3

# Week2：有限食材模式 — 缺料越少排名越靠前（在综合分上乘以系数）
MISSING_INGREDIENT_PENALTY = 0.08
FULL_MATCH_BONUS = 0.15

# Week2：按需求做菜 — 标签/时间/难度 与 语义 权重
PREFERENCE_FILTER_WEIGHT = 0.6
PREFERENCE_SEMANTIC_WEIGHT = 0.4
PREFERENCE_MIN_FILTER_SCORE = 0.25

# DeepSeek API（Day14，从环境变量读取，勿提交密钥）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.environ.get(
    "DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"
)
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
