import os
import json
import sqlite3
import numpy as np
from datetime import datetime

DB_PATH = "data.db"

def connect_db():
    """连接数据库"""
    return sqlite3.connect(DB_PATH)

def get_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def to_json(data):
    return json.dumps(data, ensure_ascii=False)

def to_list(json_str):
    return json.loads(json_str) if json_str else []

# 向量转字节（存入SQLite）
def serialize_embedding(embedding):
    return np.array(embedding, dtype=np.float32).tobytes()

# 字节转回向量（读取用，Day10用）
def deserialize_embedding(blob):
    return np.frombuffer(blob, dtype=np.float32)


def _table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _ensure_column(cursor, table_name: str, column_name: str, column_def: str) -> None:
    if column_name not in _table_columns(cursor, table_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def _migrate_schema(cursor) -> None:
    """为旧版 data.db 补齐新增列，避免 CREATE TABLE IF NOT EXISTS 跳过后 INSERT 失败。"""
    _ensure_column(cursor, "users", "password", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(cursor, "users", "role", "TEXT NOT NULL DEFAULT 'user'")


def init_db():
    """创建所有表"""
    conn = connect_db()
    cursor = conn.cursor()

    #创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users(
                   user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE,
                   password TEXT NOT NULL,
                   role TEXT NOT NULL DEFAULT 'user') ''')
    _migrate_schema(cursor)
    
    # 插入默认管理员（如不存在）；密码使用 SHA-256+salt 安全存储
    cursor.execute("SELECT user_id FROM users WHERE username='admin'")
    if cursor.fetchone() is None:
        import hashlib as _hl, secrets as _sec
        _salt = _sec.token_hex(8)
        _hashed = _hl.sha256((_salt + "123456").encode()).hexdigest()
        cursor.execute(
            "INSERT INTO users(username,password,role) VALUES('admin',?,'admin')",
            (f"{_salt}${_hashed}",),
        )

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ingredients(
                   ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   name TEXT NOT NULL,
                   quantity REAL,
                   unit TEXT,
                   expiry_date INTEGER,
                   storage_location TEXT,
                   category TEXT,
                   create_time TEXT,
                   FOREIGN KEY (user_id) REFERENCES user(user_id)
                    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recipes(
                   recipe_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL,
                   ingredients TEXT,
                   steps TEXT,
                   cooking_time INTEGER,
                   difficulty INTEGER,
                   tags TEXT,
                   nutrition TEXT,
                   embedding BLOB,
                   user_id INTEGER,
                   source_info TEXT,
                   FOREIGN KEY (user_id) REFERENCES users(id)
                   ) ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS shopping_lists(
                   item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   name TEXT,
                   quantity REAL,
                   unit TEXT,
                   checked INTEGER DEFAULT 0,
                   FOREIGN KEY(user_id) REFERENCES users(id)
                   )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS favorites(
                   favorite_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   recipe_id INTEGER NOT NULL,
                   create_time TEXT,
                   FOREIGN KEY (user_id) REFERENCES users(id),
                   FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id)
                   )''')
    
    # 日志表：操作记录
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS operation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        operate_type TEXT,
        content TEXT,
        create_time TIMESTAMP DEFAULT (datetime('now','localtime'))
    )
    ''')
    
    conn.commit()
    conn.close()
    print("[OK] 全部数据表初始化完成")


# ============================================================
# 用户认证 / 操作日志：基础必做功能补充
# ============================================================
import hashlib
import secrets


def _hash_password(password: str, salt: str) -> str:
    """SHA-256(salt + password)，避免明文存储。"""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _is_legacy_plain(stored: str) -> bool:
    """老的明文密码（如初始化的 admin/123456）走 fallback 比对。"""
    return "$" not in stored


def register_user(username: str, password: str, role: str = "user") -> tuple[bool, str]:
    """注册新用户。返回 (ok, message)。"""
    username = (username or "").strip()
    if not username or not password:
        return False, "用户名和密码不能为空"
    if len(password) < 4:
        return False, "密码至少 4 位"
    salt = secrets.token_hex(8)
    stored = f"{salt}${_hash_password(password, salt)}"
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users(username, password, role) VALUES (?, ?, ?)",
            (username, stored, role),
        )
        conn.commit()
        conn.close()
        return True, "注册成功"
    except sqlite3.IntegrityError:
        return False, "该用户名已被占用"
    except Exception as e:
        return False, f"注册失败：{e}"


def verify_user(username: str, password: str) -> dict | None:
    """登录校验，成功返回 {user_id, username, role}，失败返回 None。"""
    username = (username or "").strip()
    if not username or not password:
        return None
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, password, role FROM users WHERE username=?",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    user_id, uname, stored, role = row
    if _is_legacy_plain(stored):
        # 兼容 init_db 中插入的明文 admin
        if stored == password:
            return {"user_id": user_id, "username": uname, "role": role}
        return None
    try:
        salt, hashed = stored.split("$", 1)
    except ValueError:
        return None
    if _hash_password(password, salt) == hashed:
        return {"user_id": user_id, "username": uname, "role": role}
    return None


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    """修改密码。需提供旧密码校验。"""
    if not new_password or len(new_password) < 4:
        return False, "新密码至少 4 位"
    user = verify_user(username, old_password)
    if not user:
        return False, "旧密码不正确"
    salt = secrets.token_hex(8)
    stored = f"{salt}${_hash_password(new_password, salt)}"
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password=? WHERE username=?",
            (stored, username),
        )
        conn.commit()
        conn.close()
        return True, "密码修改成功"
    except Exception as e:
        return False, f"修改失败：{e}"


def log_operation(username: str, operate_type: str, content: str = "") -> None:
    """写入一条操作日志。异常自动吞掉，避免影响主流程。"""
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO operation_log(username, operate_type, content) VALUES (?, ?, ?)",
            (username or "anonymous", operate_type, content[:500]),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def fetch_operation_logs(limit: int = 200, username: str | None = None) -> list[tuple]:
    """读取最近的操作日志，可按用户名过滤。"""
    conn = connect_db()
    cursor = conn.cursor()
    if username:
        cursor.execute(
            "SELECT create_time, username, operate_type, content FROM operation_log "
            "WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit),
        )
    else:
        cursor.execute(
            "SELECT create_time, username, operate_type, content FROM operation_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def list_users() -> list[tuple]:
    """管理员查看：所有用户。"""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, role FROM users ORDER BY user_id")
    rows = cursor.fetchall()
    conn.close()
    return rows

def import_recipes_with_embedding(json_path="data.json"):
    # 1. 加载数据
    with open(json_path, "r", encoding="utf-8") as f:
        recipe_list = json.load(f)

    # 2. 加载组员C的向量模型
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")

    conn = connect_db()
    c = conn.cursor()

    for recipe in recipe_list:
        name = recipe.get("name", "")
        ingredients = recipe.get("ingredients", [])
        # 构造用于生成向量的文本
        text = name + " " + " ".join([str(i) for i in ingredients])

        # 3. 调用向量化
        embedding = model.encode(text)
        emb_blob = serialize_embedding(embedding)

        # 4. 插入数据库（带向量）
        c.execute('''
            INSERT INTO recipes
            (name, ingredients, steps, cooking_time, difficulty, tags, nutrition, embedding, user_id)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''', (
            name,
            to_json(ingredients),
            to_json([]),
            0, "", to_json([]), to_json({}),
            emb_blob,
            1
        ))

    conn.commit()
    conn.close()
    print("导入完成")

#将data.json导入数据库
def import_recipes_from_json():
    # 1. 读文件
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            raw = f.read()
    except:
        print("[ERROR] 无法打开 data.json")
        return

    data = json.loads(raw)
    
    # 直接入库
    conn = connect_db()
    c = conn.cursor()
    for item in data:
        name = item.get("name", "").strip()
        if not name:
            name = "未知菜品"
        c.execute('INSERT INTO recipes (name, ingredients) VALUES (?,?)',
                  (name, to_json(item.get("ingredients", []))))
    
    conn.commit()
    conn.close()
    print(f"成功导入 {len(data)} 条食谱到数据库")

#====用户CRUD====
#注册用户
def add_user(username, pwd):
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",(username,pwd,"user"))
        conn.commit()
        add_log(username, "用户注册", "新用户注册")
        return True   # 注册成功
    except Exception:
        return False  # 失败：用户名重复/数据库报错
    finally:
        conn.close()

#登录验证
def check_login(username,pwd):
    conn = connect_db()
    cur = conn.cursor()
    res=cur.execute("select role from users where username=? and password=?",(username,pwd)).fetchone()
    conn.close()
    if res:
        add_log(username, "登录", "用户登录系统")
        return res[0] #匹配成功返回 admin / user
    else:
        return None #账号密码错误

#查找用户
def get_user(username):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.commit()
        return True  # 成功
    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误信息：", e)
        conn.rollback()
        return False  # 失败
    finally:
        # 无论成功失败，都关闭连接
        conn.close()

#修改用户
def update_pwd(user_id, new_pwd):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE id=?", (new_pwd, user_id))
        conn.commit()
        return True  # 成功
    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误信息：", e)
        conn.rollback()
        return False  # 失败
    finally:
        conn.close()

#删除用户
def delete_user(user_id):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        return True  # 成功

    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误", e)
        conn.rollback()
        return False  # 失败
    finally:
        conn.close()


#====食材表CRUD====
#增加食材
def add_ingredient(name, category, quantity, unit, expire_date, user_id):
    conn = connect_db()
    c = conn.cursor()
    # 先查重：同名食材不能新增
    c.execute("select id from ingredient where name=?",(name,))
    if c.fetchone():
        conn.close()
        return False # 重复添加失败
    try:
        c.execute('''
        INSERT INTO ingredients(name,category,quantity,unit,expire_date,user_id)
        VALUES (?,?,?,?,?,?)
        ''', (name, category, quantity, unit, expire_date, user_id))
        conn.commit()
        add_log(user_id, "新增食材", f"食材：{name}")
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

#查找食材
def get_ingredients(user_id):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("SELECT * FROM ingredients WHERE user_id=?", (user_id,))
        data = c.fetchall()
        return True  # 成功
    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误信息：", e)
        conn.rollback()
        return False  # 失败
    finally:
        conn.close()
        return data

#修改食材
def update_ingredient(id, name, category, quantity, unit, expire_date, user_id):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute('''
        UPDATE ingredients 
        SET name=?, category=?, quantity=?, unit=?, expire_date=?
        WHERE id=?
        ''', (name, category, quantity, unit, expire_date, id))
        conn.commit()
        add_log(user_id, "修改食材", f"修改ID:{id}，名称：{name}")
        return True  # 成功
    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误信息：", e)
        conn.rollback()
        return False  # 失败
    finally:
        conn.close()

#删除食材
def delete_ingredient(id, user_id):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("DELETE FROM ingredients WHERE id=?", (id,))
        conn.commit()
        add_log(user_id, "删除食材", f"删除食材ID：{id}")
        return True  # 成功
    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误信息：", e)
        conn.rollback()
        return False  # 失败
    finally:
        conn.close()


#====食谱CRUD====
#增加食谱
def add_recipe(name, ingredients, steps, time, diff, tags, nutrition, user_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO recipes(name,ingredients,steps,cooking_time,difficulty,tags,nutrition,user_id)
        VALUES (?,?,?,?,?,?,?,?)
    ''', (
        name, to_json(ingredients), to_json(steps), time, diff,
        to_json(tags), to_json(nutrition), user_id
    ))
    conn.commit()
    conn.close()

