# 文件路径：ui/login.py

from PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("家庭食材助手 - 欢迎登录")
        self.setFixedSize(440, 480)
        self.setWindowFlags(Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.label_title = QLabel("家庭食材与智能食谱助手")
        self.label_title.setObjectName("loginTitle")
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_subtitle = QLabel("轻松管理食材 · 智能推荐食谱")
        self.label_subtitle.setObjectName("loginSubtitle")
        self.label_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.edit_user = QLineEdit()
        self.edit_user.setPlaceholderText("请输入用户名")
        self.edit_user.setFixedHeight(42)

        self.edit_pwd = QLineEdit()
        self.edit_pwd.setPlaceholderText("请输入密码")
        self.edit_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pwd.setFixedHeight(42)

        self.btn_login = QPushButton("登录系统")
        self.btn_login.setObjectName("primaryBtn")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setFixedHeight(42)
        self.btn_login.setMinimumWidth(140)

        self.btn_register = QPushButton("新用户注册")
        self.btn_register.setObjectName("secondaryBtn")
        self.btn_register.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_register.setFixedHeight(42)
        self.btn_register.setMinimumWidth(140)

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
        container_layout.setSpacing(16)
        container_layout.addWidget(self.label_title)
        container_layout.addWidget(self.label_subtitle)
        container_layout.addSpacing(8)
        container_layout.addLayout(form_layout)
        container_layout.addSpacing(12)
        container_layout.addLayout(btn_layout)
        container.setLayout(container_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(container)
        self.setLayout(layout)
