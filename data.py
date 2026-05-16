import os
import sqlite3

DB_FILE = "food.db"

def connect_db():
    """连接数据库"""
    return sqlite3.connect(DB_FILE)

def init_database():
    """创建所有表"""
    conn = connect_db()
    cursor = conn.cursor()

    #创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users(
                   user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE) ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ingredients(
                   ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   name TEXT NOT NULL
                   quantity REAL
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
                   incredients TEXT,
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
                   user_id INTEGER NOT NULL
                   recipe_id INTEGER NOT NULL,
                   create_time TEXT,
                   FOREIGN KEY (user_id) REFERENCES users(id),
                   FOREIGN KEY (recipe_id) REFERENCES recipes(recipee_id)
                   )''')
    
    conn.commit()
    conn.close()
    print("✅ 全部数据表初始化完成")

if __name__ == "__main__":
    init_database()