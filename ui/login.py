# 文件路径：ui/login.py
"""登录窗口：真实数据库校验 + 注册对话框。"""

from PyQt6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QDialog, QFormLayout, QComboBox, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from db.db_manager import verify_user, register_user, log_operation
from utils.logger import get_logger

logger = get_logger("ui.login")


class LoginWindow(QWidget):
    """登录窗口。校验成功后通过 login_success 信号传递用户信息。"""

    login_success = pyqtSignal(dict)  # {user_id, username, role}

    def __init__(self):
        super().__init__()
        self.current_user: dict | None = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("家庭食材助手 - 欢迎登录")
        self.setFixedSize(440, 520)
        self.setWindowFlags(Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.label_title = QLabel("家庭食材与智能食谱助手")
        self.label_title.setObjectName("loginTitle")
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_subtitle = QLabel("轻松管理食材 · 智能推荐食谱")
        self.label_subtitle.setObjectName("loginSubtitle")
        self.label_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.edit_user = QLineEdit()
        self.edit_user.setPlaceholderText("请输入用户名（默认管理员 admin / 123456）")
        self.edit_user.setFixedHeight(42)

        self.edit_pwd = QLineEdit()
        self.edit_pwd.setPlaceholderText("请输入密码")
        self.edit_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pwd.setFixedHeight(42)
        self.edit_pwd.returnPressed.connect(self.handle_login)

        self.btn_login = QPushButton("登录系统")
        self.btn_login.setObjectName("primaryBtn")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setFixedHeight(42)
        self.btn_login.setMinimumWidth(140)
        self.btn_login.clicked.connect(self.handle_login)

        self.btn_register = QPushButton("新用户注册")
        self.btn_register.setObjectName("secondaryBtn")
        self.btn_register.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_register.setFixedHeight(42)
        self.btn_register.setMinimumWidth(140)
        self.btn_register.clicked.connect(self.handle_register)

        self.label_status = QLabel("")
        self.label_status.setObjectName("loginStatus")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(0, 0, 0, 0)

        label_user = QLabel("用户名")
        label_user.setObjectName("formLabel")
        label_pwd = QLabel("密码")
        label_pwd.setObjectName("formLabel")

        form_layout.addWidget(label_user)
        form_layout.addWidget(self.edit_user)
        form_layout.addSpacing(4)
        form_layout.addWidget(label_pwd)
        form_layout.addWidget(self.edit_pwd)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_register)
        btn_layout.addStretch()

        container = QWidget()
        container.setObjectName("loginContainer")
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(32, 32, 32, 28)
        container_layout.setSpacing(14)
        container_layout.addWidget(self.label_title)
        container_layout.addWidget(self.label_subtitle)
        container_layout.addSpacing(6)
        container_layout.addLayout(form_layout)
        container_layout.addWidget(self.label_status)
        container_layout.addSpacing(4)
        container_layout.addLayout(btn_layout)
        container.setLayout(container_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(container)
        self.setLayout(layout)

    # ---------- 业务 ----------
    def _set_status(self, text: str, ok: bool = False) -> None:
        color = "#0f766e" if ok else "#dc2626"
        self.label_status.setStyleSheet(f"color: {color};")
        self.label_status.setText(text)

    def handle_login(self) -> None:
        username = self.edit_user.text().strip()
        password = self.edit_pwd.text()
        if not username or not password:
            self._set_status("请输入用户名和密码")
            return
        try:
            user = verify_user(username, password)
        except Exception as e:
            logger.exception("登录数据库异常")
            self._set_status(f"系统错误：{e}")
            return
        if not user:
            self._set_status("用户名或密码不正确")
            log_operation(username, "登录失败", "")
            logger.warning("登录失败 username=%s", username)
            return
        self.current_user = user
        self._set_status(f"欢迎，{user['username']}（{user['role']}）", ok=True)
        log_operation(user["username"], "登录成功", f"role={user['role']}")
        logger.info("登录成功 username=%s role=%s", user["username"], user["role"])
        self.login_success.emit(user)

    def handle_register(self) -> None:
        dialog = RegisterDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.edit_user.setText(dialog.username)
            self.edit_pwd.setText(dialog.password)
            self._set_status("注册成功，可直接登录", ok=True)


class RegisterDialog(QDialog):
    """注册对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.username = ""
        self.password = ""
        self.setWindowTitle("新用户注册")
        self.setMinimumWidth(360)

        self.edit_user = QLineEdit()
        self.edit_user.setPlaceholderText("用户名，3-20 位")
        self.edit_pwd1 = QLineEdit()
        self.edit_pwd1.setPlaceholderText("密码，至少 4 位")
        self.edit_pwd1.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pwd2 = QLineEdit()
        self.edit_pwd2.setPlaceholderText("再次确认密码")
        self.edit_pwd2.setEchoMode(QLineEdit.EchoMode.Password)
        self.role_box = QComboBox()
        self.role_box.addItems(["user", "admin"])
        self.role_box.setToolTip("普通用户只能使用 AI 功能，管理员可查看操作日志")

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("用户名", self.edit_user)
        form.addRow("密码", self.edit_pwd1)
        form.addRow("确认密码", self.edit_pwd2)
        form.addRow("用户角色", self.role_box)

        btn_ok = QPushButton("注册")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addLayout(btn_row)

    def _on_ok(self) -> None:
        username = self.edit_user.text().strip()
        pwd1 = self.edit_pwd1.text()
        pwd2 = self.edit_pwd2.text()
        if pwd1 != pwd2:
            QMessageBox.warning(self, "注册失败", "两次输入的密码不一致。")
            return
        ok, msg = register_user(username, pwd1, self.role_box.currentText())
        if not ok:
            QMessageBox.warning(self, "注册失败", msg)
            return
        log_operation(username, "注册账号", f"role={self.role_box.currentText()}")
        logger.info("注册账号 username=%s", username)
        self.username = username
        self.password = pwd1
        self.accept()
