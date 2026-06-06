from PyQt6.QtWidgets import *
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, Qt, QDate, QThreadPool
from PyQt6.QtGui import QColor
import csv
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

class MainWindow(QTabWidget):
    def __init__(self):
        super().__init__()
        self.ingredients = []
        self.shopping_items = []
        self._active_recipe_for_cooking = None
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
        self.init_ingredient_tab()
        self.init_recipe_tab()
        self.init_shop_tab()
        self.init_knowledge_tab()
        self.init_stats_tab()
        self.currentChanged.connect(self._on_main_tab_changed)
        self.thread_pool = QThreadPool.globalInstance()
        self._refresh_llm_status_label()

    def init_window(self):
        self.setObjectName("mainWindow")
        self.setWindowTitle("家庭食材管理与智能食谱助手")
        self.setMinimumSize(1080, 720)
        self.resize(1120, 760)
        self.tabBar().setDocumentMode(True)
        self.tabBar().setDrawBase(False)

    def _on_main_tab_changed(self, index: int):
        if 0 <= index < self.count() and self.widget(index) is self.recipe_tab:
            if self.mode_box.currentText() == "用现有食材做":
                self._refresh_ingredient_picker()

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
        self.ingredient_table.setColumnWidth(5, 128)

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

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_add_ingredient)
        btn_layout.addWidget(self.btn_remove_ingredient)
        btn_layout.addStretch()

        title_label = QLabel("食材管理中心")
        title_label.setObjectName("pageTitle")
        subtitle = QLabel("管理冰箱库存，关注保质期提醒")
        subtitle.setObjectName("pageSubtitle")

        table_card = QFrame()
        table_card.setObjectName("contentCard")
        table_card_layout = QVBoxLayout(table_card)
        table_card_layout.setContentsMargins(12, 12, 16, 12)
        table_card_layout.addWidget(self.ingredient_table)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(subtitle)
        layout.addLayout(btn_layout)
        layout.addWidget(table_card, 1)
        self.ingredient_tab.setLayout(layout)
        self.addTab(self.ingredient_tab, "食材管理")

        self.refresh_ingredient_table(show_expiry_alert=True)

    def show_add_ingredient_dialog(self, edit_row=None):
        if not isinstance(edit_row, int):
            edit_row = None
        is_edit = edit_row is not None and 0 <= edit_row < len(self.ingredients)
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑食材" if is_edit else "添加食材入库")
        dialog.setFixedSize(380, 400)

        name_edit = QLineEdit()
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
        expiry_edit = QDateEdit()
        expiry_edit.setDisplayFormat("yyyy-MM-dd")
        expiry_edit.setDate(QDate.currentDate())
        expiry_edit.setCalendarPopup(True) # 开启高级感的日历弹出视图
        
        category_box = QComboBox()
        category_box.addItems(["蔬菜", "肉类", "水果", "调料", "主食", "水产", "蛋奶"])
        location_edit = QLineEdit()

        btn_confirm = QPushButton("保存修改" if is_edit else "确认添加")
        btn_confirm.setObjectName("primaryBtn")
        btn_cancel = QPushButton("取消")

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
            location_edit.setText(item.get("location", ""))

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(25, 25, 25, 15)
        form_layout.addRow("食材名称：", name_edit)
        form_layout.addRow("数量/单位：", amount_unit_row)
        form_layout.addRow("保质期：", expiry_edit)
        form_layout.addRow("食材分类：", category_box)
        form_layout.addRow("存放位置：", location_edit)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(25, 0, 25, 25)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_confirm)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        dialog.setLayout(main_layout)

        def add_item():
            name = name_edit.text().strip()
            unit = unit_box.currentText().strip() or "个"
            expiry = expiry_edit.date().toPyDate()
            category = category_box.currentText()
            location = location_edit.text().strip()
            if not name:
                QMessageBox.warning(dialog, "输入错误", "请填写食材名称。")
                return
            try:
                amount = parse_amount_text(amount_edit.text())
            except ValueError:
                QMessageBox.warning(dialog, "输入错误", "请填写有效的数量（大于 0 的数字）。")
                return
            entry = {
                "name": name,
                "amount": amount,
                "unit": unit,
                "expiry": expiry,
                "category": category,
                "location": location,
            }
            if is_edit:
                self.ingredients[edit_row] = entry
            else:
                self.ingredients.append(entry)
            self.refresh_ingredient_table(show_expiry_alert=True)
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
            location_item = QTableWidgetItem(item["location"])

            for cell_item in [
                name_item, amount_unit_item, expiry_item, category_item, location_item
            ]:
                cell_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            op_container = QWidget()
            op_container.setStyleSheet("background: transparent;")
            op_layout = QHBoxLayout(op_container)
            op_layout.setContentsMargins(2, 4, 4, 4)
            op_layout.setSpacing(4)
            op_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit_btn = QPushButton("编辑")
            edit_btn.setObjectName("secondaryBtn")
            edit_btn.setFixedSize(48, 24)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.clicked.connect(
                lambda _checked, r=row: self.show_add_ingredient_dialog(edit_row=r)
            )
            delete_btn = QPushButton("删除")
            delete_btn.setObjectName("dangerBtn")
            delete_btn.setFixedSize(48, 24)
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

    # (delete_ingredient, remove_selected_ingredient, check_expiry_alert 保持原样不变...)
    def delete_ingredient(self, row):
        if 0 <= row < len(self.ingredients):
            del self.ingredients[row]
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
            QMessageBox.warning(self, "保质期提醒", "\n\n".join(message_parts))

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
        dialog.setFixedSize(300, 140)
        label = QLabel("本道菜按几人份扣减库存？")
        servings_box = QComboBox()
        for n in SERVING_OPTIONS:
            servings_box.addItem(f"{n} 人份", n)
        servings_box.setCurrentIndex(0)
        btn_ok = QPushButton("下一步")
        btn_ok.setObjectName("primaryBtn")
        btn_cancel = QPushButton("取消")
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(label)
        layout.addWidget(servings_box)
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
        btn_cancel = QPushButton("取消")
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(QLabel("可调整每种食材的扣减数量，0 表示不扣减："))
        layout.addWidget(table)
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
        self.mode_box = QComboBox()
        self.mode_box.addItems(["用现有食材做", "按需求做"])
        self.mode_box.currentTextChanged.connect(self._on_recipe_mode_changed)

        self.ingredient_pick_widget = QWidget()
        pick_layout = QVBoxLayout(self.ingredient_pick_widget)
        pick_layout.setContentsMargins(0, 4, 0, 0)
        pick_layout.setSpacing(6)
        pick_label = QLabel("勾选要用于推荐的食材：")
        pick_label.setObjectName("sectionLabel")
        self.ingredient_pick_list = QListWidget()
        self.ingredient_pick_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.ingredient_pick_list.setMinimumHeight(140)
        self.ingredient_pick_list.setMaximumHeight(240)
        self.ingredient_pick_list.setSpacing(4)
        pick_layout.addWidget(pick_label)
        pick_layout.addWidget(self.ingredient_pick_list)

        self.diet_box = QComboBox()
        self.diet_box.addItems(["家常菜", "减脂餐", "增肌餐", "素食", "控糖"])
        self.time_box = QComboBox()
        self.time_box.addItems(["15分钟内", "15-30分钟", "30分钟以上"])
        self.diff_box = QComboBox()
        self.diff_box.addItems(["简单", "中等", "困难"])
        for combo in (
            self.mode_box,
            self.diet_box,
            self.time_box,
            self.diff_box,
        ):
            combo.setMinimumHeight(36)

        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText("不吃/排除的食材，逗号分隔，如：香菜,葱")

        btn_generate = QPushButton("生成食谱")
        btn_generate.setObjectName("primaryBtn") # 高亮绿
        btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_generate.clicked.connect(self.generate_recipe_list)

        self.btn_ai_recipe = QPushButton("AI 生成详细步骤")
        self.btn_ai_recipe.setObjectName("secondaryBtn")
        self.btn_ai_recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_recipe.clicked.connect(self.start_ai_recipe_generation)

        self.btn_mark_cooked = QPushButton("我已做完")
        self.btn_mark_cooked.setObjectName("primaryBtn")
        self.btn_mark_cooked.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mark_cooked.setEnabled(False)
        self.btn_mark_cooked.clicked.connect(self.start_mark_cooked_flow)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.addRow("生成模式：", self.mode_box)
        form_layout.addRow("", self.ingredient_pick_widget)
        form_layout.addRow("饮食偏好：", self.diet_box)
        form_layout.addRow("烹饪时间：", self.time_box)
        form_layout.addRow("难度级别：", self.diff_box)
        form_layout.addRow("排除食材：", self.exclude_edit)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_generate)
        btn_row.addWidget(self.btn_ai_recipe)
        btn_row.addWidget(self.btn_mark_cooked)
        btn_row.addStretch()
        form_layout.addRow("", btn_row)

        self.btn_buy_missing = QPushButton("购买缺料")
        self.btn_buy_missing.setObjectName("secondaryBtn")
        self.btn_buy_missing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buy_missing.clicked.connect(self.add_missing_to_shopping_list)
        self.btn_add_recipe_shop = QPushButton("加入购物清单")
        self.btn_add_recipe_shop.setObjectName("secondaryBtn")
        self.btn_add_recipe_shop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_recipe_shop.clicked.connect(self.add_recipe_ingredients_to_shopping_list)
        shop_btn_row = QHBoxLayout()
        shop_btn_row.addWidget(self.btn_buy_missing)
        shop_btn_row.addWidget(self.btn_add_recipe_shop)
        shop_btn_row.addStretch()
        form_layout.addRow("购物联动：", shop_btn_row)

        self.llm_status_label = QLabel("")
        self.llm_status_label.setObjectName("pageSubtitle")
        form_layout.addRow("AI 引擎：", self.llm_status_label)

        group = QGroupBox("个性化食谱筛选")
        group.setLayout(form_layout)

        header_label = QLabel("智能食谱助手")
        header_label.setObjectName("pageTitle")
        recipe_subtitle = QLabel("根据冰箱食材或饮食偏好，为您推荐合适菜谱")
        recipe_subtitle.setObjectName("pageSubtitle")

        self.recipe_list = QListWidget()
        self.recipe_list.itemClicked.connect(self.show_recipe_detail)
        self.recipe_list.currentItemChanged.connect(
            lambda _cur, _prev: self._update_mark_cooked_button_state()
        )

        self.recipe_detail = QTextEdit()
        self.recipe_detail.setReadOnly(True)
        self.recipe_detail.setPlaceholderText("💡 请在左侧选择感兴趣的食谱查看详细做法、配料用量及烹饪技巧说明。")

        recipe_card = QFrame()
        recipe_card.setObjectName("contentCard")
        recipe_card_layout = QHBoxLayout(recipe_card)
        recipe_card_layout.setContentsMargins(12, 12, 12, 12)
        recipe_card_layout.setSpacing(12)
        recipe_card_layout.addWidget(self.recipe_list, 2)
        recipe_card_layout.addWidget(self.recipe_detail, 3)

        tip_label = QLabel("推荐菜谱")
        tip_label.setObjectName("sectionLabel")

        recipe_card.setMinimumHeight(360)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(header_label)
        layout.addWidget(recipe_subtitle)
        layout.addWidget(group)
        layout.addWidget(tip_label)
        layout.addWidget(recipe_card, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setWidget(content)

        tab_layout = QVBoxLayout(self.recipe_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        self.addTab(self.recipe_tab, "智能食谱")
        
        self.recipe_list.clear()
        self._on_recipe_mode_changed(self.mode_box.currentText())

    def generate_recipe_list(self):
        mode = self.mode_box.currentText()
        diet = self.diet_box.currentText()
        time = self.time_box.currentText()
        diff = self.diff_box.currentText()
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
            self.recipe_detail.clear()
            self.recipe_list.setCurrentRow(0)
            self.show_recipe_detail(self.recipe_list.item(0))
            self._active_recipe_for_cooking = results[0]
        else:
            self.recipe_list.addItem("⚠️ 未找到匹配食谱，请调整食材或筛选条件")
            self.recipe_detail.clear()
            self._active_recipe_for_cooking = None
        self._update_mark_cooked_button_state()

    def start_ai_recipe_generation(self):
        if not self.ingredients:
            QMessageBox.information(self, "提示", "请先在「食材管理」中添加食材。")
            return
        ingredient_names = self._ingredient_names_for_recipe()
        if self.mode_box.currentText() == "用现有食材做" and not ingredient_names:
            QMessageBox.information(self, "提示", "请至少勾选一种要用于生成菜谱的食材。")
            return

        current = self.recipe_list.currentItem()
        recipe = current.data(Qt.ItemDataRole.UserRole) if current else None
        if recipe and isinstance(recipe, dict):
            self._active_recipe_for_cooking = recipe
        recipe_name = (recipe or {}).get("name", "")
        diet = self.diet_box.currentText()
        time = self.time_box.currentText()
        diff = self.diff_box.currentText()

        self.btn_ai_recipe.setEnabled(False)
        self.recipe_detail.setPlainText("⏳ AI 正在生成详细菜谱，请稍候…")

        from services.recipe_service import get_recipe_service

        svc = get_recipe_service()

        def task():
            return svc.generate_recipe_text(
                ingredient_names,
                recipe_name=recipe_name,
                diet=diet,
                cooking_time=time,
                difficulty=diff,
            )

        worker = Worker(task)
        worker.signals.result.connect(self._on_ai_recipe_ready)
        worker.signals.error.connect(self._on_ai_recipe_error)
        worker.signals.finished.connect(lambda: self.btn_ai_recipe.setEnabled(True))
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
        html = (
            "<h2 style='color:#0d9488;'>AI 生成菜谱</h2>"
            f"<pre style='white-space:pre-wrap; font-family:Microsoft YaHei, sans-serif;"
            f" line-height:1.7; color:#333;'>{self._escape_html(display_text)}</pre>"
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
        if recipe:
            self._active_recipe_for_cooking = recipe
            self._update_mark_cooked_button_state()
            ingredients = "、".join(recipe.get("ingredients", []))
            score_line = ""
            if recipe.get("match_score") is not None:
                score_line = f"<p><b>匹配度：</b>{recipe['match_score']:.0%}</p>"
            missing = recipe.get("missing_ingredients") or []
            missing_line = ""
            if missing:
                missing_line = (
                    f"<p style='color:#c0392b;'><b>还缺食材：</b>"
                    f"{'、'.join(missing)}</p>"
                )
            steps = recipe.get("steps") or []
            steps_html = ""
            if steps:
                steps_html = "<ol>" + "".join(
                    f"<li style='margin:4px 0;'>{s}</li>" for s in steps
                ) + "</ol>"
            else:
                steps_html = (
                    f"<p style='line-height:1.8; color:#555555;'>{recipe.get('description', '')}</p>"
                )
            self.recipe_detail.setHtml(
                f"<h2 style='color:#0d9488;'>{recipe['name']}</h2>"
                f"<p><b>推荐标签：</b><span style='color:#e67e22;'>{','.join(recipe.get('tags', []))}</span> | "
                f"<b>烹饪时间：</b>{recipe.get('time', '')} | <b>难度：</b>{recipe.get('diff', '')}</p>"
                f"{score_line}{missing_line}"
                f"<hr style='border:none; border-top:1px solid #E4E7ED;'>"
                f"<h3>🛒 所需食材：</h3><p style='line-height:1.6;'>{ingredients}</p>"
                f"<h3>📝 烹饪步骤：</h3>{steps_html}"
                f"<p style='color:#888; font-size:12px;'>点击「AI 生成详细步骤」可获取完整用量与技巧。</p>"
            )

    # (购物清单与饮食知识库选项卡直接复用精细化间距规则...)
    def init_shop_tab(self):
        self.shop_tab = QWidget()
        self.shop_table = QTableWidget()
        self.shop_table.setColumnCount(4)
        self.shop_table.setHorizontalHeaderLabels(["食材名称", "数量", "单位", "已购买"])
        self.shop_table.setShowGrid(False)
        self.shop_table.setAlternatingRowColors(True)
        self.shop_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.shop_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.shop_table.verticalHeader().setDefaultSectionSize(42)
        self.shop_table.verticalHeader().setVisible(False)
        shop_header = self.shop_table.horizontalHeader()
        shop_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(4):
            shop_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        btn_add = QPushButton("添加商品")
        btn_add.setObjectName("primaryBtn")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.show_add_shop_dialog)
        btn_delete = QPushButton("删除选中")
        btn_delete.setObjectName("dangerBtn")
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.clicked.connect(self.delete_selected_shop_items)
        btn_export = QPushButton("导出购物清单")
        btn_export.setObjectName("primaryBtn")
        btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_export.clicked.connect(self.export_shopping_list)
        btn_clear = QPushButton("清空清单")
        btn_clear.setObjectName("dangerBtn")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(self.clear_all_shopping_items)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_clear)
        btn_layout.addWidget(btn_export)
        btn_layout.addStretch()

        header_label = QLabel("购物清单")
        header_label.setObjectName("pageTitle")
        shop_subtitle = QLabel("记录待购食材，支持导出 CSV")
        shop_subtitle.setObjectName("pageSubtitle")

        shop_card = QFrame()
        shop_card.setObjectName("contentCard")
        shop_card_layout = QVBoxLayout(shop_card)
        shop_card_layout.setContentsMargins(12, 12, 12, 12)
        shop_card_layout.addWidget(self.shop_table)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(header_label)
        layout.addWidget(shop_subtitle)
        layout.addLayout(btn_layout)
        layout.addWidget(shop_card, 1)
        self.shop_tab.setLayout(layout)
        self.addTab(self.shop_tab, "购物清单")
        self.refresh_shop_table()

    def show_add_shop_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加购物清单项目")
        dialog.setFixedSize(360, 260)
        name_edit = QLineEdit()
        quantity_edit = QLineEdit()
        unit_edit = QLineEdit()
        bought_box = QComboBox()
        bought_box.addItems(["否", "是"])
        btn_confirm = QPushButton("确认添加")
        btn_confirm.setObjectName("primaryBtn")
        btn_cancel = QPushButton("取消")
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(20, 20, 20, 10)
        form_layout.addRow("食材名称：", name_edit)
        form_layout.addRow("数量：", quantity_edit)
        form_layout.addRow("单位：", unit_edit)
        form_layout.addRow("已购买：", bought_box)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(20, 0, 20, 20)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_confirm)
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        dialog.setLayout(main_layout)
        def add_item():
            name = name_edit.text().strip()
            quantity = quantity_edit.text().strip()
            unit = unit_edit.text().strip()
            bought = bought_box.currentText() == "是"
            if not name or not quantity or not unit:
                QMessageBox.warning(dialog, "输入错误", "请填写完整购物项目。")
                return
            self.shopping_items.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "unit": unit,
                    "bought": bought,
                }
            )
            self.refresh_shop_table()
            dialog.accept()
        btn_confirm.clicked.connect(add_item)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def refresh_shop_table(self):
        self.shop_table.setRowCount(len(self.shopping_items))
        for row, item in enumerate(self.shopping_items):
            n_item = QTableWidgetItem(item["name"])
            q_item = QTableWidgetItem(str(item["quantity"]))
            u_item = QTableWidgetItem(item["unit"])
            for it in [n_item, q_item, u_item]:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.shop_table.setItem(row, 0, n_item)
            self.shop_table.setItem(row, 1, q_item)
            self.shop_table.setItem(row, 2, u_item)
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
            self.shop_table.setCellWidget(row, 3, cb_wrap)

    def _on_shop_item_checked(self, row: int) -> None:
        if row < 0 or row >= len(self.shopping_items):
            return
        cb = self.shop_table.cellWidget(row, 3)
        if cb is None:
            return
        checkbox = cb.findChild(QCheckBox)
        if checkbox is None:
            return
        self.shopping_items[row]["bought"] = checkbox.isChecked()

    def delete_selected_shop_items(self):
        rows = sorted({idx.row() for idx in self.shop_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "删除购物项目", "请先选择要删除的购物项。")
            return
        for row in rows:
            if 0 <= row < len(self.shopping_items):
                del self.shopping_items[row]
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
        self.knowledge_nav.addItems(list(self.knowledge_books.keys()))
        self.knowledge_nav.setFixedWidth(220)
        self.knowledge_nav.currentRowChanged.connect(self.update_knowledge_content)
        self.knowledge_content = QTextEdit()
        self.knowledge_content.setReadOnly(True)
        self.knowledge_content.setPlaceholderText("选择左侧分类，查看饮食知识。")

        self.knowledge_search_edit = QLineEdit()
        self.knowledge_search_edit.setPlaceholderText("输入食材名，如 鸡蛋 / 番茄 / 牛肉")
        self.knowledge_search_edit.returnPressed.connect(self.search_food_shelf_life)
        self.btn_knowledge_search = QPushButton("AI 查询保质期")
        self.btn_knowledge_search.setObjectName("primaryBtn")
        self.btn_knowledge_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_knowledge_search.clicked.connect(self.search_food_shelf_life)
        self.knowledge_search_status = QLabel("")
        self.knowledge_search_status.setObjectName("pageSubtitle")

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.knowledge_search_edit, 1)
        search_row.addWidget(self.btn_knowledge_search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.knowledge_nav)
        splitter.addWidget(self.knowledge_content)
        splitter.setSizes([220, 700])
        label = QLabel("饮食健康知识库")
        label.setObjectName("pageTitle")
        knowledge_subtitle = QLabel("食材保存、搭配与人群饮食建议")
        knowledge_subtitle.setObjectName("pageSubtitle")

        knowledge_card = QFrame()
        knowledge_card.setObjectName("contentCard")
        knowledge_card_layout = QVBoxLayout(knowledge_card)
        knowledge_card_layout.setContentsMargins(8, 8, 8, 8)
        knowledge_card_layout.addWidget(splitter)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(label)
        layout.addWidget(knowledge_subtitle)
        layout.addLayout(search_row)
        layout.addWidget(self.knowledge_search_status)
        layout.addWidget(knowledge_card, 1)
        self.knowledge_tab.setLayout(layout)
        self.addTab(self.knowledge_tab, "饮食知识")
        self.knowledge_nav.setCurrentRow(0)

    def update_knowledge_content(self, index):
        if index < 0:
            self.knowledge_content.clear()
            return
        key = self.knowledge_nav.item(index).text()
        self.knowledge_content.setHtml(
            f"<h3 style='color:#0d9488; margin-top:0;'>{key}</h3>"
            f"<p style='line-height:1.8; color:#475569;'>{self.knowledge_books.get(key, '').replace(chr(10), '<br>')}</p>"
        )

    def search_food_shelf_life(self):
        food_name = self.knowledge_search_edit.text().strip()
        if not food_name:
            QMessageBox.information(self, "提示", "请输入要查询的食材名称。")
            return

        self.btn_knowledge_search.setEnabled(False)
        self.knowledge_search_status.setText("AI 正在查询，请稍候...")
        self.knowledge_content.setPlainText(f"正在查询「{food_name}」的保质期和保存建议...")

        def task():
            from fallback.llm import get_llm

            llm = get_llm()
            return llm.generate(
                self._build_shelf_life_prompt(food_name),
                system=(
                    "你是家庭食材保存顾问，回答要简洁、实用、适合家庭冰箱管理。"
                    "如果不同品牌、包装或保存环境会影响保质期，请明确提醒。"
                ),
                max_tokens=512,
            )

        worker = Worker(task)
        worker.signals.result.connect(
            lambda text, name=food_name: self._on_shelf_life_ready(name, text)
        )
        worker.signals.error.connect(self._on_shelf_life_error)
        worker.signals.finished.connect(
            lambda: self.btn_knowledge_search.setEnabled(True)
        )
        self.thread_pool.start(worker)

    @staticmethod
    def _build_shelf_life_prompt(food_name: str) -> str:
        return (
            f"请查询食材「{food_name}」的家庭保存与保质期建议。"
            "请按以下结构回答：\n"
            "1. 常温、冷藏、冷冻的大致保质期；\n"
            "2. 最推荐的保存方式；\n"
            "3. 变质/不宜食用的判断方法；\n"
            "4. 家庭使用注意事项。\n"
            "回答要用中文，简洁但具体。"
        )

    def _on_shelf_life_ready(self, food_name: str, text: str):
        self.knowledge_search_status.setText("查询完成")
        self.knowledge_content.setHtml(
            f"<h3 style='color:#0d9488; margin-top:0;'>「{self._escape_html(food_name)}」保质期查询</h3>"
            f"<pre style='white-space:pre-wrap; font-family:Microsoft YaHei, sans-serif;"
            f" line-height:1.7; color:#475569;'>{self._escape_html(text)}</pre>"
            "<p style='color:#94a3b8; font-size:12px;'>提示：AI 回答仅供家庭参考，请以包装标识和实际气味、颜色、质地为准。</p>"
        )

    def _on_shelf_life_error(self, message: str):
        self.knowledge_search_status.setText("查询失败")
        self.knowledge_content.setPlainText(
            "AI 查询失败："
            f"{message}\n\n"
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

    def _refresh_llm_status_label(self) -> None:
        if not hasattr(self, "llm_status_label"):
            return
        try:
            from services.recipe_service import get_recipe_service

            status = get_recipe_service().llm_status()
            engine = status.get("engine", "none")
            labels = {"local": "本地 Qwen", "cloud": "云端 DeepSeek", "none": "未就绪"}
            hint = status.get("hint", "")
            text = f"当前：{labels.get(engine, engine)}"
            if hint:
                text += f"（{hint}）"
            self.llm_status_label.setText(text)
        except Exception as e:
            self.llm_status_label.setText(f"状态未知：{e}")

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