#查找食谱
def get_recipes(user_id):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("SELECT * FROM recipes WHERE user_id=?", (user_id,))
        data = c.fetchall()
        return True  # 成功

    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误信息：", e)
        conn.rollback()
        return False  # 失败

    finally:
        conn.close()
        return data

#删除食谱
def delete_recipe(recipe_id):
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("DELETE FROM recipes WHERE recipe_id=?", (recipe_id,))
        conn.commit()
        return True  # 成功

    except Exception as e:
        # 出错了！打印错误，数据库回滚（撤销操作）
        print("错误信息：", e)
        conn.rollback()
        return False  # 失败

    finally:
        conn.close()


#====购物CRUD====
#增加物品
def add_shop_item(user_id, name, quantity, unit):
    conn = connect_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO shopping_lists(user_id,name,quantity,unit)
        VALUES (?,?,?,?)
    ''', (user_id, name, quantity, unit))
    conn.commit()
    conn.close()

#修改物品（勾选已购买）
def check_item(item_id, status):
    conn = connect_db()
    c = conn.cursor()
    c.execute("UPDATE shopping_lists SET checked=? WHERE item_id=?", (status, item_id))
    conn.commit()
    conn.close()

#查找物品
def get_shop_list(user_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM shopping_lists WHERE user_id=?", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

#删除物品


#====喜欢CRUD====
#增加喜欢
def add_favorite(user_id, recipe_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO favorites(user_id,recipe_id,create_time)
        VALUES (?,?,?)
    ''', (user_id, recipe_id, get_time()))
    conn.commit()
    conn.close()

