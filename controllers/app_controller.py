from db import *
from ui import LoginWindow, MainWindow


class AppController:
    def __init__(self):
        # 数据库初始化
        init_db()
        self.db = connect_db()
        self.cursor = self.db.cursor()
        
        self.login = LoginWindow()
        self.main = MainWindow()
        self.login.btn_login.clicked.connect(self.show_main)
        self.login.btn_register.clicked.connect(lambda: print("注册功能待对接数据库"))
        self.login.show()

    def show_main(self):
        self.login.close()
        self.main.show()

    