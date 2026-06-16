from PyQt6.QtWidgets import *
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, Qt, QDate, QThreadPool
from PyQt6.QtGui import QColor
import csv
import json
import re
from datetime import datetime

from config import INGREDIENT_UNITS, SERVING_OPTIONS
from services.inventory_service import (
    DeductionRow,
    apply_deductions,
    format_amount_display,
    normalize_pantry_item,
    parse_amount_text,
    plan_deductions,
    recipe_ingredients_from_dict,
)
from services.nutrition_service import summarize_pantry_nutrition
from db.db_manager import (
    db_load_ingredients, db_add_ingredient, db_update_ingredient, db_delete_ingredient,
    db_load_shopping, db_add_shopping_item, db_update_shopping_item,
    db_delete_shopping_item, db_clear_shopping,
)

LOCATION_UNSET = "未添加位置"
LOCATION_OPTIONS = [LOCATION_UNSET, "冷藏区", "冷冻区", "常温区"]


def normalize_location(value: str | None) -> str:
    text = (value or "").strip()
    return text if text in LOCATION_OPTIONS and text != LOCATION_UNSET else ""


def display_location(value: str | None) -> str:
    return normalize_location(value) or LOCATION_UNSET


# (WorkerSignals 与 Worker 类保持原样不变...)
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

def _recognize_voice_once(timeout: float = 6.0, phrase_time_limit: float = 8.0) -> str:
    """阻塞调用：录音 + 离线/在线识别（在后台线程中运行）。"""
    import speech_recognition as sr  # 局部导入：未装依赖时不影响主程序

    r = sr.Recognizer()
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    try:
        return r.recognize_google(audio, language="zh-CN")
    except Exception:
        try:
            return r.recognize_sphinx(audio, language="zh-CN")
        except Exception as e:
            raise RuntimeError(f"语音识别失败：{e}")