#查找所有喜欢
def get_favorites(user_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM favorites WHERE user_id=?", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

#删除喜欢

#智能推荐算法
# 计算余弦相似度（纯 numpy 实现）
def cosine_similarity(a, b):
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    return dot / (norm_a * norm_b)

# 推荐食谱（根据用户食材）
def recommend_recipes(user_id=1, top_n=5):
    conn = connect_db()
    c = conn.cursor()

    # 1. 获取用户食材
    c.execute("SELECT name FROM ingredients WHERE user_id=?", (user_id,))
    user_ingredients = [row[0] for row in c.fetchall()]

    if not user_ingredients:
        conn.close()
        return []

    # 2. 读取所有食谱
    c.execute("SELECT recipe_id, name, ingredients, embedding FROM recipes WHERE embedding IS NOT NULL")
    all_recipes = c.fetchall()
    conn.close()

    # 3. 生成用户食材的向量（简单统计向量）
    all_ingredients = set()
    for rec in all_recipes:
        ings = json.loads(rec[2])
        all_ingredients.update(ings)
    all_ingredients = list(all_ingredients)

    # 用户食材向量
    user_vec = np.array([1.0 if ing in user_ingredients else 0.0 for ing in all_ingredients])

    # 4. 计算相似度
    result = []
    for rec in all_recipes:
        rec_id, name, ing_str, emb_blob = rec
        rec_vec = np.frombuffer(emb_blob, dtype=np.float32)

        # 相似度
        score = cosine_similarity(user_vec, rec_vec)
        result.append((score, name, json.loads(ing_str)))

    # 5. 排序
    result.sort(reverse=True)
    return result[:top_n]

# 展示推荐结果
def show_recommend(user_id=1):
    print("\n==== 智能食谱推荐（仅 Numpy） ====")
    data = recommend_recipes(user_id)
    for i, (score, name, ings) in enumerate(data, 1):
        print(f"{i}. {name} | 匹配度：{score:.1%}")

# 列出临期食材
def get_remain_days(expire_date_str):
    today = datetime.now().date()  # 今天日期
    expire_date = datetime.strptime(expire_date_str, "%Y-%m-%d").date()
    remain_days = (expire_date - today).days  # 剩余天数
    return remain_days

# 添加日志（所有操作都会调用这个）
def add_log(username, operate_type, content):
    try:
        conn = sqlite3.connect("food.db")
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO operation_log (username, operate_type, content)
            VALUES (?, ?, ?)
        ''', (username, operate_type, content))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

def get_all_logs():
    conn = connect_db()
    c = conn.cursor()
    # 查询整张日志表所有数据
    c.execute("SELECT * FROM operation_log ORDER BY create_time DESC")
    res = c.fetchall()
    conn.close()
    return res


# ============================================================
# 食材持久化：与 MainWindow 对接的干净 CRUD（按当前用户隔离）
# ============================================================

def db_load_ingredients(user_id: int) -> list[dict]:
    """读取指定用户的全部食材，返回 list[dict]。

    dict 字段：ingredient_id, name, quantity, unit, expiry_date, category, location
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute(
            "SELECT ingredient_id, name, quantity, unit, expiry_date, category, storage_location "
            "FROM ingredients WHERE user_id=? ORDER BY ingredient_id",
            (user_id,),
        )
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            iid, name, qty, unit, expiry_str, category, location = row
            result.append({
                "ingredient_id": iid,
                "name": name or "",
                "amount": float(qty or 1),
                "unit": unit or "个",
                "expiry_date_str": expiry_str or "",
                "category": category or "蔬菜",
                "location": location or "",
            })
        return result
    except Exception as e:
        print(f"[ERROR] db_load_ingredients: {e}")
        return []


def db_add_ingredient(user_id: int, name: str, quantity: float,
                      unit: str, expiry_date_str: str, category: str,
                      location: str) -> int:
    """新增一条食材记录，返回新插入的 ingredient_id（失败返回 -1）。

    :param user_id: 当前登录用户 ID
    :param name: 食材名称
    :param quantity: 数量
    :param unit: 单位
    :param expiry_date_str: 保质期字符串 YYYY-MM-DD
    :param category: 分类
    :param location: 存放位置
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO ingredients(user_id, name, quantity, unit, expiry_date, category, storage_location, create_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, quantity, unit, expiry_date_str, category, location, get_time()),
        )
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return new_id
    except Exception as e:
        print(f"[ERROR] db_add_ingredient: {e}")
        return -1


def db_update_ingredient(ingredient_id: int, name: str, quantity: float,
                         unit: str, expiry_date_str: str, category: str,
                         location: str) -> bool:
    """更新食材记录。返回是否成功。

    :param ingredient_id: 要更新的食材主键
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute(
            "UPDATE ingredients SET name=?, quantity=?, unit=?, expiry_date=?, "
            "category=?, storage_location=? WHERE ingredient_id=?",
            (name, quantity, unit, expiry_date_str, category, location, ingredient_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] db_update_ingredient: {e}")
        return False


def db_delete_ingredient(ingredient_id: int) -> bool:
    """删除一条食材记录。返回是否成功。

    :param ingredient_id: 要删除的食材主键
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("DELETE FROM ingredients WHERE ingredient_id=?", (ingredient_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] db_delete_ingredient: {e}")
        return False


# ============================================================
# 购物清单持久化：与 MainWindow 对接的干净 CRUD
# ============================================================

def db_load_shopping(user_id: int) -> list[dict]:
    """读取指定用户的全部购物清单，返回 list[dict]。

    dict 字段：item_id, name, quantity, unit, bought
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute(
            "SELECT item_id, name, quantity, unit, checked FROM shopping_lists "
            "WHERE user_id=? ORDER BY item_id",
            (user_id,),
        )
        rows = c.fetchall()
        conn.close()
        return [
            {
                "item_id": r[0],
                "name": r[1] or "",
                "quantity": str(r[2] or 1),
                "unit": r[3] or "个",
                "bought": bool(r[4]),
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[ERROR] db_load_shopping: {e}")
        return []


def db_add_shopping_item(user_id: int, name: str, quantity: str,
                         unit: str, bought: bool = False) -> int:
    """新增购物清单项，返回新插入的 item_id（失败返回 -1）。

    :param user_id: 当前登录用户 ID
    :param name: 商品名称
    :param quantity: 数量（字符串）
    :param unit: 单位
    :param bought: 是否已购买
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO shopping_lists(user_id, name, quantity, unit, checked) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, float(quantity) if quantity else 1, unit, int(bought)),
        )
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return new_id
    except Exception as e:
        print(f"[ERROR] db_add_shopping_item: {e}")
        return -1


def db_update_shopping_item(item_id: int, bought: bool) -> bool:
    """更新购物清单项的已购买状态。

    :param item_id: 购物清单项主键
    :param bought: 是否已购买
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("UPDATE shopping_lists SET checked=? WHERE item_id=?", (int(bought), item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] db_update_shopping_item: {e}")
        return False


def db_delete_shopping_item(item_id: int) -> bool:
    """删除购物清单项。

    :param item_id: 购物清单项主键
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("DELETE FROM shopping_lists WHERE item_id=?", (item_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] db_delete_shopping_item: {e}")
        return False


def db_clear_shopping(user_id: int) -> bool:
    """清空某用户的全部购物清单。

    :param user_id: 当前登录用户 ID
    """
    try:
        conn = connect_db()
        c = conn.cursor()
        c.execute("DELETE FROM shopping_lists WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] db_clear_shopping: {e}")
        return False
    return res