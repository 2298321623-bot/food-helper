import os
import json
import sqlite3
import numpy as np
from datetime import datetime

DB_FILE = "food.db"

def connect_db():
    """连接数据库"""
    return sqlite3.connect(DB_FILE)

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

def init_database():
    """创建所有表"""
    conn = connect_db()
    cursor = conn.cursor()

    # # 强制删除旧表，确保每次都是新建
    # conn.execute("DROP TABLE IF EXISTS users")
    # conn.execute("DROP TABLE IF EXISTS ingredients")
    # conn.execute("DROP TABLE IF EXISTS recipes")
    # conn.execute("DROP TABLE IF EXISTS shopping_lists")
    # conn.execute("DROP TABLE IF EXISTS favorites")

    #创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users(
                   user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE) ''')

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
                   embedding BLOB,  -- 新增：存储向量
                   user_id INTEGER,
                   FOREIGN KEY (user_id) REFERENCES users(id)
                   source TEXT
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
    
    conn.commit()
    conn.close()
    print("✅ 全部数据表初始化完成")

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
        print("❌ 无法打开 data.json")
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
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users(username,password) VALUES (?,?)", (username, pwd))
    conn.commit()
    conn.close()

#查找用户
def get_user(username):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()
    return user

#修改用户
def update_pwd(user_id, new_pwd):
    conn = connect_db()
    c = conn.cursor()
    c.execute("UPDATE users SET password=? WHERE id=?", (new_pwd, user_id))
    conn.commit()
    conn.close()

#删除用户
def delete_user(user_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


#====食材表CRUD====
#增加食材
def add_ingredient(name, category, quantity, unit, expire_date, user_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO ingredients(name,category,quantity,unit,expire_date,user_id)
        VALUES (?,?,?,?,?,?)
    ''', (name, category, quantity, unit, expire_date, user_id))
    conn.commit()
    conn.close()

#查找食材
def get_ingredients(user_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM ingredients WHERE user_id=?", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

#修改食材
def update_ingredient(id, new_quantity):
    conn = connect_db()
    c = conn.cursor()
    c.execute("UPDATE ingredients SET quantity=? WHERE id=?", (new_quantity, id))
    conn.commit()
    conn.close()

#删除食材
def delete_ingredient(id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("DELETE FROM ingredients WHERE id=?", (id,))
    conn.commit()
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
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM recipes WHERE user_id=?", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

#删除食谱
def delete_recipe(recipe_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("DELETE FROM recipes WHERE recipe_id=?", (recipe_id,))
    conn.commit()
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
    print("\n==== 🍲 智能食谱推荐（仅 Numpy） ====")
    data = recommend_recipes(user_id)
    for i, (score, name, ings) in enumerate(data, 1):
        print(f"{i}. {name} | 匹配度：{score:.1%}")



if __name__ == "__main__":
    init_database()
    import_recipes_from_json()  # 导入你的爬虫数据
    show_recommend(user_id=1, top_n=5)