class MainWindow(QTabWidget):
    def __init__(self, current_user: dict | None = None):
        super().__init__()
        self.current_user = current_user or {"username": "guest", "role": "user", "user_id": 0}
        self._user_id: int = int(self.current_user.get("user_id") or 0)
        self.ingredients = []   # 内存列表，每项含 ingredient_id 用于持久化
        self.shopping_items = []  # 内存列表，每项含 item_id 用于持久化
        self._active_recipe_for_cooking = None
        self._expiry_alert_checked_this_session = False
        self.recipes = [
            {"name": "番茄炒蛋", "tags": ["家常菜"], "time": "15分钟内", "diff": "简单", "ingredients": ["鸡蛋", "番茄"], "description": "用番茄和鸡蛋快速炒制，口感酸甜，营养丰富。"},
            {"name": "蒜蓉虾仁", "tags": ["家常菜", "增肌餐"], "time": "15-30分钟", "diff": "中等", "ingredients": ["虾仁", "蒜"], "description": "鲜嫩虾仁搭配蒜蓉，适合轻松下厨。"},
            {"name": "清炒西蓝花", "tags": ["家常菜", "减脂餐", "素食"], "time": "15分钟内", "diff": "简单", "ingredients": ["西蓝花", "胡萝卜"], "description": "低卡高纤维，适合减脂和素食者。"},
            {"name": "红烧牛肉", "tags": ["家常菜"], "time": "30分钟以上", "diff": "困难", "ingredients": ["牛肉", "酱油", "葱姜"], "description": "经典红烧牛肉，适合周末家庭聚餐。"},
            {"name": "三文鱼沙拉", "tags": ["增肌餐", "控糖"], "time": "15分钟内", "diff": "简单", "ingredients": ["三文鱼", "生菜", "牛油果"], "description": "清爽低脂，适合健身和控糖需求。"}
        ]
        self.knowledge_books = {
            "食材保存方法": "1. 蔬菜水果应保持干燥，放入保鲜袋后排出多余空气。\n2. 肉类冷藏前用保鲜膜包好，避免交叉污染。\n3. 面包、馒头放在阴凉干燥处，冷藏可延长保存时间。",
            "食物相克相宜": "1. 牛牛奶与海鲜同食可能导致消化不良。\n2. 菠菜与豆制品搭配有助于铁吸收。\n3. 西红柿与黄瓜同食不会影响营养，但醋会破坏维生素C。",
            "厨房小技巧": "1. 姜片用保鲜膜包好后放冰箱，可减少异味。\n2. 洗菜时加入少许盐能去除泥沙。\n3. 切辣椒后立即用水洗手，可减少辣椒刺激。",
            "人群饮食建议": "1. 儿童饮食应注意营养均衡，多吃蔬菜水果。\n2. 青年人可适当补充蛋白质，加强体力恢复。\n3. 老年人宜少油少盐，多吃高纤维食物。"
        }
        self.init_window()
        self._load_from_db()   # 从数据库加载用户数据
        self.init_dashboard_tab()
        self.init_ingredient_tab()
        self.init_recipe_tab()
        self.init_shop_tab()
        self.init_knowledge_tab()
        self.init_stats_tab()
        if self.current_user.get("role") == "admin":
            self.init_admin_tab()
        self.currentChanged.connect(self._on_main_tab_changed)
        self.thread_pool = QThreadPool.globalInstance()
        self._refresh_llm_status_label()

    def showEvent(self, event):
        super().showEvent(event)
        self._maybe_show_expiry_alert_once()

    def init_window(self):
        self.setObjectName("mainWindow")
        title = "家庭食材管理与智能食谱助手"
        u = self.current_user
        self.setWindowTitle(
            f"{title}　·　{u.get('username','guest')}（{u.get('role','user')}）"
        )
        self.setMinimumSize(1080, 720)
        self.resize(1120, 760)
        self.tabBar().setDocumentMode(True)
        self.tabBar().setDrawBase(False)

        # 右上角：当前用户徽章 + 修改密码 + 退出登录
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(8, 4, 12, 4)
        cl.setSpacing(8)
        user_chip = QLabel(f"👤 {u.get('username','guest')} · {u.get('role','user')}")
        user_chip.setObjectName("statusChip")
        btn_pwd = QPushButton("修改密码")
        btn_pwd.setObjectName("ghostBtn")
        btn_pwd.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pwd.clicked.connect(self.show_change_password_dialog)
        btn_logout = QPushButton("退出登录")
        btn_logout.setObjectName("ghostBtn")
        btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logout.clicked.connect(self._logout)
        cl.addWidget(user_chip)
        cl.addWidget(btn_pwd)
        cl.addWidget(btn_logout)
        self.setCornerWidget(corner, Qt.Corner.TopRightCorner)

    def _load_from_db(self) -> None:
        """启动时从数据库加载当前用户的食材和购物清单。"""
        if self._user_id <= 0:
            return
        try:
            from datetime import date as _date
            raw_ingredients = db_load_ingredients(self._user_id)
            self.ingredients = []
            for r in raw_ingredients:
                expiry_str = r.get("expiry_date_str", "")
                try:
                    expiry = _date.fromisoformat(expiry_str)
                except Exception:
                    expiry = _date.today()
                self.ingredients.append({
                    "ingredient_id": r["ingredient_id"],
                    "name": r["name"],
                    "amount": r["amount"],
                    "unit": r["unit"],
                    "expiry": expiry,
                    "category": r["category"],
                    "location": normalize_location(r["location"]),
                })
        except Exception as e:
            print(f"[WARN] 加载食材失败：{e}")

        try:
            raw_shopping = db_load_shopping(self._user_id)
            self.shopping_items = []
            for r in raw_shopping:
                self.shopping_items.append({
                    "item_id": r["item_id"],
                    "name": r["name"],
                    "quantity": r["quantity"],
                    "unit": r["unit"],
                    "bought": r["bought"],
                })
        except Exception as e:
            print(f"[WARN] 加载购物清单失败：{e}")

    def _logout(self) -> None:
        self._log_op("退出登录")
        QApplication.quit()

    def _on_main_tab_changed(self, index: int):
        if index < 0 or index >= self.count():
            return
        widget = self.widget(index)
        if hasattr(self, "ingredient_tab") and widget is self.ingredient_tab:
            self._maybe_show_expiry_alert_once()
        elif widget is self.recipe_tab:
            if self.mode_box.currentText() == "用现有食材做":
                self._refresh_ingredient_picker()
        elif hasattr(self, "stats_tab") and widget is self.stats_tab:
            self.refresh_stats_view()
        elif hasattr(self, "dashboard_tab") and widget is self.dashboard_tab:
            self.refresh_dashboard_view()
        elif hasattr(self, "admin_tab") and widget is self.admin_tab:
            self.refresh_admin_view()

    def init_dashboard_tab(self) -> None:
        """首页总览：把库存、临期、购物和 AI 状态汇总成产品化入口。"""
        self.dashboard_tab = QWidget()
        root = QVBoxLayout(self.dashboard_tab)
        root.setContentsMargins(24, 18, 24, 24)
        root.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(18)

        hero_text = QVBoxLayout()
        hero_title = QLabel("家庭食材管理与智能食谱助手")
        hero_title.setObjectName("heroTitle")
        hero_subtitle = QLabel(
            "从冰箱库存到智能菜谱、购物清单、营养统计，形成完整的 Python + AI 家庭饮食管理闭环。"
        )
        hero_subtitle.setObjectName("heroSubtitle")
        hero_subtitle.setWordWrap(True)
        hero_text.addWidget(hero_title)
        hero_text.addWidget(hero_subtitle)
        hero_text.addStretch()

        hero_actions = QHBoxLayout()
        btn_to_recipe = QPushButton("生成今日菜谱")
        btn_to_recipe.setObjectName("primaryBtn")
        btn_to_recipe.clicked.connect(lambda: self.setCurrentWidget(self.recipe_tab))
        btn_to_inventory = QPushButton("管理库存")
        btn_to_inventory.setObjectName("secondaryBtn")
        btn_to_inventory.clicked.connect(lambda: self.setCurrentWidget(self.ingredient_tab))
        hero_actions.addWidget(btn_to_recipe)
        hero_actions.addWidget(btn_to_inventory)
        hero_actions.addStretch()
        hero_text.addLayout(hero_actions)

        self.dashboard_ai_chip = QLabel("AI 引擎 · 检测中")
        self.dashboard_ai_chip.setObjectName("heroChip")
        hero_layout.addLayout(hero_text, 1)
        hero_layout.addWidget(self.dashboard_ai_chip)
        root.addWidget(hero)

        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)
        self.dashboard_metric_cards: dict[str, QLabel] = {}
        metric_defs = [
            ("pantry", "库存食材", "0", "当前已入库的食材种类", "🥬"),
            ("expiring", "临期提醒", "0", "3 天内到期或已过期", "⏰"),
            ("shopping", "待购清单", "0", "尚未购买的购物项", "🛒"),
            ("recipe", "推荐菜谱", "0", "本地菜谱库可推荐数量", "🍳"),
        ]
        for idx, (key, title, value, desc, icon) in enumerate(metric_defs):
            card = self._create_dashboard_metric_card(key, title, value, desc, icon)
            metrics_grid.addWidget(card, idx // 4, idx % 4)
        root.addLayout(metrics_grid)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.dashboard_expiry_box = QTextEdit()
        self.dashboard_expiry_box.setObjectName("dashboardTextBox")
        self.dashboard_expiry_box.setReadOnly(True)
        self.dashboard_expiry_box.setMinimumHeight(180)
        self.dashboard_expiry_box.setPlaceholderText("暂无临期提醒")

        self.dashboard_flow_box = QTextEdit()
        self.dashboard_flow_box.setObjectName("dashboardTextBox")
        self.dashboard_flow_box.setReadOnly(True)
        self.dashboard_flow_box.setMinimumHeight(180)

        bottom.addWidget(self._wrap_dashboard_panel("临期食材提醒", self.dashboard_expiry_box), 1)
        bottom.addWidget(self._wrap_dashboard_panel("系统亮点流程", self.dashboard_flow_box), 1)
        root.addLayout(bottom, 1)

        self.addTab(self.dashboard_tab, "首页总览")
        self.refresh_dashboard_view()

    def _create_dashboard_metric_card(
        self, key: str, title: str, value: str, desc: str, icon: str
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        title_label = QLabel(f"{icon} {title}")
        title_label.setObjectName("metricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        desc_label = QLabel(desc)
        desc_label.setObjectName("metricDesc")
        desc_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(desc_label)
        self.dashboard_metric_cards[key] = value_label
        return card

    @staticmethod
    def _wrap_dashboard_panel(title: str, widget: QWidget) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        layout.addWidget(widget, 1)
        return panel

    def refresh_dashboard_view(self) -> None:
        if not hasattr(self, "dashboard_metric_cards"):
            return
        today = datetime.now().date()
        expiring = []
        for item in self.ingredients:
            normalized = normalize_pantry_item(dict(item))
            days_left = (normalized["expiry"] - today).days
            if days_left <= 3:
                expiring.append((days_left, normalized))
        expiring.sort(key=lambda x: x[0])
        pending_shop = sum(1 for it in self.shopping_items if not it.get("bought"))

        self.dashboard_metric_cards["pantry"].setText(str(len(self.ingredients)))
        self.dashboard_metric_cards["expiring"].setText(str(len(expiring)))
        self.dashboard_metric_cards["shopping"].setText(str(pending_shop))
        self.dashboard_metric_cards["recipe"].setText(str(len(self.recipes)))

        if expiring:
            lines = []
            for days_left, item in expiring[:8]:
                if days_left < 0:
                    status = f"已过期 {abs(days_left)} 天"
                elif days_left == 0:
                    status = "今天到期"
                else:
                    status = f"还剩 {days_left} 天"
                lines.append(
                    f"• {item['name']}（{format_amount_display(item['amount'], item['unit'])}）：{status}"
                )
            self.dashboard_expiry_box.setPlainText("\n".join(lines))
        else:
            self.dashboard_expiry_box.setPlainText(
                "当前没有 3 天内到期的食材。\n保持库存新鲜，推荐先用临期食材生成菜谱。"
            )

        self.dashboard_flow_box.setPlainText(
            "1. 食材入库：录入数量、保质期和存放位置。\n"
            "2. RAG 推荐：根据现有库存匹配本地菜谱库。\n"
            "3. AI 生成：本地 Qwen 生成可照做的菜谱详情。\n"
            "4. 购物联动：缺少食材一键加入购物清单。\n"
            "5. 做完扣减：按份数扣减库存并进入营养统计。"
        )

        if hasattr(self, "dashboard_ai_chip") and hasattr(self, "llm_status_label"):
            self.dashboard_ai_chip.setText(self.llm_status_label.text())

    def _maybe_show_expiry_alert_once(self):
        if self._expiry_alert_checked_this_session:
            return
        if not hasattr(self, "ingredient_tab") or self.currentWidget() is not self.ingredient_tab:
            return
        self._expiry_alert_checked_this_session = True
        self.check_expiry_alert()

    def _on_recipe_mode_changed(self, mode: str):
        use_pantry = mode == "用现有食材做"
        self.ingredient_pick_widget.setVisible(use_pantry)
        if use_pantry:
            self._refresh_ingredient_picker()

    def _refresh_ingredient_picker(self):
        if not hasattr(self, "ingredient_pick_list"):
            return
        self.ingredient_pick_list.clear()
        for raw in self.ingredients:
            item = normalize_pantry_item(dict(raw))
            label = f"{item['name']}（{format_amount_display(item.get('amount', 1), item.get('unit', '个'))}）"
            list_item = QListWidgetItem(label)
            list_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            list_item.setCheckState(Qt.CheckState.Checked)
            list_item.setData(Qt.ItemDataRole.UserRole, item["name"])
            self.ingredient_pick_list.addItem(list_item)

    def _get_checked_ingredient_names(self) -> list:
        if not hasattr(self, "ingredient_pick_list"):
            return [item["name"] for item in self.ingredients]
        names = []
        for i in range(self.ingredient_pick_list.count()):
            list_item = self.ingredient_pick_list.item(i)
            if list_item.checkState() == Qt.CheckState.Checked:
                name = list_item.data(Qt.ItemDataRole.UserRole)
                if name:
                    names.append(name)
        return names

    def _ingredient_names_for_recipe(self) -> list:
        if self.mode_box.currentText() == "用现有食材做":
            return self._get_checked_ingredient_names()
        return [item["name"] for item in self.ingredients]

    def init_ingredient_tab(self):
        self.ingredient_tab = QWidget()
        self.ingredient_table = QTableWidget()
        self.ingredient_table.setColumnCount(6)
        self.ingredient_table.setHorizontalHeaderLabels(
            ["食材名称", "数量/单位", "保质期", "食材分类", "存放位置", "操作"]
        )
        
        # 2. 表格高级打磨
        self.ingredient_table.setShowGrid(False)
        self.ingredient_table.setAlternatingRowColors(True)
        self.ingredient_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ingredient_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows) # 允许整行选中
        self.ingredient_table.verticalHeader().setDefaultSectionSize(40)
        self.ingredient_table.verticalHeader().setVisible(False) # 隐藏极其刺眼的左侧原生数字行号
        header = self.ingredient_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.ingredient_table.setColumnWidth(5, 156)

        self.btn_add_ingredient = QPushButton("添加食材")
        self.btn_add_ingredient.setObjectName("primaryBtn") # 赋予主操作绿色
        self.btn_add_ingredient.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_ingredient.clicked.connect(
            lambda _checked=False: self.show_add_ingredient_dialog()
        )

        self.btn_remove_ingredient = QPushButton("删除选中")
        self.btn_remove_ingredient.setObjectName("dangerBtn") # 赋予危险操作淡红
        self.btn_remove_ingredient.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_ingredient.clicked.connect(self.remove_selected_ingredient)

        self.btn_fridge_zones = QPushButton("🧊 分区视图")
        self.btn_fridge_zones.setObjectName("ghostBtn")
        self.btn_fridge_zones.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fridge_zones.setToolTip("按冷藏/冷冻/常温查看食材分布")
        self.btn_fridge_zones.clicked.connect(self.show_fridge_zones_dialog)

        self.btn_import_excel = QPushButton("📥 导入 Excel")
        self.btn_import_excel.setObjectName("ghostBtn")
        self.btn_import_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_excel.clicked.connect(self.import_ingredients_excel)

        self.btn_export_excel = QPushButton("📤 导出 Excel")
        self.btn_export_excel.setObjectName("ghostBtn")
        self.btn_export_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_excel.clicked.connect(self.export_ingredients_excel)

        title_label = QLabel("食材管理中心")
        title_label.setObjectName("pageTitle")
        subtitle = QLabel("管理冰箱库存，关注保质期提醒")
        subtitle.setObjectName("pageSubtitle")

        toolbar_card = QFrame()
        toolbar_card.setObjectName("toolbarCard")
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(14, 10, 14, 10)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(self.btn_add_ingredient)
        toolbar_layout.addWidget(self.btn_remove_ingredient)
        toolbar_layout.addWidget(self.btn_fridge_zones)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_import_excel)
        toolbar_layout.addWidget(self.btn_export_excel)

        table_card = QFrame()
        table_card.setObjectName("contentCard")
        table_card_layout = QVBoxLayout(table_card)
        table_card_layout.setContentsMargins(14, 12, 14, 12)
        table_card_layout.addWidget(self.ingredient_table)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(subtitle)
        layout.addWidget(toolbar_card)
        layout.addWidget(table_card, 1)
        self.ingredient_tab.setLayout(layout)
        self.addTab(self.ingredient_tab, "食材管理")

        self.refresh_ingredient_table(show_expiry_alert=False)

    def show_add_ingredient_dialog(self, edit_row=None):
        if not isinstance(edit_row, int):
            edit_row = None
        is_edit = edit_row is not None and 0 <= edit_row < len(self.ingredients)
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑食材" if is_edit else "添加食材入库")
        dialog.setMinimumWidth(400)

        name_edit = QLineEdit()
        name_row = QWidget()
        name_row_layout = QHBoxLayout(name_row)
        name_row_layout.setContentsMargins(0, 0, 0, 0)
        name_row_layout.setSpacing(6)
        btn_voice = QPushButton("🎤 语音")
        btn_voice.setObjectName("secondaryBtn")
        btn_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_voice.setToolTip("说出食材名称、数量和单位，自动填入表单")
        btn_voice.setFixedWidth(80)
        name_row_layout.addWidget(name_edit, 1)
        name_row_layout.addWidget(btn_voice)

        amount_edit = QLineEdit()
        amount_edit.setPlaceholderText("例如 2 或 1.5")
        unit_box = QComboBox()
        unit_box.addItems(INGREDIENT_UNITS)
        unit_box.setEditable(True)
        unit_box.setFixedWidth(96)
        amount_unit_row = QWidget()
        amount_unit_layout = QHBoxLayout(amount_unit_row)
        amount_unit_layout.setContentsMargins(0, 0, 0, 0)
        amount_unit_layout.setSpacing(8)
        amount_unit_layout.addWidget(amount_edit, 1)
        amount_unit_layout.addWidget(unit_box)

        btn_voice.clicked.connect(
            lambda: self._fill_form_from_voice(dialog, name_edit, amount_edit, unit_box)
        )
        expiry_edit = QDateEdit()
        expiry_edit.setDisplayFormat("yyyy-MM-dd")
        expiry_edit.setDate(QDate.currentDate())
        expiry_edit.setCalendarPopup(True) # 开启高级感的日历弹出视图
        
        category_box = QComboBox()
        category_box.addItems(["蔬菜", "肉类", "水果", "调料", "主食", "水产", "蛋奶"])
        location_box = QComboBox()
        location_box.addItems(LOCATION_OPTIONS)

        btn_confirm = QPushButton("保存修改" if is_edit else "确认添加")
        btn_confirm.setObjectName("primaryBtn")
        btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)

        if is_edit:
            item = normalize_pantry_item(dict(self.ingredients[edit_row]))
            name_edit.setText(item["name"])
            amount_edit.setText(
                str(int(item["amount"]))
                if item.get("amount") == int(item.get("amount", 1))
                else str(item.get("amount", 1))
            )
            idx = unit_box.findText(item.get("unit", "个"))
            if idx >= 0:
                unit_box.setCurrentIndex(idx)
            else:
                unit_box.setEditText(item.get("unit", "个"))
            expiry_edit.setDate(QDate(item["expiry"].year, item["expiry"].month, item["expiry"].day))
            cidx = category_box.findText(item.get("category", "蔬菜"))
            if cidx >= 0:
                category_box.setCurrentIndex(cidx)
            lidx = location_box.findText(display_location(item.get("location", "")))
            if lidx >= 0:
                location_box.setCurrentIndex(lidx)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.addRow("食材名称", name_row)
        form_layout.addRow("数量 / 单位", amount_unit_row)
        form_layout.addRow("保质期", expiry_edit)
        form_layout.addRow("食材分类", category_box)
        form_layout.addRow("存放位置", location_box)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_confirm)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(24, 22, 24, 20)
        main_layout.setSpacing(16)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)

        def add_item():
            name = name_edit.text().strip()
            unit = unit_box.currentText().strip() or "个"
            expiry = expiry_edit.date().toPyDate()
            category = category_box.currentText()
            location = normalize_location(location_box.currentText())
            if not name:
                QMessageBox.warning(dialog, "输入错误", "请填写食材名称。")
                return
            try:
                amount = parse_amount_text(amount_edit.text())
            except ValueError:
                QMessageBox.warning(dialog, "输入错误", "请填写有效的数量（大于 0 的数字）。")
                return
            expiry_str = expiry.strftime("%Y-%m-%d")
            entry = {
                "name": name,
                "amount": amount,
                "unit": unit,
                "expiry": expiry,
                "category": category,
                "location": location,
            }
            if is_edit:
                old_entry = self.ingredients[edit_row]
                entry["ingredient_id"] = old_entry.get("ingredient_id", -1)
                if self._user_id > 0 and entry["ingredient_id"] > 0:
                    db_update_ingredient(
                        entry["ingredient_id"], name, amount, unit, expiry_str, category, location
                    )
                self.ingredients[edit_row] = entry
                self._log_op("编辑食材", f"{name} {amount}{unit}")
            else:
                if self._user_id > 0:
                    new_id = db_add_ingredient(
                        self._user_id, name, amount, unit, expiry_str, category, location
                    )
                    entry["ingredient_id"] = new_id
                self.ingredients.append(entry)
                self._log_op("添加食材", f"{name} {amount}{unit}")
            self.refresh_ingredient_table(show_expiry_alert=False)
            self._refresh_ingredient_picker()
            self.refresh_stats_view()
            dialog.accept()

        btn_confirm.clicked.connect(add_item)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def refresh_ingredient_table(self, *, show_expiry_alert: bool = False):
        self.ingredients = [normalize_pantry_item(dict(x)) for x in self.ingredients]
        self.ingredient_table.setRowCount(len(self.ingredients))
        now = datetime.now().date()
        for row, item in enumerate(self.ingredients):
            expiry = item["expiry"]
            days_left = (expiry - now).days
            amount = item.get("amount", 1.0)
            unit = item.get("unit", "个")

            name_item = QTableWidgetItem(item["name"])
            amount_unit_item = QTableWidgetItem(format_amount_display(amount, unit))
            expiry_item = QTableWidgetItem(expiry.strftime("%Y-%m-%d"))
            category_item = QTableWidgetItem(item["category"])
            location_item = QTableWidgetItem(display_location(item.get("location", "")))

            for cell_item in [
                name_item, amount_unit_item, expiry_item, category_item, location_item
            ]:
                cell_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            op_container = QWidget()
            op_container.setStyleSheet("background: transparent;")
            op_layout = QHBoxLayout(op_container)
            op_layout.setContentsMargins(4, 4, 4, 4)
            op_layout.setSpacing(8)
            op_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit_btn = QPushButton("编辑")
            edit_btn.setObjectName("tableEditBtn")
            edit_btn.setFixedSize(58, 24)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.clicked.connect(
                lambda _checked, r=row: self.show_add_ingredient_dialog(edit_row=r)
            )
            delete_btn = QPushButton("删除")
            delete_btn.setObjectName("tableDeleteBtn")
            delete_btn.setFixedSize(58, 24)
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.clicked.connect(lambda _checked, r=row: self.delete_ingredient(r))
            op_layout.addWidget(edit_btn)
            op_layout.addWidget(delete_btn)

            if days_left < 0:
                bg_color = QColor("#ffe4e6")
                expiry_item.setToolTip("已过期")
            elif days_left <= 3:
                bg_color = QColor("#fef3c7")
                expiry_item.setToolTip(f"剩余 {days_left} 天")
            else:
                bg_color = None

            for col, widget_item in enumerate(
                [name_item, amount_unit_item, expiry_item, category_item, location_item]
            ):
                if bg_color is not None:
                    widget_item.setBackground(bg_color)
                self.ingredient_table.setItem(row, col, widget_item)

            self.ingredient_table.setCellWidget(row, 5, op_container)

        if show_expiry_alert:
            self.check_expiry_alert()
        self.refresh_dashboard_view()

    # (delete_ingredient, remove_selected_ingredient, check_expiry_alert 保持原样不变...)
    def delete_ingredient(self, row):
        if 0 <= row < len(self.ingredients):
            entry = self.ingredients[row]
            name = entry.get("name", "?")
            iid = entry.get("ingredient_id", -1)
            if self._user_id > 0 and iid and iid > 0:
                db_delete_ingredient(iid)
            del self.ingredients[row]
            self._log_op("删除食材", name)
            self.refresh_ingredient_table()
            self._refresh_ingredient_picker()
            self.refresh_stats_view()

    def remove_selected_ingredient(self):
        rows = sorted({idx.row() for idx in self.ingredient_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "删除食材", "请先选择要删除的行。")
            return
        for row in rows:
            if 0 <= row < len(self.ingredients):
                del self.ingredients[row]
        self.refresh_ingredient_table()
        self._refresh_ingredient_picker()
        self.refresh_stats_view()

    def check_expiry_alert(self):
        now = datetime.now().date()
        expired = []
        soon = []
        for item in self.ingredients:
            days_left = (item["expiry"] - now).days
            if days_left < 0:
                expired.append(f"{item['name']} ({item['expiry']})")
            elif days_left <= 3:
                soon.append(f"{item['name']} 剩余 {days_left} 天")
        if expired or soon:
            message_parts = []
            if expired:
                message_parts.append("已过期食材：\n" + "\n".join(expired))
            if soon:
                message_parts.append("即将过期食材：\n" + "\n".join(soon))
            QMessageBox.warning(
                self, "保质期提醒", "\n\n".join(message_parts)
            )

    # ====================== 创新点：冰箱分区可视化 ======================
    def show_fridge_zones_dialog(self) -> None:
        """按 location 字段把食材分为 冷冻/冷藏/常温/未添加 四区展示。"""
        zones: dict[str, list[dict]] = {
            "🧊 冷藏区": [],
            "❄️ 冷冻区": [],
            "🌡️ 常温区": [],
            "❓ 未添加位置": [],
        }
        for item in self.ingredients:
            loc = normalize_location(item.get("location", ""))
            if loc == "冷冻区":
                zones["❄️ 冷冻区"].append(item)
            elif loc == "冷藏区":
                zones["🧊 冷藏区"].append(item)
            elif loc == "常温区":
                zones["🌡️ 常温区"].append(item)
            else:
                zones["❓ 未添加位置"].append(item)

        dlg = QDialog(self)
        dlg.setWindowTitle("冰箱分区视图")
        dlg.setMinimumSize(720, 480)
        layout = QHBoxLayout(dlg)
        layout.setSpacing(10)
        for zone_name, items in zones.items():
            card = QFrame()
            card.setObjectName("contentCard")
            vbox = QVBoxLayout(card)
            vbox.setContentsMargins(12, 10, 12, 10)
            title = QLabel(f"{zone_name}  ({len(items)})")
            title.setObjectName("sectionLabel")
            vbox.addWidget(title)
            listw = QListWidget()
            listw.setAlternatingRowColors(True)
            now = datetime.now().date()
            for it in items:
                days_left = (it["expiry"] - now).days
                tag = "⚠️" if days_left < 0 else ("🟡" if days_left <= 3 else "🟢")
                listw.addItem(
                    f"{tag} {it['name']}  "
                    f"{format_amount_display(it.get('amount', 1), it.get('unit', '个'))}  "
                    f"剩{days_left}天"
                )
            if not items:
                listw.addItem("（空）")
            vbox.addWidget(listw, 1)
            layout.addWidget(card, 1)
        dlg.exec()

    # ====================== 创新点：Excel 导入/导出 ======================
    def export_ingredients_excel(self) -> None:
        """用 pandas 把冰箱食材导出为 Excel/CSV，便于备份与分享。"""
        if not self.ingredients:
            QMessageBox.information(self, "导出 Excel", "当前没有食材数据。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出食材数据", "冰箱食材.xlsx", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            import pandas as pd
            rows = []
            for it in self.ingredients:
                rows.append({
                    "食材名称": it.get("name", ""),
                    "数量": it.get("amount", 1),
                    "单位": it.get("unit", "个"),
                    "保质期": it["expiry"].strftime("%Y-%m-%d"),
                    "分类": it.get("category", ""),
                    "存放位置": display_location(it.get("location", "")),
                })
            df = pd.DataFrame(rows)
            if path.lower().endswith(".csv"):
                df.to_csv(path, index=False, encoding="utf-8-sig")
            else:
                try:
                    df.to_excel(path, index=False)
                except ImportError:
                    # 没装 openpyxl 时降级为 CSV
                    path = path.rsplit(".", 1)[0] + ".csv"
                    df.to_csv(path, index=False, encoding="utf-8-sig")
            self._log_op("导出食材", f"{len(rows)} 条 -> {path}")
            QMessageBox.information(self, "导出成功", f"已导出 {len(rows)} 条食材到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def import_ingredients_excel(self) -> None:
        """从 Excel/CSV 批量导入食材；列名兼容中英文。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择食材 Excel/CSV", "", "数据文件 (*.xlsx *.xls *.csv)"
        )
        if not path:
            return
        try:
            import pandas as pd
            from datetime import date as _date
            if path.lower().endswith(".csv"):
                df = pd.read_csv(path)
            else:
                df = pd.read_excel(path)
            # 列名兼容映射
            col_map = {}
            for c in df.columns:
                key = str(c).strip().lower()
                if key in ("食材名称", "名称", "name"): col_map[c] = "name"
                elif key in ("数量", "amount", "quantity"): col_map[c] = "amount"
                elif key in ("单位", "unit"): col_map[c] = "unit"
                elif key in ("保质期", "expiry", "expiry_date"): col_map[c] = "expiry"
                elif key in ("分类", "category"): col_map[c] = "category"
                elif key in ("存放位置", "位置", "location"): col_map[c] = "location"
            df = df.rename(columns=col_map)
            if "name" not in df.columns:
                QMessageBox.warning(self, "导入失败", "未找到「食材名称」列")
                return
            # pandas 清洗：去重 + 去空
            df = df.dropna(subset=["name"]).drop_duplicates(subset=["name"])
            added = 0
            for _, r in df.iterrows():
                name = str(r["name"]).strip()
                if not name:
                    continue
                try:
                    amount = float(r.get("amount", 1) or 1)
                except Exception:
                    amount = 1.0
                unit = str(r.get("unit", "个") or "个").strip()
                category = str(r.get("category", "蔬菜") or "蔬菜").strip()
                location = normalize_location(str(r.get("location", "") or "").strip())
                expiry_str = str(r.get("expiry", "") or "").strip()
                try:
                    expiry = _date.fromisoformat(expiry_str[:10])
                except Exception:
                    expiry = _date.today()
                entry = {
                    "name": name, "amount": amount, "unit": unit,
                    "expiry": expiry, "category": category, "location": location,
                }
                if self._user_id > 0:
                    new_id = db_add_ingredient(
                        self._user_id, name, amount, unit,
                        expiry.strftime("%Y-%m-%d"), category, location,
                    )
                    entry["ingredient_id"] = new_id
                self.ingredients.append(entry)
                added += 1
            self.refresh_ingredient_table(show_expiry_alert=False)
            self.refresh_stats_view()
            self._log_op("导入食材", f"{added} 条 <- {path}")
            QMessageBox.information(self, "导入成功", f"已导入 {added} 条食材。")
        except ImportError as e:
            QMessageBox.warning(
                self, "缺少依赖",
                f"读取 Excel 需要 openpyxl：pip install openpyxl\n{e}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    # ====================== 创新点：菜谱步骤语音朗读 ======================
    def toggle_speak_recipe(self) -> None:
        """切换朗读状态：第一次点击开始朗读当前菜谱步骤，再次点击停止。"""
        if self._tts_thread and self._tts_thread.is_alive():
            self._stop_tts()
            self.btn_speak_recipe.setChecked(False)
            self.btn_speak_recipe.setText("🔊 朗读步骤")
            return

        recipe = self._get_selected_recipe()
        if not recipe:
            QMessageBox.information(self, "朗读步骤", "请先在左侧选择一道菜谱。")
            self.btn_speak_recipe.setChecked(False)
            return
        text = self.recipe_detail.toPlainText().strip()
        if text:
            # 优先朗读用户当前看到的详情内容，确保 AI 生成后读的是 AI 菜谱。
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text.replace("AI 生成菜谱", "").strip()
            speak_text = f"开始朗读 {recipe.get('name', '当前菜谱')}。{text}"
        else:
            steps = recipe.get("steps") or []
            if not steps:
                QMessageBox.information(self, "朗读步骤", "当前菜谱没有可朗读的步骤内容。")
                self.btn_speak_recipe.setChecked(False)
                return
            speak_text = f"开始烹饪 {recipe.get('name', '菜谱')}。"
            for idx, s in enumerate(steps, 1):
                speak_text += f"第 {idx} 步，{s}。"
            speak_text += "烹饪步骤已读完。"

        try:
            import pyttsx3
        except ImportError:
            QMessageBox.warning(
                self, "缺少依赖",
                "朗读功能需要 pyttsx3：\npip install pyttsx3"
            )
            self.btn_speak_recipe.setChecked(False)
            return

        import threading
        self.btn_speak_recipe.setText("⏹ 停止朗读")
        self.btn_speak_recipe.setChecked(True)

        def run_tts():
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", 180)
                self._tts_engine = engine
                engine.say(speak_text)
                engine.runAndWait()
            except Exception as e:
                print(f"[TTS] 朗读失败：{e}")
            finally:
                self._tts_engine = None
                # 朗读完成后恢复按钮（跨线程通过单触发计时）
                try:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: (
                        self.btn_speak_recipe.setChecked(False),
                        self.btn_speak_recipe.setText("🔊 朗读步骤"),
                    ))
                except Exception:
                    pass

        self._tts_thread = threading.Thread(target=run_tts, daemon=True)
        self._tts_thread.start()
        self._log_op("朗读菜谱", recipe.get("name", ""))

    def _stop_tts(self) -> None:
        """尽力中断 pyttsx3 朗读（部分平台不支持立即打断）。"""
        engine = self._tts_engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

    def _get_selected_recipe(self):
        current = self.recipe_list.currentItem()
        if not current:
            return None
        recipe = current.data(Qt.ItemDataRole.UserRole)
        if not recipe or not isinstance(recipe, dict) or not recipe.get("name"):
            return None
        return recipe

    def _update_mark_cooked_button_state(self):
        if not hasattr(self, "btn_mark_cooked"):
            return
        recipe = self._get_selected_recipe()
        self.btn_mark_cooked.setEnabled(recipe is not None)

    def _get_recipe_for_cooking(self):
        recipe = self._active_recipe_for_cooking or self._get_selected_recipe()
        return recipe

    def start_mark_cooked_flow(self):
        recipe = self._get_recipe_for_cooking()
        if not recipe:
            QMessageBox.information(self, "提示", "请先在左侧选择一道菜谱。")
            return
        if not self.ingredients:
            QMessageBox.information(self, "提示", "食材库存为空，无需扣减。")
            return

        servings = self._ask_servings()
        if servings is None:
            return

        names = recipe_ingredients_from_dict(recipe)
        if not names:
            QMessageBox.information(self, "提示", "当前菜谱没有可用的食材列表。")
            return

        plan = plan_deductions(names, self.ingredients, servings)
        confirmed = self._show_deduction_confirm_dialog(plan, servings)
        if not confirmed:
            return

        self.ingredients, summary = apply_deductions(self.ingredients, confirmed)
        self.refresh_ingredient_table()
        self._refresh_ingredient_picker()
        self.refresh_stats_view()
        QMessageBox.information(
            self,
            "库存已更新",
            f"已扣减 {summary.deducted_count} 种食材，"
            f"用尽并删除 {summary.removed_count} 种；"
            f"跳过 {summary.skipped_count} 种（冰箱无货或未匹配）。",
        )

    def _ask_servings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("选择几人份")
        dialog.setMinimumWidth(320)
        label = QLabel("本道菜按几人份扣减库存？")
        servings_box = QComboBox()
        for n in SERVING_OPTIONS:
            servings_box.addItem(f"{n} 人份", n)
        servings_box.setCurrentIndex(0)
        btn_ok = QPushButton("下一步")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(label)
        layout.addWidget(servings_box)
        layout.addStretch()
        layout.addLayout(btn_row)
        result = {"value": None}

        def on_ok():
            result["value"] = float(servings_box.currentData())
            dialog.accept()

        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return result["value"]

    def _show_deduction_confirm_dialog(self, plan, servings):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"确认扣减库存（{int(servings) if servings == int(servings) else servings} 人份）")
        dialog.resize(620, 400)
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ["菜谱食材", "冰箱匹配", "扣减数量", "单位", "扣减后剩余"]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)

        spinboxes = []
        table.setRowCount(len(plan))
        for row, item in enumerate(plan):
            table.setItem(row, 0, QTableWidgetItem(item.recipe_ingredient))
            if item.matched:
                match_text = f"{item.pantry_name}（现有 {format_amount_display(item.current_amount, item.unit)}）"
                spin = QDoubleSpinBox()
                spin.setRange(0, max(item.current_amount, item.deduct_amount))
                spin.setDecimals(2)
                spin.setValue(item.deduct_amount)
                spin.setSingleStep(0.5)
                spinboxes.append((row, item, spin))
                table.setCellWidget(row, 2, spin)
                table.setItem(row, 1, QTableWidgetItem(match_text))
                table.setItem(row, 3, QTableWidgetItem(item.unit))
                rem_item = QTableWidgetItem(
                    format_amount_display(item.remaining_after, item.unit)
                )
                spin.valueChanged.connect(
                    lambda v, s=spin, it=item, ri=rem_item: ri.setText(
                        format_amount_display(max(0.0, it.current_amount - v), it.unit)
                    )
                )
                table.setItem(row, 4, rem_item)
            else:
                spinboxes.append((row, item, None))
                skip = QTableWidgetItem(item.skip_reason or "跳过")
                skip.setForeground(QColor("#94a3b8"))
                table.setItem(row, 1, skip)
                for col in range(2, 5):
                    table.setItem(row, col, QTableWidgetItem("—"))

        btn_ok = QPushButton("确认扣减")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(QLabel("可调整每种食材的扣减数量，0 表示不扣减："))
        layout.addWidget(table, 1)
        layout.addLayout(btn_row)
        confirmed = {"plan": None}

        def on_ok():
            out = []
            for _row, item, spin in spinboxes:
                if spin is None:
                    out.append(item)
                    continue
                copy = DeductionRow(
                    recipe_ingredient=item.recipe_ingredient,
                    pantry_index=item.pantry_index,
                    pantry_name=item.pantry_name,
                    deduct_amount=spin.value(),
                    unit=item.unit,
                    current_amount=item.current_amount,
                    remaining_after=max(0.0, item.current_amount - spin.value()),
                    matched=True,
                )
                out.append(copy)
            confirmed["plan"] = out
            dialog.accept()

        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return confirmed["plan"]

    def init_recipe_tab(self):
        self.recipe_tab = QWidget()

        # —— 控件 —— #
        self.mode_box = QComboBox()
        self.mode_box.addItems(["用现有食材做", "按需求做"])
        self.mode_box.currentTextChanged.connect(self._on_recipe_mode_changed)

        self.diet_box = QComboBox()
        self.diet_box.addItems(["家常菜", "减脂餐", "增肌餐", "素食", "控糖"])
        self.time_box = QComboBox()
        self.time_box.addItems(["15分钟内", "15-30分钟", "30分钟以上"])
        self.diff_box = QComboBox()
        self.diff_box.addItems(["简单", "中等", "困难"])

        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText("排除的食材，用逗号分隔，如：香菜,葱")

        self.ingredient_pick_widget = QWidget()
        pick_layout = QVBoxLayout(self.ingredient_pick_widget)
        pick_layout.setContentsMargins(0, 0, 0, 0)
        pick_layout.setSpacing(6)
        pick_label = QLabel("勾选要用于推荐的食材")
        pick_label.setObjectName("sectionLabel")
        self.ingredient_pick_list = QListWidget()
        self.ingredient_pick_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.ingredient_pick_list.setMinimumHeight(120)
        self.ingredient_pick_list.setMaximumHeight(170)
        pick_layout.addWidget(pick_label)
        pick_layout.addWidget(self.ingredient_pick_list)

        # —— 按钮 —— #
        self.btn_generate_recipe = QPushButton("生成智能食谱")
        self.btn_generate_recipe.setObjectName("primaryBtn")
        self.btn_generate_recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate_recipe.setToolTip("RAG 检索匹配菜谱，并自动调用 AI 生成完整菜谱")
        self.btn_generate_recipe.clicked.connect(self.generate_recipe_list)

        self.btn_ai_recipe = QPushButton("AI 重新生成")
        self.btn_ai_recipe.setObjectName("secondaryBtn")
        self.btn_ai_recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_recipe.setToolTip("针对左侧选中菜谱，再次调用 AI 生成")
        self.btn_ai_recipe.clicked.connect(self.start_ai_recipe_generation)

        self.btn_mark_cooked = QPushButton("我已做完")
        self.btn_mark_cooked.setObjectName("ghostBtn")
        self.btn_mark_cooked.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mark_cooked.setEnabled(False)
        self.btn_mark_cooked.clicked.connect(self.start_mark_cooked_flow)

        self.btn_buy_missing = QPushButton("购买缺料")
        self.btn_buy_missing.setObjectName("ghostBtn")
        self.btn_buy_missing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buy_missing.clicked.connect(self.add_missing_to_shopping_list)

        self.btn_add_recipe_shop = QPushButton("整单加入购物清单")
        self.btn_add_recipe_shop.setObjectName("ghostBtn")
        self.btn_add_recipe_shop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_recipe_shop.clicked.connect(self.add_recipe_ingredients_to_shopping_list)

        # 创新点：步骤朗读
        self.btn_speak_recipe = QPushButton("🔊 朗读步骤")
        self.btn_speak_recipe.setObjectName("ghostBtn")
        self.btn_speak_recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_speak_recipe.setToolTip("做菜不方便看屏幕？让 AI 朗读步骤（离线 TTS）")
        self.btn_speak_recipe.setCheckable(True)
        self.btn_speak_recipe.clicked.connect(self.toggle_speak_recipe)
        self._tts_engine = None
        self._tts_thread = None

        # —— 筛选卡（左栏） —— #
        filter_form = QFormLayout()
        filter_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        filter_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        filter_form.setHorizontalSpacing(12)
        filter_form.setVerticalSpacing(10)
        filter_form.addRow("生成模式", self.mode_box)
        filter_form.addRow("饮食偏好", self.diet_box)
        filter_form.addRow("烹饪时间", self.time_box)
        filter_form.addRow("难度级别", self.diff_box)
        filter_form.addRow("排除食材", self.exclude_edit)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self.btn_generate_recipe)
        action_row.addWidget(self.btn_ai_recipe)
        action_row.addStretch()

        self.llm_status_label = QLabel("")
        self.llm_status_label.setObjectName("statusChipMuted")
        self.llm_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        filter_card = QFrame()
        filter_card.setObjectName("contentCard")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(18, 16, 18, 16)
        filter_layout.setSpacing(12)
        filter_title = QLabel("个性化筛选")
        filter_title.setObjectName("sectionLabel")
        engine_row = QHBoxLayout()
        engine_row.setSpacing(8)
        engine_row.addWidget(filter_title)
        engine_row.addStretch()
        engine_row.addWidget(self.llm_status_label)
        filter_layout.addLayout(engine_row)
        filter_layout.addLayout(filter_form)
        filter_layout.addWidget(self.ingredient_pick_widget)
        filter_layout.addLayout(action_row)

        # —— 详情卡（右栏） —— #
        self.recipe_list = QListWidget()
        self.recipe_list.itemClicked.connect(self.show_recipe_detail)
        self.recipe_list.currentItemChanged.connect(
            lambda _cur, _prev: self._update_mark_cooked_button_state()
        )
        self.recipe_list.setMinimumWidth(220)

        self.recipe_detail = QTextEdit()
        self.recipe_detail.setReadOnly(True)
        self.recipe_detail.setPlaceholderText(
            "在左侧选择菜谱后，这里会显示完整食材、做法步骤与营养估算。"
        )

        list_box = QFrame()
        list_box.setObjectName("contentCard")
        list_box_layout = QVBoxLayout(list_box)
        list_box_layout.setContentsMargins(14, 12, 14, 14)
        list_box_layout.setSpacing(8)
        list_title = QLabel("推荐菜谱")
        list_title.setObjectName("sectionLabel")
        list_box_layout.addWidget(list_title)
        list_box_layout.addWidget(self.recipe_list, 1)

        detail_box = QFrame()
        detail_box.setObjectName("contentCard")
        detail_box_layout = QVBoxLayout(detail_box)
        detail_box_layout.setContentsMargins(14, 12, 14, 14)
        detail_box_layout.setSpacing(8)
        detail_title_row = QHBoxLayout()
        detail_title = QLabel("菜谱详情")
        detail_title.setObjectName("sectionLabel")
        detail_title_row.addWidget(detail_title)
        detail_title_row.addStretch()
        detail_title_row.addWidget(self.btn_speak_recipe)
        detail_title_row.addWidget(self.btn_buy_missing)
        detail_title_row.addWidget(self.btn_add_recipe_shop)
        detail_title_row.addWidget(self.btn_mark_cooked)
        detail_box_layout.addLayout(detail_title_row)
        detail_box_layout.addWidget(self.recipe_detail, 1)

        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.addWidget(list_box)
        right_splitter.addWidget(detail_box)
        right_splitter.setSizes([260, 620])
        right_splitter.setChildrenCollapsible(False)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(filter_card)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([320, 760])
        main_splitter.setChildrenCollapsible(False)

        # —— 页眉 + 主体 —— #
        header_label = QLabel("智能食谱助手")
        header_label.setObjectName("pageTitle")
        recipe_subtitle = QLabel("基于冰箱库存或口味偏好，RAG 检索 + AI 生成完整菜谱")
        recipe_subtitle.setObjectName("pageSubtitle")

        layout = QVBoxLayout(self.recipe_tab)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(10)
        layout.addWidget(header_label)
        layout.addWidget(recipe_subtitle)
        layout.addWidget(main_splitter, 1)

        self.addTab(self.recipe_tab, "智能食谱")
        self.recipe_list.clear()
        self._on_recipe_mode_changed(self.mode_box.currentText())

    def generate_recipe_list(self):
        mode = self.mode_box.currentText()
        diet = self.diet_box.currentText()
        time = self.time_box.currentText()
        diff = self.diff_box.currentText()
        self._log_op("生成菜谱", f"mode={mode} diet={diet} time={time} diff={diff}")
        ingredient_names = self._ingredient_names_for_recipe()
        exclude_set = self._parse_exclude_ingredients()
        ingredient_names = [n for n in ingredient_names if n not in exclude_set]
        results = []

        try:
            from services.recipe_service import get_recipe_service

            svc = get_recipe_service()
            if mode == "用现有食材做":
                if not self.ingredients:
                    QMessageBox.information(
                        self, "提示", "请先在「食材管理」中添加冰箱食材。"
                    )
                elif not ingredient_names:
                    QMessageBox.information(
                        self, "提示", "请至少勾选一种要用于推荐的食材。"
                    )
                else:
                    results = svc.search_by_ingredients(
                        ingredient_names, top_k=10, min_score=0.12
                    )
            else:
                results = svc.search_by_preferences(
                    diet=diet, cooking_time=time, difficulty=diff, top_k=10
                )
        except Exception:
            ingredient_set = set(ingredient_names)
            if mode == "用现有食材做":
                # 服务异常时退化到本地规则匹配：至少命中一个食材，按命中比例排序
                ranked = []
                for recipe in self.recipes:
                    recipe_set = set(recipe["ingredients"])
                    if not recipe_set:
                        continue
                    overlap = len(recipe_set & ingredient_set)
                    if overlap <= 0:
                        continue
                    score = overlap / len(recipe_set)
                    item = dict(recipe)
                    item["match_score"] = score
                    ranked.append(item)
                ranked.sort(key=lambda r: r.get("match_score", 0), reverse=True)
                results = ranked[:10]
            else:
                results = [
                    r
                    for r in self.recipes
                    if diet in r["tags"] and r["time"] == time and r["diff"] == diff
                ]

        if exclude_set:
            results = [
                r
                for r in results
                if not exclude_set.intersection(set(r.get("ingredients") or []))
            ]

        self.recipe_list.clear()
        if results:
            for recipe in results:
                label = recipe["name"]
                if recipe.get("match_score") is not None:
                    label = f"{label}  ({recipe['match_score']:.0%})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, recipe)
                self.recipe_list.addItem(item)
            self.recipe_list.setCurrentRow(0)
            self._active_recipe_for_cooking = results[0]
            self._update_mark_cooked_button_state()
            # 先显示本地 RAG 菜谱详情，避免每次推荐都等待本地 LLM 冷启动。
            self.show_recipe_detail(self.recipe_list.item(0))
        else:
            self.recipe_list.addItem("⚠️ 未找到匹配食谱，请调整食材或筛选条件")
            self.recipe_detail.clear()
            self._active_recipe_for_cooking = None
            self._update_mark_cooked_button_state()

    def start_ai_recipe_generation(self, auto: bool = False):
        """
        触发 AI 生成菜谱（方案 C：RAG 匹配的菜作为参考 → LLM 生成完整菜谱）。
        auto=True 表示由 generate_recipe_list 自动触发，跳过额外提示。
        """
        if not auto:
            if not self.ingredients:
                QMessageBox.information(self, "提示", "请先在「食材管理」中添加食材。")
                return
            ingredient_names = self._ingredient_names_for_recipe()
            if self.mode_box.currentText() == "用现有食材做" and not ingredient_names:
                QMessageBox.information(self, "提示", "请至少勾选一种要用于生成菜谱的食材。")
                return
        else:
            ingredient_names = self._ingredient_names_for_recipe()

        current = self.recipe_list.currentItem()
        recipe = current.data(Qt.ItemDataRole.UserRole) if current else None
        if recipe and isinstance(recipe, dict):
            self._active_recipe_for_cooking = recipe
        recipe_name = (recipe or {}).get("name", "")
        diet = self.diet_box.currentText()
        time = self.time_box.currentText()
        diff = self.diff_box.currentText()

        from services.recipe_service import get_recipe_service

        svc = get_recipe_service()

        cached = svc.get_cached_recipe_text(
            ingredient_names,
            recipe_name=recipe_name,
            diet=diet,
            cooking_time=time,
            difficulty=diff,
        )
        if cached:
            self._on_ai_recipe_ready(cached)
            return

        self.btn_ai_recipe.setEnabled(False)
        if hasattr(self, "btn_generate_recipe"):
            self.btn_generate_recipe.setEnabled(False)
        hint = "⏳ AI 正在生成详细菜谱，请稍候…"
        if recipe_name:
            hint = f"⏳ AI 正在为「{recipe_name}」生成完整菜谱，请稍候…"
        self.recipe_detail.setPlainText(hint)

        def task():
            return svc.generate_recipe_text(
                ingredient_names,
                recipe_name=recipe_name,
                diet=diet,
                cooking_time=time,
                difficulty=diff,
            )

        def _reenable_buttons():
            self.btn_ai_recipe.setEnabled(True)
            if hasattr(self, "btn_generate_recipe"):
                self.btn_generate_recipe.setEnabled(True)

        worker = Worker(task)
        worker.signals.result.connect(self._on_ai_recipe_ready)
        worker.signals.error.connect(self._on_ai_recipe_error)
        worker.signals.finished.connect(_reenable_buttons)
        self.thread_pool.start(worker)

    def _on_ai_recipe_ready(self, text):
        if not self._active_recipe_for_cooking:
            self._active_recipe_for_cooking = self._get_selected_recipe()
        nutrition = self._extract_nutrition_from_ai_text(text)
        display_text = (
            self._strip_nutrition_section_from_ai_text(text)
            if nutrition
            else text
        )
        nutrition_html = self._build_ai_nutrition_html(nutrition)
        body_html = self._markdown_to_html(display_text)
        html = (
            "<h2 style='color:#0d9488; margin:0 0 8px 0;'>AI 生成菜谱</h2>"
            f"<div style='font-family:Microsoft YaHei, sans-serif;"
            f" line-height:1.8; color:#333; font-size:14px;'>{body_html}</div>"
            f"{nutrition_html}"
        )
        self.recipe_detail.setHtml(html)
        self._update_mark_cooked_button_state()

    def _on_ai_recipe_error(self, message):
        import sys

        extra = ""
        if "access violation" in message.lower():
            extra = (
                "\n\n提示：本地模型在后台线程调用时可能崩溃，已尝试子进程隔离。"
                "若仍失败，请完全退出后重新启动应用，或配置 DEEPSEEK_API_KEY 使用云端生成。"
            )
        elif "llama" in message.lower() or "LocalLLM" in message:
            from llm.deps import format_llm_setup_hint

            extra = f"\n\n{format_llm_setup_hint()}"

        self.recipe_detail.setPlainText(
            f"生成失败：{message}{extra}\n\n"
            "也可配置云端：设置环境变量 DEEPSEEK_API_KEY 后重启。\n"
            f"当前 Python：{sys.executable}"
        )

    @staticmethod
    def _escape_html(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @classmethod
    def _markdown_to_html(cls, text: str) -> str:
        """将 AI 输出的简易 Markdown 转换为美观的 HTML（标题/列表/加粗）。"""
        import re

        if not text:
            return ""

        lines = text.replace("\r\n", "\n").split("\n")
        html_parts: list[str] = []
        in_ul = False
        in_ol = False

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False

        def inline(s: str) -> str:
            s = cls._escape_html(s)
            s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
            s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
            return s

        heading_styles = {
            1: "color:#0d9488; font-size:20px; margin:14px 0 8px 0;",
            2: "color:#0d9488; font-size:18px; margin:12px 0 6px 0;",
            3: "color:#0f766e; font-size:16px; margin:10px 0 6px 0;"
                " border-left:4px solid #0d9488; padding-left:8px;",
            4: "color:#115e59; font-size:15px; margin:8px 0 4px 0; font-weight:bold;",
            5: "color:#115e59; font-size:14px; margin:6px 0 4px 0; font-weight:bold;",
            6: "color:#115e59; font-size:14px; margin:6px 0 4px 0; font-weight:bold;",
        }

        for raw in lines:
            line = raw.rstrip()
            if not line.strip():
                close_lists()
                html_parts.append("<div style='height:6px;'></div>")
                continue

            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                close_lists()
                level = len(m.group(1))
                style = heading_styles.get(level, heading_styles[4])
                html_parts.append(
                    f"<div style='{style}'>{inline(m.group(2).strip())}</div>"
                )
                continue

            m = re.match(r"^\s*[-*•]\s+(.+)$", line)
            if m:
                if in_ol:
                    html_parts.append("</ol>")
                    in_ol = False
                if not in_ul:
                    html_parts.append(
                        "<ul style='margin:4px 0 4px 20px; padding-left:16px;'>"
                    )
                    in_ul = True
                html_parts.append(
                    f"<li style='margin:3px 0;'>{inline(m.group(1).strip())}</li>"
                )
                continue

            m = re.match(r"^\s*\d+[\.、)]\s*(.+)$", line)
            if m:
                if in_ul:
                    html_parts.append("</ul>")
                    in_ul = False
                if not in_ol:
                    html_parts.append(
                        "<ol style='margin:4px 0 4px 20px; padding-left:16px;'>"
                    )
                    in_ol = True
                html_parts.append(
                    f"<li style='margin:3px 0;'>{inline(m.group(1).strip())}</li>"
                )
                continue

            close_lists()
            html_parts.append(
                f"<p style='margin:4px 0;'>{inline(line.strip())}</p>"
            )

        close_lists()
        return "".join(html_parts)

    @staticmethod
    def _extract_nutrition_from_ai_text(text: str) -> dict:
        """从 AI 生成的 Markdown/普通文本中提取营养数值。"""
        if not text:
            return {}

        normalized = text.replace("：", ":")
        patterns = {
            "calories": (
                "热量",
                ["热量", "卡路里", "能量"],
                "kcal",
            ),
            "protein": (
                "蛋白质",
                ["蛋白质", "蛋白"],
                "g",
            ),
            "carbs": (
                "碳水",
                ["碳水化合物", "碳水"],
                "g",
            ),
            "fat": (
                "脂肪",
                ["脂肪"],
                "g",
            ),
        }

        result = {}
        for key, (label, aliases, default_unit) in patterns.items():
            alias_pattern = "|".join(re.escape(alias) for alias in aliases)
            match = re.search(
                rf"(?:{alias_pattern})[^\d\n\r]{{0,24}}(\d+(?:\.\d+)?)\s*(kcal|千卡|大卡|克|g|G)?",
                normalized,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            value = float(match.group(1))
            unit = match.group(2) or default_unit
            if unit in {"千卡", "大卡"}:
                unit = "kcal"
            elif unit == "克":
                unit = "g"
            else:
                unit = unit.lower()
            result[key] = {"label": label, "value": value, "unit": unit}
        return result

    @staticmethod
    def _strip_nutrition_section_from_ai_text(text: str) -> str:
        """删除 AI 原文末尾的营养成分段，避免和图形化展示重复。"""
        if not text:
            return ""

        heading = re.search(
            r"(?im)^\s{0,3}#{0,6}\s*营养成分[^\n]*\n?",
            text,
        )
        if not heading:
            return text.strip()

        tail = text[heading.end():]
        next_heading = re.search(r"(?m)^\s{0,3}#{1,6}\s+\S+", tail)
        end = heading.end() + next_heading.start() if next_heading else len(text)
        cleaned = (text[: heading.start()] + text[end:]).strip()
        return cleaned or text.strip()

    def _build_ai_nutrition_html(self, nutrition: dict) -> str:
        if not nutrition:
            return ""

        macro_items = [
            ("protein", "#0d9488"),
            ("carbs", "#f59e0b"),
            ("fat", "#ef4444"),
        ]
        max_macro = max(
            [nutrition[k]["value"] for k, _color in macro_items if k in nutrition]
            or [1]
        )

        cards = []
        if "calories" in nutrition:
            item = nutrition["calories"]
            cards.append(
                "<td style='padding:8px;'>"
                "<div style='border-radius:12px; background:#ecfeff; padding:12px; border:1px solid #99f6e4;'>"
                "<div style='font-size:13px; color:#0f766e; font-weight:700;'>总热量</div>"
                f"<div style='font-size:22px; color:#0f172a; font-weight:800;'>{item['value']:g} {item['unit']}</div>"
                "</div></td>"
            )
        for key, color in macro_items:
            if key not in nutrition:
                continue
            item = nutrition[key]
            cards.append(
                "<td style='padding:8px;'>"
                "<div style='border-radius:12px; background:#f8fafc; padding:12px; border:1px solid #e2e8f0;'>"
                f"<div style='font-size:13px; color:{color}; font-weight:700;'>{item['label']}</div>"
                f"<div style='font-size:22px; color:#0f172a; font-weight:800;'>{item['value']:g} {item['unit']}</div>"
                "</div></td>"
            )

        bars = []
        bar_units = 24
        for key, color in macro_items:
            if key not in nutrition:
                continue
            item = nutrition[key]
            filled_units = 0
            if item["value"] > 0:
                filled_units = max(1, round(item["value"] / max_macro * bar_units))
            filled_units = min(bar_units, filled_units)
            empty_units = bar_units - filled_units
            bar_html = (
                f"<span style='color:{color}; font-family:Consolas, monospace;'>"
                f"{'█' * filled_units}</span>"
                f"<span style='color:#cbd5e1; font-family:Consolas, monospace;'>"
                f"{'░' * empty_units}</span>"
            )
            bars.append(
                "<tr>"
                f"<td style='width:68px; padding:6px 8px; color:#334155; font-weight:700;'>{item['label']}</td>"
                f"<td style='padding:6px 8px; font-size:16px;'>{bar_html}</td>"
                f"<td style='width:72px; padding:6px 8px; color:#475569;'>{item['value']:g} {item['unit']}</td>"
                "</tr>"
            )

        return (
            "<hr style='border:none; border-top:1px solid #e2e8f0; margin:16px 0;'>"
            "<h3 style='color:#0d9488; margin:8px 0;'>营养价值图示</h3>"
            "<p style='color:#64748b; margin:4px 0 10px 0;'>根据 AI 生成的估算营养成分自动提取，供家庭参考。</p>"
            "<table style='width:100%; border-collapse:collapse;'><tr>"
            + "".join(cards)
            + "</tr></table>"
            "<table style='width:100%; border-collapse:collapse; margin-top:8px;'>"
            + "".join(bars)
            + "</table>"
        )

    def show_recipe_detail(self, item):
        recipe = item.data(Qt.ItemDataRole.UserRole)
        if not recipe:
            return
        self._active_recipe_for_cooking = recipe
        self._update_mark_cooked_button_state()
        ingredient_names = self._ingredient_names_for_recipe()
        try:
            from services.recipe_service import get_recipe_service

            cached = get_recipe_service().get_cached_recipe_text(
                ingredient_names,
                recipe_name=recipe.get("name", ""),
                diet=self.diet_box.currentText(),
                cooking_time=self.time_box.currentText(),
                difficulty=self.diff_box.currentText(),
            )
        except Exception:
            cached = None
        if cached:
            self._on_ai_recipe_ready(cached)
            return
        ingredients = "、".join(recipe.get("ingredients", []))
        score_line = ""
        if recipe.get("match_score") is not None:
            score_line = (
                f"<p style='margin:4px 0;'><b>匹配度：</b>"
                f"<span style='color:#0d9488;'>{recipe['match_score']:.0%}</span></p>"
            )
        missing = recipe.get("missing_ingredients") or []
        missing_line = ""
        if missing:
            missing_line = (
                f"<p style='color:#c0392b; margin:4px 0;'><b>还缺食材：</b>"
                f"{'、'.join(missing)}</p>"
            )
        steps = recipe.get("steps") or []
        if steps:
            steps_html = (
                "<ol style='margin:4px 0 4px 20px; padding-left:16px;'>"
                + "".join(f"<li style='margin:3px 0;'>{s}</li>" for s in steps)
                + "</ol>"
            )
        else:
            steps_html = (
                f"<p style='line-height:1.8; color:#555555;'>"
                f"{recipe.get('description', '')}</p>"
            )
        tags_html = ",".join(recipe.get("tags", []))
        self.recipe_detail.setHtml(
            f"<h2 style='color:#0d9488; margin:0 0 8px 0;'>{recipe['name']}</h2>"
            f"<p style='margin:4px 0;'><b>推荐标签：</b>"
            f"<span style='color:#e67e22;'>{tags_html}</span> | "
            f"<b>烹饪时间：</b>{recipe.get('time', '')} | "
            f"<b>难度：</b>{recipe.get('diff', '')}</p>"
            f"{score_line}{missing_line}"
            f"<hr style='border:none; border-top:1px solid #E4E7ED;'>"
            f"<h3 style='color:#0f766e; margin:10px 0 4px 0;'>🛒 所需食材</h3>"
            f"<p style='line-height:1.6; margin:4px 0;'>{ingredients}</p>"
            f"<h3 style='color:#0f766e; margin:10px 0 4px 0;'>📝 烹饪步骤</h3>"
            f"{steps_html}"
            f"<p style='color:#888; font-size:12px; margin-top:10px;'>"
            f"这是本地菜谱库详情。需要更完整的 AI 版本时，点击上方「AI 重新生成」。</p>"
        )

    # (购物清单与饮食知识库选项卡直接复用精细化间距规则...)
    # 超市动线分区映射（创新点：按动线排序，少走冤枉路）
    SHOP_ZONE_ORDER = ["🥬 蔬果区", "🍖 肉类水产", "🥚 蛋奶冷藏", "❄️ 冷冻区", "🍚 粮油主食", "🧂 调味料", "🍪 零食饮料", "📦 其他"]
    SHOP_ZONE_KEYWORDS = {
        "🥬 蔬果区": ["菜", "瓜", "椒", "茄", "萝卜", "菇", "葱", "姜", "蒜", "果", "莓", "桃", "梨", "苹果", "橙", "柠檬", "香蕉"],
        "🍖 肉类水产": ["肉", "排", "鸡", "鸭", "牛", "猪", "羊", "鱼", "虾", "蟹", "贝"],
        "🥚 蛋奶冷藏": ["蛋", "奶", "酸奶", "芝士", "黄油", "豆腐"],
        "❄️ 冷冻区": ["冻", "冰", "雪糕"],
        "🍚 粮油主食": ["米", "面", "粉", "油", "粮", "馒头", "饺子", "面包"],
        "🧂 调味料": ["盐", "糖", "酱", "醋", "料酒", "胡椒", "辣椒粉", "味精", "鸡精", "花椒", "八角"],
        "🍪 零食饮料": ["饼", "薯片", "巧克力", "糖果", "可乐", "水", "饮料", "啤酒"],
    }

    @classmethod
    def _classify_shop_zone(cls, name: str) -> str:
        """根据商品名称匹配关键词，返回所属超市分区。"""
        n = (name or "").strip()
        for zone, kws in cls.SHOP_ZONE_KEYWORDS.items():
            for kw in kws:
                if kw in n:
                    return zone
        return "📦 其他"

    def init_shop_tab(self):
        self.shop_tab = QWidget()
        self.shop_table = QTableWidget()
        self.shop_table.setColumnCount(5)
        self.shop_table.setHorizontalHeaderLabels(["分区", "食材名称", "数量", "单位", "已购买"])
        self.shop_table.setShowGrid(False)
        self.shop_table.setAlternatingRowColors(True)
        self.shop_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.shop_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.shop_table.verticalHeader().setDefaultSectionSize(42)
        self.shop_table.verticalHeader().setVisible(False)
        shop_header = self.shop_table.horizontalHeader()
        shop_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(5):
            shop_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        btn_add = QPushButton("添加商品")
        btn_add.setObjectName("primaryBtn")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.show_add_shop_dialog)
        btn_voice_batch = QPushButton("🎤 语音批量添加")
        btn_voice_batch.setObjectName("secondaryBtn")
        btn_voice_batch.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_voice_batch.setToolTip("一次说出多个商品，自动解析为购物清单")
        btn_voice_batch.clicked.connect(self.voice_add_shopping_items)
        btn_export = QPushButton("导出 CSV")
        btn_export.setObjectName("secondaryBtn")
        btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_export.clicked.connect(self.export_shopping_list)
        btn_delete = QPushButton("删除选中")
        btn_delete.setObjectName("ghostBtn")
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.clicked.connect(self.delete_selected_shop_items)
        btn_clear = QPushButton("清空清单")
        btn_clear.setObjectName("dangerBtn")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(self.clear_all_shopping_items)

        toolbar_card = QFrame()
        toolbar_card.setObjectName("toolbarCard")
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(14, 10, 14, 10)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(btn_add)
        toolbar_layout.addWidget(btn_voice_batch)
        toolbar_layout.addWidget(btn_export)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(btn_delete)
        toolbar_layout.addWidget(btn_clear)

        header_label = QLabel("购物清单")
        header_label.setObjectName("pageTitle")
        shop_subtitle = QLabel("记录待购食材，支持一键导出 CSV")
        shop_subtitle.setObjectName("pageSubtitle")

        shop_card = QFrame()
        shop_card.setObjectName("contentCard")
        shop_card_layout = QVBoxLayout(shop_card)
        shop_card_layout.setContentsMargins(14, 12, 14, 12)
        shop_card_layout.addWidget(self.shop_table)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(header_label)
        layout.addWidget(shop_subtitle)
        layout.addWidget(toolbar_card)
        layout.addWidget(shop_card, 1)
        self.shop_tab.setLayout(layout)
        self.addTab(self.shop_tab, "购物清单")
        self.refresh_shop_table()

    def show_add_shop_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加购物清单项目")
        dialog.setMinimumWidth(380)
        name_edit = QLineEdit()
        name_row = QWidget()
        name_row_layout = QHBoxLayout(name_row)
        name_row_layout.setContentsMargins(0, 0, 0, 0)
        name_row_layout.setSpacing(6)
        btn_voice = QPushButton("🎤 语音")
        btn_voice.setObjectName("secondaryBtn")
        btn_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_voice.setToolTip("说出商品名称、数量和单位，自动填入表单")
        btn_voice.setFixedWidth(80)
        name_row_layout.addWidget(name_edit, 1)
        name_row_layout.addWidget(btn_voice)

        quantity_edit = QLineEdit()
        quantity_edit.setPlaceholderText("例如 2")
        unit_edit = QLineEdit()
        unit_edit.setPlaceholderText("例如 个 / 斤 / 瓶")
        bought_box = QComboBox()
        bought_box.addItems(["否", "是"])
        btn_voice.clicked.connect(
            lambda: self._fill_form_from_voice(dialog, name_edit, quantity_edit, unit_edit)
        )
        btn_confirm = QPushButton("确认添加")
        btn_confirm.setObjectName("primaryBtn")
        btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.addRow("食材名称", name_row)
        form_layout.addRow("数量", quantity_edit)
        form_layout.addRow("单位", unit_edit)
        form_layout.addRow("已购买", bought_box)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_confirm)
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(24, 22, 24, 20)
        main_layout.setSpacing(16)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        def add_item():
            name = name_edit.text().strip()
            quantity = quantity_edit.text().strip()
            unit = unit_edit.text().strip()
            bought = bought_box.currentText() == "是"
            if not name or not quantity or not unit:
                QMessageBox.warning(dialog, "输入错误", "请填写完整购物项目。")
                return
            new_item = {
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "bought": bought,
            }
            if self._user_id > 0:
                new_id = db_add_shopping_item(self._user_id, name, quantity, unit, bought)
                new_item["item_id"] = new_id
            self.shopping_items.append(new_item)
            self._log_op("添加购物项", f"{name} {quantity}{unit}")
            self.refresh_shop_table()
            dialog.accept()
        btn_confirm.clicked.connect(add_item)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def refresh_shop_table(self):
        # 给每项打上分区标签
        for it in self.shopping_items:
            it["zone"] = self._classify_shop_zone(it.get("name", ""))
        # 按超市动线顺序 + 是否已购买排序（已购买的沉底）
        order_index = {z: i for i, z in enumerate(self.SHOP_ZONE_ORDER)}
        sorted_items = sorted(
            enumerate(self.shopping_items),
            key=lambda x: (
                bool(x[1].get("bought")),
                order_index.get(x[1]["zone"], 999),
                x[1]["name"],
            ),
        )
        self.shop_table.setRowCount(len(sorted_items))
        # 记录排序后行号 -> 原始索引，便于操作回写
        self._shop_row_to_index = []
        for row, (orig_idx, item) in enumerate(sorted_items):
            self._shop_row_to_index.append(orig_idx)
            z_item = QTableWidgetItem(item["zone"])
            n_item = QTableWidgetItem(item["name"])
            q_item = QTableWidgetItem(str(item["quantity"]))
            u_item = QTableWidgetItem(item["unit"])
            for it in [z_item, n_item, q_item, u_item]:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if item.get("bought"):
                for it in [z_item, n_item, q_item, u_item]:
                    it.setForeground(QColor("#9ca3af"))
            self.shop_table.setItem(row, 0, z_item)
            self.shop_table.setItem(row, 1, n_item)
            self.shop_table.setItem(row, 2, q_item)
            self.shop_table.setItem(row, 3, u_item)
            cb_wrap = QWidget()
            cb_layout = QHBoxLayout(cb_wrap)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox = QCheckBox()
            checkbox.setChecked(bool(item.get("bought")))
            checkbox.stateChanged.connect(
                lambda _state, r=row: self._on_shop_item_checked(r)
            )
            cb_layout.addWidget(checkbox)
            self.shop_table.setCellWidget(row, 4, cb_wrap)
        self.refresh_dashboard_view()

    def _row_to_item_index(self, row: int) -> int:
        """显示行号 -> 真实 self.shopping_items 索引。"""
        if hasattr(self, "_shop_row_to_index") and 0 <= row < len(self._shop_row_to_index):
            return self._shop_row_to_index[row]
        return row

    def _on_shop_item_checked(self, row: int) -> None:
        real_idx = self._row_to_item_index(row)
        if real_idx < 0 or real_idx >= len(self.shopping_items):
            return
        cb = self.shop_table.cellWidget(row, 4)
        if cb is None:
            return
        checkbox = cb.findChild(QCheckBox)
        if checkbox is None:
            return
        bought = checkbox.isChecked()
        self.shopping_items[real_idx]["bought"] = bought
        iid = self.shopping_items[real_idx].get("item_id", -1)
        if self._user_id > 0 and iid and iid > 0:
            db_update_shopping_item(iid, bought)
        self.refresh_shop_table()  # 重排序：已购买项沉底

    def delete_selected_shop_items(self):
        rows = sorted({idx.row() for idx in self.shop_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "删除购物项目", "请先选择要删除的购物项。")
            return
        # 把显示行映射回真实索引后再降序删除
        real_indices = sorted(
            {self._row_to_item_index(r) for r in rows}, reverse=True
        )
        for idx in real_indices:
            if 0 <= idx < len(self.shopping_items):
                iid = self.shopping_items[idx].get("item_id", -1)
                if self._user_id > 0 and iid and iid > 0:
                    db_delete_shopping_item(iid)
                del self.shopping_items[idx]
        self.refresh_shop_table()

    def clear_all_shopping_items(self):
        if not self.shopping_items:
            return
        reply = QMessageBox.question(
            self,
            "清空购物清单",
            "确定要清空全部购物项吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._user_id > 0:
            db_clear_shopping(self._user_id)
        self.shopping_items.clear()
        self.refresh_shop_table()

    def export_shopping_list(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出购物清单", "购物清单.csv", "CSV 文件 (*.csv)")
        if not path: return
        try:
            with open(path, "w", newline='', encoding="utf-8-sig") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["食材名称", "数量", "单位", "已购买"])
                for item in self.shopping_items:
                    writer.writerow([item["name"], item["quantity"], item["unit"], "是" if item["bought"] else "否"])
            QMessageBox.information(self, "导出成功", f"已成功导出购物清单到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"保存文件时出错：{e}")

    def init_knowledge_tab(self):
        self.knowledge_tab = QWidget()
        self.knowledge_nav = QListWidget()
        self.knowledge_nav.addItems(["AI 对话"] + list(self.knowledge_books.keys()))
        self.knowledge_nav.setFixedWidth(220)
        self.knowledge_nav.currentRowChanged.connect(self.update_knowledge_content)
        self.knowledge_content = QTextEdit()
        self.knowledge_content.setReadOnly(True)
        self.knowledge_content.setPlaceholderText("选择左侧分类，查看饮食知识。")

        self._knowledge_history: list[dict] = []  # 多轮对话上下文

        self.knowledge_search_edit = QLineEdit()
        self.knowledge_search_edit.setPlaceholderText("输入问题，如 鸡蛋怎么保存 / 牛肉冷冻多久")
        self.knowledge_search_edit.returnPressed.connect(self.search_food_shelf_life)
        self.btn_knowledge_search = QPushButton("AI 查询")
        self.btn_knowledge_search.setObjectName("primaryBtn")
        self.btn_knowledge_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_knowledge_search.clicked.connect(self.search_food_shelf_life)
        self.btn_clear_history = QPushButton("清除对话")
        self.btn_clear_history.setObjectName("ghostBtn")
        self.btn_clear_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_history.clicked.connect(self._clear_knowledge_history)
        self.knowledge_search_status = QLabel("")
        self.knowledge_search_status.setObjectName("pageSubtitle")

        search_card = QFrame()
        search_card.setObjectName("toolbarCard")
        search_card_layout = QHBoxLayout(search_card)
        search_card_layout.setContentsMargins(14, 10, 14, 10)
        search_card_layout.setSpacing(8)
        search_card_layout.addWidget(self.knowledge_search_edit, 1)
        search_card_layout.addWidget(self.btn_knowledge_search)
        search_card_layout.addWidget(self.btn_clear_history)
        search_card_layout.addWidget(self.knowledge_search_status)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.knowledge_nav)
        splitter.addWidget(self.knowledge_content)
        splitter.setSizes([220, 700])
        splitter.setChildrenCollapsible(False)

        label = QLabel("饮食健康知识库")
        label.setObjectName("pageTitle")
        knowledge_subtitle = QLabel("食材保存、搭配与人群饮食建议，支持 AI 查询保质期")
        knowledge_subtitle.setObjectName("pageSubtitle")

        knowledge_card = QFrame()
        knowledge_card.setObjectName("contentCard")
        knowledge_card_layout = QVBoxLayout(knowledge_card)
        knowledge_card_layout.setContentsMargins(12, 12, 12, 12)
        knowledge_card_layout.addWidget(splitter)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(label)
        layout.addWidget(knowledge_subtitle)
        layout.addWidget(search_card)
        layout.addWidget(knowledge_card, 1)
        self.knowledge_tab.setLayout(layout)
        self.addTab(self.knowledge_tab, "饮食知识")
        self.knowledge_nav.setCurrentRow(0)

    def update_knowledge_content(self, index):
        if index < 0:
            self.knowledge_content.clear()
            return
        key = self.knowledge_nav.item(index).text()
        if key == "AI 对话":
            self._render_knowledge_history()
            return
        self.knowledge_content.setHtml(
            f"<h3 style='color:#0d9488; margin-top:0;'>{key}</h3>"
            f"<p style='line-height:1.8; color:#475569;'>{self.knowledge_books.get(key, '').replace(chr(10), '<br>')}</p>"
        )

    def _clear_knowledge_history(self) -> None:
        """清除多轮对话历史，开始新一轮问答。"""
        self._knowledge_history = []
        self.knowledge_search_status.setText("对话已清除")
        self.knowledge_content.setPlainText("对话已重置，请输入新问题。")
        self.knowledge_nav.setCurrentRow(0)

    def search_food_shelf_life(self):
        query = self.knowledge_search_edit.text().strip()
        if not query:
            QMessageBox.information(self, "提示", "请输入要查询的内容。")
            return

        self.knowledge_nav.setCurrentRow(0)
        self.btn_knowledge_search.setEnabled(False)
        self.knowledge_search_status.setText("AI 正在思考…")
        # 将用户消息追加到历史
        self._knowledge_history.append({"role": "user", "content": query})
        # 限制历史长度，避免超出模型 context window
        if len(self._knowledge_history) > 10:
            self._knowledge_history = self._knowledge_history[-10:]

        history_snapshot = list(self._knowledge_history)  # 传递快照给后台线程

        def task():
            from fallback.llm import get_llm
            llm = get_llm(prefer_local=False)
            system_msg = (
                "你是家庭食材保存与饮食知识助手。回答必须简短、准确、适合家庭日常。"
                "最多 4 条要点，每条不超过 25 字；不要重复同一句；不确定时提醒查看包装标识。"
                "如果用户在追问，请结合上下文回答。"
            )
            # 尝试使用多轮消息接口；不支持时退回单条 generate
            try:
                messages = [{"role": "system", "content": system_msg}] + history_snapshot
                return llm._chat_completion(messages, max_tokens=220, temperature=0.2)
            except (AttributeError, TypeError):
                # 本地 LLM 不支持 _chat_completion，降级为单轮
                ctx = ""
                for m in history_snapshot[:-1]:
                    role = "用户" if m["role"] == "user" else "助手"
                    ctx += f"{role}：{m['content']}\n"
                prompt = (ctx + f"用户：{query}\n助手：") if ctx else query
                return llm.generate(
                    prompt,
                    system=system_msg,
                    max_tokens=220,
                    temperature=0.2,
                )

        worker = Worker(task)
        worker.signals.result.connect(
            lambda text, q=query: self._on_shelf_life_ready(q, text)
        )
        worker.signals.error.connect(self._on_shelf_life_error)
        worker.signals.finished.connect(
            lambda: self.btn_knowledge_search.setEnabled(True)
        )
        self.thread_pool.start(worker)
        self.knowledge_search_edit.clear()

    def _on_shelf_life_ready(self, query: str, text: str):
        # 将 AI 回复也加入历史
        text = self._clean_ai_short_answer(text)
        self._knowledge_history.append({"role": "assistant", "content": text})
        self.knowledge_search_status.setText(f"对话 {len(self._knowledge_history) // 2} 轮")
        self._render_knowledge_history()

    @staticmethod
    def _clean_ai_short_answer(text: str) -> str:
        """清理本地小模型偶发的长重复片段，保证知识问答适合展示。"""
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        parts = re.split(r"[；;。]\s*", text)
        cleaned = []
        seen = set()
        for part in parts:
            part = part.strip(" ，,。；;")
            if not part:
                continue
            key = part[:18]
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(part)
            if len(cleaned) >= 4:
                break
        return "。\n".join(cleaned) + ("。" if cleaned else "")

    def _render_knowledge_history(self) -> None:
        # 构建多轮对话展示 HTML
        if not self._knowledge_history:
            self.knowledge_content.setHtml(
                "<h3 style='color:#0d9488; margin-top:0;'>AI 对话</h3>"
                "<p style='line-height:1.8; color:#64748b;'>输入问题后，AI 问答会保留在这里。</p>"
            )
            return
        html_parts = []
        for msg in self._knowledge_history:
            role = msg["role"]
            content = self._escape_html(msg["content"])
            if role == "user":
                html_parts.append(
                    f"<p style='margin:6px 0 2px 0;'>"
                    f"<b style='color:#0d9488;'>🙋 你：</b></p>"
                    f"<p style='margin:0 0 8px 0; color:#1e293b;'>{content}</p>"
                )
            else:
                html_parts.append(
                    f"<p style='margin:6px 0 2px 0;'>"
                    f"<b style='color:#7c3aed;'>🤖 AI：</b></p>"
                    f"<pre style='white-space:pre-wrap; font-family:Microsoft YaHei,sans-serif;"
                    f"line-height:1.7; color:#475569; margin:0 0 10px 0;'>{content}</pre>"
                )
        html_parts.append(
            "<p style='color:#94a3b8; font-size:11px; border-top:1px solid #e2e8f0; "
            "padding-top:6px; margin-top:4px;'>"
            "AI 回答仅供家庭参考，请以包装标识和实际气味、颜色、质地为准。"
            "点击「清除对话」可开始新话题。</p>"
        )
        self.knowledge_content.setHtml("".join(html_parts))

    def _on_shelf_life_error(self, message: str):
        # 回滚最后一条用户消息
        if self._knowledge_history and self._knowledge_history[-1]["role"] == "user":
            self._knowledge_history.pop()
        self.knowledge_search_status.setText("查询失败")
        self.knowledge_content.setPlainText(
            f"AI 查询失败：{message}\n\n"
            "请确认本地模型已下载，或配置 DEEPSEEK_API_KEY 后重启程序。"
        )

    def _parse_exclude_ingredients(self) -> set:
        text = self.exclude_edit.text().strip() if hasattr(self, "exclude_edit") else ""
        if not text:
            return set()
        parts = text.replace("，", ",").replace("、", ",").split(",")
        return {p.strip() for p in parts if p.strip()}

    def _merge_shopping_names(self, names: list) -> int:
        existing = {it["name"] for it in self.shopping_items}
        added = 0
        for name in names:
            n = (name or "").strip()
            if not n or n in existing:
                continue
            self.shopping_items.append(
                {"name": n, "quantity": "1", "unit": "个", "bought": False}
            )
            existing.add(n)
            added += 1
        self.refresh_shop_table()
        return added

    def add_missing_to_shopping_list(self) -> None:
        recipe = self._get_selected_recipe()
        if not recipe:
            QMessageBox.information(self, "提示", "请先在左侧选择一道菜谱。")
            return
        missing = recipe.get("missing_ingredients") or []
        if not missing:
            QMessageBox.information(self, "提示", "当前菜谱没有缺少的食材。")
            return
        added = self._merge_shopping_names(missing)
        QMessageBox.information(
            self, "已加入购物清单", f"已添加 {added} 种缺料食材（重复项已跳过）。"
        )

    def add_recipe_ingredients_to_shopping_list(self) -> None:
        recipe = self._get_selected_recipe()
        if not recipe:
            QMessageBox.information(self, "提示", "请先在左侧选择一道菜谱。")
            return
        names = recipe.get("ingredients") or []
        if not names:
            QMessageBox.information(self, "提示", "当前菜谱没有食材列表。")
            return
        added = self._merge_shopping_names(names)
        QMessageBox.information(
            self, "已加入购物清单", f"已添加 {added} 种食材（重复项已跳过）。"
        )

    # ============ 用户与权限 ============
    def _log_op(self, op_type: str, content: str = "") -> None:
        """便捷写日志，自动带上当前用户名。"""
        try:
            from db.db_manager import log_operation
            log_operation(self.current_user.get("username", "guest"), op_type, content)
        except Exception:
            pass

    def show_change_password_dialog(self) -> None:
        from db.db_manager import change_password

        dialog = QDialog(self)
        dialog.setWindowTitle("修改密码")
        dialog.setMinimumWidth(360)

        edit_old = QLineEdit()
        edit_old.setEchoMode(QLineEdit.EchoMode.Password)
        edit_old.setPlaceholderText("当前密码")
        edit_new1 = QLineEdit()
        edit_new1.setEchoMode(QLineEdit.EchoMode.Password)
        edit_new1.setPlaceholderText("新密码（≥ 4 位）")
        edit_new2 = QLineEdit()
        edit_new2.setEchoMode(QLineEdit.EchoMode.Password)
        edit_new2.setPlaceholderText("再次输入新密码")

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("账号", QLabel(self.current_user.get("username", "")))
        form.addRow("旧密码", edit_old)
        form.addRow("新密码", edit_new1)
        form.addRow("确认", edit_new2)

        btn_ok = QPushButton("保存")
        btn_ok.setObjectName("primaryBtn")
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostBtn")
        btn_ok.clicked.connect(lambda: None)  # 占位，后面覆盖

        def _on_ok():
            if edit_new1.text() != edit_new2.text():
                QMessageBox.warning(dialog, "失败", "两次输入的新密码不一致。")
                return
            ok, msg = change_password(
                self.current_user.get("username", ""),
                edit_old.text(),
                edit_new1.text(),
            )
            if not ok:
                QMessageBox.warning(dialog, "失败", msg)
                return
            self._log_op("修改密码")
            QMessageBox.information(dialog, "成功", "密码已更新。")
            dialog.accept()

        btn_ok.clicked.disconnect()
        btn_ok.clicked.connect(_on_ok)
        btn_cancel.clicked.connect(dialog.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addLayout(btn_row)
        dialog.exec()

    # ============ 管理员：操作日志 / 用户管理 ============
    def init_admin_tab(self) -> None:
        self.admin_tab = QWidget()

        title = QLabel("管理员控制台")
        title.setObjectName("pageTitle")
        subtitle = QLabel("查看全系统操作日志与注册用户")
        subtitle.setObjectName("pageSubtitle")

        # —— 用户表 —— #
        self.admin_user_table = QTableWidget()
        self.admin_user_table.setColumnCount(3)
        self.admin_user_table.setHorizontalHeaderLabels(["ID", "用户名", "角色"])
        self.admin_user_table.verticalHeader().setVisible(False)
        self.admin_user_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.admin_user_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # —— 日志表 —— #
        self.admin_log_table = QTableWidget()
        self.admin_log_table.setColumnCount(4)
        self.admin_log_table.setHorizontalHeaderLabels(["时间", "用户", "操作类型", "详情"])
        self.admin_log_table.verticalHeader().setVisible(False)
        self.admin_log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        h = self.admin_log_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setObjectName("primaryBtn")
        btn_refresh.clicked.connect(self.refresh_admin_view)
        btn_export = QPushButton("导出日志 CSV")
        btn_export.setObjectName("secondaryBtn")
        btn_export.clicked.connect(self.export_operation_logs)
        self.btn_crawl = QPushButton("一键更新菜谱库")
        self.btn_crawl.setObjectName("secondaryBtn")
        self.btn_crawl.setToolTip("从 xiangha.com 抓取热门菜谱，pandas 去重后增量合并到本地")
        self.btn_crawl.clicked.connect(self.start_crawl_recipes)
        self.crawl_status = QLabel("")
        self.crawl_status.setObjectName("pageSubtitle")

        toolbar = QFrame()
        toolbar.setObjectName("toolbarCard")
        tlayout = QHBoxLayout(toolbar)
        tlayout.setContentsMargins(14, 10, 14, 10)
        tlayout.setSpacing(8)
        tlayout.addWidget(btn_refresh)
        tlayout.addWidget(btn_export)
        tlayout.addWidget(self.btn_crawl)
        tlayout.addWidget(self.crawl_status, 1)
        tlayout.addStretch()

        users_card = QFrame()
        users_card.setObjectName("contentCard")
        ucl = QVBoxLayout(users_card)
        ucl.setContentsMargins(14, 12, 14, 14)
        ucl.setSpacing(8)
        ul = QLabel("已注册用户")
        ul.setObjectName("sectionLabel")
        ucl.addWidget(ul)
        ucl.addWidget(self.admin_user_table, 1)

        logs_card = QFrame()
        logs_card.setObjectName("contentCard")
        lcl = QVBoxLayout(logs_card)
        lcl.setContentsMargins(14, 12, 14, 14)
        lcl.setSpacing(8)
        ll = QLabel("操作日志（最近 200 条）")
        ll.setObjectName("sectionLabel")
        lcl.addWidget(ll)
        lcl.addWidget(self.admin_log_table, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(users_card)
        splitter.addWidget(logs_card)
        splitter.setSizes([320, 760])
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self.admin_tab)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(toolbar)
        layout.addWidget(splitter, 1)

        self.addTab(self.admin_tab, "管理员")
        self.refresh_admin_view()

    def refresh_admin_view(self) -> None:
        if not hasattr(self, "admin_user_table"):
            return
        try:
            from db.db_manager import fetch_operation_logs, list_users
            users = list_users()
            logs = fetch_operation_logs(limit=200)
        except Exception as e:
            QMessageBox.warning(self, "管理员数据读取失败", str(e))
            return
        self.admin_user_table.setRowCount(len(users))
        for r, (uid, name, role) in enumerate(users):
            self.admin_user_table.setItem(r, 0, QTableWidgetItem(str(uid)))
            self.admin_user_table.setItem(r, 1, QTableWidgetItem(name))
            self.admin_user_table.setItem(r, 2, QTableWidgetItem(role))
        self.admin_log_table.setRowCount(len(logs))
        for r, (ts, uname, op, content) in enumerate(logs):
            self.admin_log_table.setItem(r, 0, QTableWidgetItem(str(ts)))
            self.admin_log_table.setItem(r, 1, QTableWidgetItem(uname or ""))
            self.admin_log_table.setItem(r, 2, QTableWidgetItem(op or ""))
            self.admin_log_table.setItem(r, 3, QTableWidgetItem(content or ""))

    def start_crawl_recipes(self) -> None:
        """后台线程跑爬虫，状态实时反馈到 UI。"""
        try:
            import spider  # noqa: F401
        except Exception as e:
            QMessageBox.warning(self, "爬虫不可用", f"未能加载 spider 模块：{e}")
            return

        self.btn_crawl.setEnabled(False)
        self.crawl_status.setText("准备抓取…")
        self._log_op("启动菜谱爬虫")

        # 跨线程进度提示
        class _Sig(QObject):
            tip = pyqtSignal(str)
        sig = _Sig()
        sig.tip.connect(self.crawl_status.setText)

        def task():
            import spider as _spider
            return _spider.run(pages=2, progress_cb=lambda m: sig.tip.emit(m))

        def _done(stats):
            msg = (
                f"完成：新增 {stats['new']} 条 / 总 {stats['total']} 条；"
                f"失败列表 {stats['failed_pages']}，失败详情 {stats['failed_details']}"
            )
            self.crawl_status.setText(msg)
            self._log_op("菜谱爬虫完成", json.dumps(stats, ensure_ascii=False))
            QMessageBox.information(self, "菜谱库已更新", msg)

        def _err(err):
            self.crawl_status.setText(f"失败：{err}")
            self._log_op("菜谱爬虫失败", err)
            QMessageBox.critical(self, "爬虫失败", err)

        worker = Worker(task)
        worker.signals.result.connect(_done)
        worker.signals.error.connect(_err)
        worker.signals.finished.connect(lambda: self.btn_crawl.setEnabled(True))
        self.thread_pool.start(worker)

    def export_operation_logs(self) -> None:
        from db.db_manager import fetch_operation_logs
        path, _ = QFileDialog.getSaveFileName(self, "导出操作日志", "操作日志.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            rows = fetch_operation_logs(limit=10000)
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["时间", "用户", "操作类型", "详情"])
                writer.writerows(rows)
            self._log_op("导出操作日志", f"{len(rows)} 条")
            QMessageBox.information(self, "导出成功", f"已导出 {len(rows)} 条日志到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ============ 语音输入通用 ============
    def _capture_voice_text(self, prompt: str = "请说出您要添加的内容") -> str | None:
        """弹出语音录入小窗：自动录音 → 显示识别结果 → 用户确认后返回文本。

        返回 None 表示用户取消。失败/超时时会显示错误提示。
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("语音输入")
        dialog.setMinimumWidth(420)

        tip = QLabel(prompt)
        tip.setObjectName("sectionLabel")
        tip.setWordWrap(True)

        status = QLabel("准备就绪")
        status.setObjectName("pageSubtitle")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_edit = QTextEdit()
        text_edit.setPlaceholderText("识别结果会出现在这里，您也可以手动修改")
        text_edit.setMinimumHeight(110)

        btn_record = QPushButton("🎤 开始录音")
        btn_record.setObjectName("primaryBtn")
        btn_record.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_ok = QPushButton("使用此内容")
        btn_ok.setObjectName("secondaryBtn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setEnabled(False)

        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(btn_record)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(tip)
        layout.addWidget(text_edit)
        layout.addWidget(status)
        layout.addLayout(btn_row)

        def _enable_ok_on_text():
            btn_ok.setEnabled(bool(text_edit.toPlainText().strip()))
        text_edit.textChanged.connect(_enable_ok_on_text)

        def _start_record():
            btn_record.setEnabled(False)
            status.setText("正在聆听…请说话")

            def task():
                return _recognize_voice_once()

            worker = Worker(task)
            worker.signals.result.connect(_on_result)
            worker.signals.error.connect(_on_error)
            worker.signals.finished.connect(lambda: btn_record.setEnabled(True))
            self.thread_pool.start(worker)

        def _on_result(text: str):
            status.setText("识别完成，可继续手动修改")
            current = text_edit.toPlainText().strip()
            if current:
                text_edit.setPlainText(f"{current} {text}".strip())
            else:
                text_edit.setPlainText(text)

        def _on_error(message: str):
            status.setText(f"识别失败：{message}")

        btn_record.clicked.connect(_start_record)
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return text_edit.toPlainText().strip() or None

    def _fill_form_from_voice(self, dialog: QDialog, name_edit: QLineEdit,
                              quantity_edit, unit_widget) -> None:
        """共用：录音 → 解析为购物项 → 填回表单（取第一项）。"""
        try:
            from services.voice_shopping_service import parse_voice_to_shopping_list
        except Exception as e:
            QMessageBox.warning(dialog, "语音功能不可用", f"语音服务未就绪：{e}")
            return

        text = self._capture_voice_text("请说出食材名称、数量和单位，例如：两斤猪肉")
        if not text:
            return
        items = parse_voice_to_shopping_list(text)
        if not items:
            QMessageBox.information(dialog, "未识别", f"未能从「{text}」中解析出食材，您可以手动填写。")
            name_edit.setText(text)
            return
        first = items[0]
        name_edit.setText(first.name)
        if quantity_edit is not None:
            quantity_edit.setText(str(first.quantity))
        if isinstance(unit_widget, QComboBox):
            idx = unit_widget.findText(first.unit)
            if idx >= 0:
                unit_widget.setCurrentIndex(idx)
            else:
                unit_widget.setEditText(first.unit)
        elif isinstance(unit_widget, QLineEdit):
            unit_widget.setText(first.unit)

    def voice_add_shopping_items(self) -> None:
        """购物清单工具栏：一次说出多项，批量添加到清单。"""
        try:
            from services.voice_shopping_service import voice_text_to_shopping_items
        except Exception as e:
            QMessageBox.warning(self, "语音功能不可用", f"语音服务未就绪：{e}")
            return

        text = self._capture_voice_text(
            "请一次说出所有要购买的商品，例如：买三斤猪肉，两个鸡蛋，一瓶酱油"
        )
        if not text:
            return
        new_items = voice_text_to_shopping_items(text, existing_items=self.shopping_items)
        if not new_items:
            QMessageBox.information(self, "未识别", f"未能从「{text}」中解析出新商品。")
            return
        for item in new_items:
            if self._user_id > 0:
                new_id = db_add_shopping_item(
                    self._user_id, item["name"], item["quantity"], item["unit"], item["bought"]
                )
                item["item_id"] = new_id
        self.shopping_items.extend(new_items)
        self.refresh_shop_table()
        QMessageBox.information(
            self,
            "语音添加完成",
            f"已添加 {len(new_items)} 项（与已有清单去重）。",
        )

    def _refresh_llm_status_label(self) -> None:
        if not hasattr(self, "llm_status_label"):
            return
        try:
            from services.recipe_service import get_recipe_service

            status = get_recipe_service().llm_status()
            engine = status.get("engine", "none")
            labels = {"local": "本地 Qwen", "cloud": "云端 DeepSeek", "none": "未就绪"}
            text = f"AI 引擎 · {labels.get(engine, engine)}"
            tooltip = status.get("hint", "") or text
            self.llm_status_label.setText(text)
            self.llm_status_label.setToolTip(tooltip)
            self.llm_status_label.setObjectName(
                "statusChip" if engine in ("local", "cloud") else "statusChipMuted"
            )
            self.llm_status_label.style().unpolish(self.llm_status_label)
            self.llm_status_label.style().polish(self.llm_status_label)
            if hasattr(self, "dashboard_ai_chip"):
                self.dashboard_ai_chip.setText(text)
        except Exception as e:
            self.llm_status_label.setText("AI 引擎 · 未知")
            self.llm_status_label.setToolTip(str(e))
            if hasattr(self, "dashboard_ai_chip"):
                self.dashboard_ai_chip.setText("AI 引擎 · 未知")

    def init_stats_tab(self) -> None:
        import matplotlib
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
        matplotlib.rcParams["axes.unicode_minus"] = False

        self.stats_tab = QWidget()
        self.stats_figure = Figure(figsize=(9, 4))
        self.stats_canvas = FigureCanvas(self.stats_figure)

        btn_refresh = QPushButton("刷新图表")
        btn_refresh.setObjectName("primaryBtn")
        btn_refresh.clicked.connect(self.refresh_stats_view)

        self.stats_summary_label = QLabel("暂无食材数据")
        self.stats_summary_label.setObjectName("pageSubtitle")
        self.stats_summary_label.setWordWrap(True)

        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(8)
        self.stats_table.setHorizontalHeaderLabels(
            ["食材", "库存数量", "估算重量(g)", "热量(kcal)", "蛋白质(g)", "碳水(g)", "脂肪(g)", "备注"]
        )
        self.stats_table.setShowGrid(False)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_table.verticalHeader().setVisible(False)
        stats_header = self.stats_table.horizontalHeader()
        stats_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(7):
            stats_header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        stats_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self.stats_tab)
        title = QLabel("数据统计")
        title.setObjectName("pageTitle")
        subtitle = QLabel("基于当前冰箱库存估算总热量、蛋白质、碳水和脂肪")
        subtitle.setObjectName("pageSubtitle")
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(btn_row)
        layout.addWidget(self.stats_summary_label)
        layout.addWidget(self.stats_canvas, 1)
        layout.addWidget(self.stats_table, 1)
        self.addTab(self.stats_tab, "数据统计")
        self.refresh_stats_view()

    def refresh_stats_view(self) -> None:
        if not hasattr(self, "stats_figure"):
            return
        summary = summarize_pantry_nutrition(self.ingredients)
        self._update_stats_summary(summary)
        self._update_stats_table(summary)
        self._update_stats_charts(summary)

    def _update_stats_summary(self, summary: dict) -> None:
        totals = summary["totals"]
        if not summary["rows"]:
            self.stats_summary_label.setText("暂无冰箱食材，请先在「食材管理」中添加食材。")
            return
        self.stats_summary_label.setText(
            "当前库存估算："
            f"总重量 {totals['grams']:.1f} g，"
            f"总热量 {totals['calories']:.1f} kcal，"
            f"蛋白质 {totals['protein']:.1f} g，"
            f"碳水 {totals['carbs']:.1f} g，"
            f"脂肪 {totals['fat']:.1f} g。"
            f"已识别 {summary['recognized_count']} 种，"
            f"未识别 {summary['unrecognized_count']} 种。"
        )

    def _update_stats_table(self, summary: dict) -> None:
        rows = summary["rows"]
        self.stats_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                row["name"],
                row["amount_display"],
                f"{row['grams']:.1f}",
                f"{row['calories']:.1f}",
                f"{row['protein']:.1f}",
                f"{row['carbs']:.1f}",
                f"{row['fat']:.1f}",
                row["note"] or "已按本地营养表估算",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 7:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.stats_table.setItem(row_idx, col, item)

    def _update_stats_charts(self, summary: dict) -> None:
        self.stats_figure.clear()

        ax1 = self.stats_figure.add_subplot(1, 2, 1)
        totals = summary["totals"]
        macro_calories = [
            totals["protein"] * 4,
            totals["carbs"] * 4,
            totals["fat"] * 9,
        ]
        labels = ["蛋白质", "碳水", "脂肪"]
        if sum(macro_calories) > 0:
            ax1.pie(macro_calories, labels=labels, autopct="%1.0f%%", startangle=90)
        else:
            ax1.text(0.5, 0.5, "暂无可统计营养数据", ha="center", va="center")
            ax1.set_axis_off()
        ax1.set_title("三大营养素热量占比")

        ax2 = self.stats_figure.add_subplot(1, 2, 2)
        calorie_rows = [
            row for row in summary["rows"] if row["calories"] > 0
        ]
        calorie_rows.sort(key=lambda r: r["calories"], reverse=True)
        top_rows = calorie_rows[:8]
        if top_rows:
            names = [row["name"] for row in top_rows]
            values = [row["calories"] for row in top_rows]
            ax2.bar(names, values, color="#0d9488")
            ax2.set_ylabel("kcal")
        else:
            ax2.text(0.5, 0.5, "暂无热量数据", ha="center", va="center")
            ax2.set_axis_off()
        ax2.set_title("食材热量贡献 Top 8")
        ax2.tick_params(axis="x", rotation=30)
        self.stats_figure.tight_layout()
        self.stats_canvas.draw()