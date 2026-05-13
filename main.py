import sys
from PyQt6.QtWidgets import QApplication
from ui import LoginWindow, MainWindow

def switch_to_main():
    login.close()
    main.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    login = LoginWindow()
    main = MainWindow()

    login.btn_login.clicked.connect(switch_to_main)
    login.btn_register.clicked.connect(lambda: print("注册功能待对接数据库"))

    login.show()
    sys.exit(app.exec())