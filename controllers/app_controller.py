from db.db_manager import init_db
from ui import LoginWindow, MainWindow
from utils.logger import get_logger

logger = get_logger("controller")


class AppController:
    """登录窗口 → 主窗口的总控。"""

    def __init__(self):
        init_db()
        logger.info("数据库初始化完成")

        self.login = LoginWindow()
        self.main: MainWindow | None = None
        self.login.login_success.connect(self._enter_main)
        self.login.show()

    def _enter_main(self, user: dict) -> None:
        logger.info("进入主界面 user=%s role=%s", user.get("username"), user.get("role"))
        self.main = MainWindow(current_user=user)
        self.main.show()
        self.login.close()
