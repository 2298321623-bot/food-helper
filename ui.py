from PyQt6.QtWidgets import *
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, Qt
from PyQt6.QtGui import QFont

class WorkerSignals(QObject):
    finished = pyqtSignal()
    result = pyqtSignal(object)
    error = pyqtSignal(str)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("家庭食材管理与智能食谱助手")
        self.setFixedSize(350, 250)
        self.setWindowFlags(Qt.WindowType.WindowCloseButtonHint)

        font = QFont("微软雅黑", 10)
        self.setFont(font)

        self.label_user = QLabel("用户名：")
        self.edit_user = QLineEdit()
        self.edit_user.setPlaceholderText("请输入用户名")

        self.label_pwd = QLabel("密  码：")
        self.edit_pwd = QLineEdit()
        self.edit_pwd.setPlaceholderText("请输入密码")
        self.edit_pwd.setEchoMode(QLineEdit.EchoMode.Password)

        self.btn_login = QPushButton("登录")
        self.btn_register = QPushButton("注册")

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(40, 30, 40, 30)

        layout.addWidget(self.label_user)
        layout.addWidget(self.edit_user)
        layout.addWidget(self.label_pwd)
        layout.addWidget(self.edit_pwd)
        layout.addWidget(self.btn_login)
        layout.addWidget(self.btn_register)

        self.setLayout(layout)

class MainWindow(QTabWidget):
    def __init__(self):
        super().__init__()
        self.init_window()
        self.init_ingredient_tab()
        self.init_recipe_tab()
        self.init_shop_tab()
        self.init_knowledge_tab()

    def init_window(self):
        self.setWindowTitle("家庭食材管理与智能食谱助手")
        self.setFixedSize(1000, 650)
        font = QFont("微软雅黑", 10)
        self.setFont(font)

class MainWindow(QTabWidget):
    def __init__(self):
        super().__init__()
        self.init_window()
        self.init_ingredient_tab()
        self.init_recipe_tab()
        self.init_shop_tab()
        self.init_knowledge_tab()

    def init_window(self):
        self.setWindowTitle("家庭食材管理与智能食谱助手")
        self.setFixedSize(1000, 650)
        font = QFont("微软雅黑", 10)
        self.setFont(font)

    def init_ingredient_tab(self):
        self.ingredient_tab = QWidget()
        self.ingredient_table = QTableWidget()
        self.ingredient_table.setColumnCount(6)
        self.ingredient_table.setHorizontalHeaderLabels(
            ["食材名称", "数量/单位", "保质期", "食材分类", "存放位置", "操作"]
        )
        self.ingredient_table.horizontalHeader().setStretchLastSection(True)

        self.btn_add = QPushButton("➕ 添加食材")
        self.btn_add.clicked.connect(self.show_add_ingredient_dialog)

        layout = QVBoxLayout()
        layout.addWidget(self.btn_add)
        layout.addWidget(self.ingredient_table)
        self.ingredient_tab.setLayout(layout)
        self.addTab(self.ingredient_tab, "食材管理")

    def show_add_ingredient_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加食材")
        dialog.setFixedSize(350, 350)

        name_edit = QLineEdit()
        quantity_edit = QLineEdit()
        expiry_edit = QDateEdit()
        expiry_edit.setDisplayFormat("yyyy-MM-dd")
        category_box = QComboBox()
        category_box.addItems(["蔬菜", "肉类", "水果", "调料", "主食", "水产", "蛋奶"])
        location_edit = QLineEdit()

        btn_confirm = QPushButton("确认添加")
        btn_cancel = QPushButton("取消")

        form_layout = QFormLayout()
        form_layout.addRow("食材名称：", name_edit)
        form_layout.addRow("数量/单位：", quantity_edit)
        form_layout.addRow("保质期：", expiry_edit)
        form_layout.addRow("食材分类：", category_box)
        form_layout.addRow("存放位置：", location_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_confirm)
        btn_layout.addWidget(btn_cancel)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        dialog.setLayout(main_layout)

        dialog.exec()

    def init_recipe_tab(self):
        self.recipe_tab = QWidget()
        group = QGroupBox("食谱筛选")
        mode_box = QComboBox()
        mode_box.addItems(["用现有食材做", "按需求做"])
        diet_box = QComboBox()
        diet_box.addItems(["家常菜", "减脂餐", "增肌餐", "素食", "控糖"])
        time_box = QComboBox()
        time_box.addItems(["15分钟内", "15-30分钟", "30分钟以上"])
        diff_box = QComboBox()
        diff_box.addItems(["简单", "中等", "困难"])

        btn_generate = QPushButton("🔍 生成食谱")

        form_layout = QFormLayout()
        form_layout.addRow("生成模式：", mode_box)
        form_layout.addRow("饮食偏好：", diet_box)
        form_layout.addRow("烹饪时间：", time_box)
        form_layout.addRow("难度：", diff_box)
        form_layout.addRow("", btn_generate)
        group.setLayout(form_layout)

        self.recipe_list = QListWidget()
        self.recipe_list.addItem("【待生成】食谱将显示在这里")

        layout = QVBoxLayout()
        layout.addWidget(group)
        layout.addWidget(QLabel("📋 推荐食谱"))
        layout.addWidget(self.recipe_list)
        self.recipe_tab.setLayout(layout)
        self.addTab(self.recipe_tab, "智能食谱")

    def init_shop_tab(self):
        self.shop_tab = QWidget()
        self.shop_table = QTableWidget()
        self.shop_table.setColumnCount(4)
        self.shop_table.setHorizontalHeaderLabels(["食材名称", "数量", "单位", "已购买"])

        btn_export = QPushButton("📤 导出购物清单")
        btn_clear = QPushButton("🗑 清空清单")

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_export)
        btn_layout.addWidget(btn_clear)

        layout = QVBoxLayout()
        layout.addLayout(btn_layout)
        layout.addWidget(self.shop_table)
        self.shop_tab.setLayout(layout)
        self.addTab(self.shop_tab, "购物清单")

    def init_knowledge_tab(self):
        self.knowledge_tab = QWidget()
        nav_list = QListWidget()
        nav_list.addItems(["食材保存方法", "食物相克相宜", "厨房小技巧", "人群饮食建议"])
        content_edit = QTextEdit()
        content_edit.setPlaceholderText("选择左侧分类，查看饮食知识")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(nav_list)
        splitter.addWidget(content_edit)
        splitter.setSizes([200, 600])

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        self.knowledge_tab.setLayout(layout)
        self.addTab(self.knowledge_tab, "饮食知识")