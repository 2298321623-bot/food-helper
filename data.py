import os
import json
import sqlite3
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
                   FOREIGN KEY (recipe_id) REFERENCES recipes(recipee_id)
                   )''')
    
    conn.commit()
    conn.close()
    print("✅ 全部数据表初始化完成")

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


if __name__ == "__main__":
    init_database()
    import_recipes_from_json()  # 导入你的爬虫数据
    