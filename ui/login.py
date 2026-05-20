# 文件路径：ui/login.py

from PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("家庭食材助手 - 欢迎登录")
        self.setFixedSize(420, 450)
        self.setWindowFlags(Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet("background-color: #f3f7f3;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # 1. 顶部艺术大标题
        self.label_title = QLabel("家庭食材与智能食谱助手")
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #27ae60; letter-spacing: 0.8px;")

        self.label_subtitle = QLabel("轻松管理食材、生成智能食谱")
        self.label_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_subtitle.setStyleSheet("color: #6b7c72; font-size: 13px; margin-bottom: 10px;")

        # 2. 表单输入框
        self.edit_user = QLineEdit()
        self.edit_user.setPlaceholderText("请输入用户名")
        self.edit_user.setFixedHeight(44)
        self.edit_user.setStyleSheet("border-radius: 12px; background-color: #f8faf8; padding-left: 12px;")

        self.edit_pwd = QLineEdit()
        self.edit_pwd.setPlaceholderText("请输入密码")
        self.edit_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pwd.setFixedHeight(44)
        self.edit_pwd.setStyleSheet("border-radius: 12px; background-color: #f8faf8; padding-left: 12px;")

        # 3. 功能操作按钮
        self.btn_login = QPushButton("登录系统")
        self.btn_login.setObjectName("secondaryBtn")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setFixedSize(150, 42)
        self.btn_login.setStyleSheet("font-size: 14px; font-weight: 700;")

        self.btn_register = QPushButton("新用户注册")
        self.btn_register.setObjectName("secondaryBtn")
        self.btn_register.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_register.setFixedSize(150, 42)
        self.btn_register.setStyleSheet("font-size: 14px; font-weight: 700;")

        # 4. 重新构建紧凑有序的表单布局
        form_layout = QVBoxLayout()
        form_layout.setSpacing(14) # 标签与输入框之间的亲密间距
        form_layout.setContentsMargins(0, 0, 0, 0)

        label_user = QLabel("用户名：")
        label_user.setStyleSheet("font-size: 13px; font-weight: bold; color: #3a4b42; margin-top: 12px;")
        label_pwd = QLabel("密码：")
        label_pwd.setStyleSheet("font-size: 13px; font-weight: bold; color: #3a4b42; margin-top: 12px;")

        form_layout.addWidget(label_user)
        form_layout.addWidget(self.edit_user)
        form_layout.addWidget(label_pwd)
        form_layout.addWidget(self.edit_pwd)

        # 5. 底部按钮横向对齐
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_register)
        btn_layout.addStretch()

        # 6. 将所有内容打包进漂亮的白色卡片主容器
        container = QWidget()
        container.setObjectName("loginContainer")
        container.setStyleSheet("QWidget#loginContainer { background-color: #ffffff; border-radius: 16px; }")
        
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(28, 28, 28, 28) # 增大留白，拒绝拥挤
        container_layout.setSpacing(20) # 控制大模块之间的上下平铺间距

        container_layout.addWidget(self.label_title)
        container_layout.addWidget(self.label_subtitle)
        container_layout.addSpacing(10) # 额外撑开标题与表单的距离
        container_layout.addLayout(form_layout)
        container_layout.addSpacing(20) # 额外撑开表单与按钮的距离
        container_layout.addLayout(btn_layout)
        container.setLayout(container_layout)

        # 7. 全局居中布局
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(container)
        self.setLayout(layout)