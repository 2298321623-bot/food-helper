from PyQt6.QtWidgets import *
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, Qt, QDate, QThreadPool
from PyQt6.QtGui import QFont, QColor # 1. 必须引入 QColor
import csv
from datetime import datetime

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
        self.thread_pool = QThreadPool.globalInstance()

    def init_window(self):
        self.setObjectName("mainWindow")
        self.setWindowTitle("家庭食材管理与智能食谱助手")
        self.setFixedSize(1050, 700) # 黄金展现尺寸

    def init_ingredient_tab(self):
        self.ingredient_tab = QWidget()
        self.ingredient_table = QTableWidget()
        self.ingredient_table.setColumnCount(6)
        self.ingredient_table.setHorizontalHeaderLabels(["食材名称", "数量/单位", "保质期", "食材分类", "存放位置", "操作"])
        
        # 2. 表格高级打磨
        self.ingredient_table.setShowGrid(False)
        self.ingredient_table.setAlternatingRowColors(True)
        self.ingredient_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ingredient_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows) # 允许整行选中
        self.ingredient_table.verticalHeader().setDefaultSectionSize(44) # 设置宽裕的现代行高
        self.ingredient_table.verticalHeader().setVisible(False) # 隐藏极其刺眼的左侧原生数字行号
        header = self.ingredient_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.btn_add_ingredient = QPushButton("➕ 添加食材")
        self.btn_add_ingredient.setObjectName("primaryBtn") # 赋予主操作绿色
        self.btn_add_ingredient.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_ingredient.clicked.connect(self.show_add_ingredient_dialog)
        
        self.btn_remove_ingredient = QPushButton("🗑 删除选中")
        self.btn_remove_ingredient.setObjectName("dangerBtn") # 赋予危险操作淡红
        self.btn_remove_ingredient.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_ingredient.clicked.connect(self.remove_selected_ingredient)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_add_ingredient)
        btn_layout.addWidget(self.btn_remove_ingredient)
        btn_layout.addStretch()

        title_label = QLabel("✨ 食材管理中心")
        title_label.setStyleSheet("font-size:16px; font-weight:700; color:#1d6b43; margin-bottom:10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15) # 设置合理的内边距
        layout.addWidget(title_label)
        layout.addLayout(btn_layout)
        layout.addSpacing(8)
        layout.addWidget(self.ingredient_table)
        self.ingredient_tab.setLayout(layout)
        self.addTab(self.ingredient_tab, "食材管理")

        self.refresh_ingredient_table()

    def show_add_ingredient_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加食材入库")
        dialog.setFixedSize(380, 400)

        name_edit = QLineEdit()
        quantity_edit = QLineEdit()
        expiry_edit = QDateEdit()
        expiry_edit.setDisplayFormat("yyyy-MM-dd")
        expiry_edit.setDate(QDate.currentDate())
        expiry_edit.setCalendarPopup(True) # 开启高级感的日历弹出视图
        
        category_box = QComboBox()
        category_box.addItems(["蔬菜", "肉类", "水果", "调料", "主食", "水产", "蛋奶"])
        location_edit = QLineEdit()

        btn_confirm = QPushButton("确认添加")
        btn_confirm.setObjectName("primaryBtn")
        btn_cancel = QPushButton("取消")

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(25, 25, 25, 15)
        form_layout.addRow("食材名称：", name_edit)
        form_layout.addRow("数量/单位：", quantity_edit)
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
            quantity = quantity_edit.text().strip()
            expiry = expiry_edit.date().toPyDate()
            category = category_box.currentText()
            location = location_edit.text().strip()
            if not name or not quantity:
                QMessageBox.warning(dialog, "输入错误", "请填写食材名称和数量/单位。")
                return
            self.ingredients.append({
                "name": name,
                "quantity": quantity,
                "expiry": expiry,
                "category": category,
                "location": location
            })
            self.refresh_ingredient_table()
            dialog.accept()

        btn_confirm.clicked.connect(add_item)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def refresh_ingredient_table(self):
        self.ingredient_table.setRowCount(len(self.ingredients))
        now = datetime.now().date()
        for row, item in enumerate(self.ingredients):
            expiry = item["expiry"]
            days_left = (expiry - now).days
            
            # 3. 建立数据单元格并统一设置为【居中对齐】
            name_item = QTableWidgetItem(item["name"])
            quantity_item = QTableWidgetItem(item["quantity"])
            expiry_item = QTableWidgetItem(expiry.strftime("%Y-%m-%d"))
            category_item = QTableWidgetItem(item["category"])
            location_item = QTableWidgetItem(item["location"])
            
            for cell_item in [name_item, quantity_item, expiry_item, category_item, location_item]:
                cell_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 4. 表格内嵌按钮的缩放与居中修正（防止按钮撑满格子变形）
            delete_btn_container = QWidget()
            delete_btn_layout = QHBoxLayout()
            delete_btn = QPushButton("删除")
            delete_btn.setObjectName("dangerBtn")
            delete_btn.setFixedSize(80, 28) # 锁定按钮比例并保证内容完全显示
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.clicked.connect(lambda checked, r=row: self.delete_ingredient(r))
            delete_btn_layout.addWidget(delete_btn)
            delete_btn_container.setFixedWidth(100)
            delete_btn_layout.setContentsMargins(0, 0, 0, 0)
            delete_btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            delete_btn_container.setLayout(delete_btn_layout)

            # 5. 高级色彩体系（替换原生的刺眼正红和正黄）
            if days_left < 0:
                bg_color = QColor("#FADBD8") # 优雅莫兰迪淡粉红（过期）
                expiry_item.setToolTip("已过期")
            elif days_left <= 3:
                bg_color = QColor("#FCF3CF") # 柔和马卡龙暖浅黄（临近过期）
                expiry_item.setToolTip(f"剩余 {days_left} 天")
            else:
                bg_color = None

            for col, widget_item in enumerate([name_item, quantity_item, expiry_item, category_item, location_item]):
                if bg_color is not None:
                    widget_item.setBackground(bg_color)
                self.ingredient_table.setItem(row, col, widget_item)
                
            # 必须用 setCellWidget 装载包裹好的居中按钮容器
            self.ingredient_table.setCellWidget(row, 5, delete_btn_container)

        self.check_expiry_alert()

    # (delete_ingredient, remove_selected_ingredient, check_expiry_alert 保持原样不变...)
    def delete_ingredient(self, row):
        if 0 <= row < len(self.ingredients):
            del self.ingredients[row]
            self.refresh_ingredient_table()

    def remove_selected_ingredient(self):
        rows = sorted({idx.row() for idx in self.ingredient_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "删除食材", "请先选择要删除的行。")
            return
        for row in rows:
            if 0 <= row < len(self.ingredients):
                del self.ingredients[row]
        self.refresh_ingredient_table()

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

    def init_recipe_tab(self):
        self.recipe_tab = QWidget()
        self.mode_box = QComboBox()
        self.mode_box.addItems(["用现有食材做", "按需求做"])
        self.diet_box = QComboBox()
        self.diet_box.addItems(["家常菜", "减脂餐", "增肌餐", "素食", "控糖"])
        self.time_box = QComboBox()
        self.time_box.addItems(["15分钟内", "15-30分钟", "30分钟以上"])
        self.diff_box = QComboBox()
        self.diff_box.addItems(["简单", "中等", "困难"])

        btn_generate = QPushButton("🔍 生成智能食谱")
        btn_generate.setObjectName("primaryBtn") # 高亮绿
        btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_generate.clicked.connect(self.generate_recipe_list)

        self.btn_ai_recipe = QPushButton("✨ AI 生成详细步骤")
        self.btn_ai_recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_recipe.clicked.connect(self.start_ai_recipe_generation)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.addRow("生成模式：", self.mode_box)
        form_layout.addRow("饮食偏好：", self.diet_box)
        form_layout.addRow("烹饪时间：", self.time_box)
        form_layout.addRow("难度级别：", self.diff_box)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_generate)
        btn_row.addWidget(self.btn_ai_recipe)
        btn_row.addStretch()
        form_layout.addRow("", btn_row)

        group = QGroupBox("个性化食谱筛选")
        group.setLayout(form_layout)

        header_label = QLabel("🍽️ 智能食谱助手为您推荐更健康的做法")
        header_label.setStyleSheet("font-size:14px; color:#3a5f47; margin-bottom:10px;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.recipe_list = QListWidget()
        self.recipe_list.itemClicked.connect(self.show_recipe_detail)

        self.recipe_detail = QTextEdit()
        self.recipe_detail.setReadOnly(True)
        self.recipe_detail.setPlaceholderText("💡 请在左侧选择感兴趣的食谱查看详细做法、配料用量及烹饪技巧说明。")

        recipe_layout = QHBoxLayout()
        recipe_layout.addWidget(self.recipe_list, 2)
        recipe_layout.addWidget(self.recipe_detail, 3)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.addWidget(header_label)
        layout.addWidget(group)
        layout.addSpacing(12)
        tip_label = QLabel("📋 为您精准推荐的健康菜谱：")
        tip_label.setStyleSheet("font-weight:bold; color:#2f3a3a;")
        layout.addWidget(tip_label)
        layout.addLayout(recipe_layout)
        self.recipe_tab.setLayout(layout)
        self.addTab(self.recipe_tab, "智能食谱")
        
        # 初始化清空默认提示
        self.recipe_list.clear()

    # (generate_recipe_list, show_recipe_detail 保持原样不变...)
    def generate_recipe_list(self):
        mode = self.mode_box.currentText()
        diet = self.diet_box.currentText()
        time = self.time_box.currentText()
        diff = self.diff_box.currentText()
        ingredient_names = [item["name"] for item in self.ingredients]
        results = []

        try:
            from services.recipe_service import get_recipe_service

            svc = get_recipe_service()
            if mode == "用现有食材做":
                if not ingredient_names:
                    QMessageBox.information(
                        self, "提示", "请先在「食材管理」中添加冰箱食材。"
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
                for recipe in self.recipes:
                    if set(recipe["ingredients"]).issubset(ingredient_set):
                        results.append(recipe)
            else:
                results = [
                    r
                    for r in self.recipes
                    if diet in r["tags"] and r["time"] == time and r["diff"] == diff
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
        else:
            self.recipe_list.addItem("⚠️ 未找到匹配食谱，请调整食材或筛选条件")
            self.recipe_detail.clear()

    def start_ai_recipe_generation(self):
        ingredient_names = [item["name"] for item in self.ingredients]
        if not ingredient_names:
            QMessageBox.information(self, "提示", "请先在「食材管理」中添加食材。")
            return

        current = self.recipe_list.currentItem()
        recipe = current.data(Qt.ItemDataRole.UserRole) if current else None
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
        html = (
            "<h2 style='color:#27ae60;'>✨ AI 生成菜谱</h2>"
            f"<pre style='white-space:pre-wrap; font-family:Microsoft YaHei, sans-serif;"
            f" line-height:1.7; color:#333;'>{self._escape_html(text)}</pre>"
        )
        self.recipe_detail.setHtml(html)

    def _on_ai_recipe_error(self, message):
        self.recipe_detail.setPlainText(f"生成失败：{message}\n\n请确认已下载本地模型或配置 DEEPSEEK_API_KEY。")

    @staticmethod
    def _escape_html(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def show_recipe_detail(self, item):
        recipe = item.data(Qt.ItemDataRole.UserRole)
        if recipe:
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
                f"<h2 style='color:#27ae60;'>🍳 {recipe['name']}</h2>"
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
        self.shop_table.horizontalHeader().setStretchLastSection(True)
        self.shop_table.setAlternatingRowColors(True)
        self.shop_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.shop_table.verticalHeader().setDefaultSectionSize(38)
        self.shop_table.verticalHeader().setVisible(False)

        btn_add = QPushButton("➕ 添加商品")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.show_add_shop_dialog)
        btn_delete = QPushButton("🗑 删除选中")
        btn_delete.setObjectName("dangerBtn")
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.clicked.connect(self.delete_selected_shop_items)
        btn_export = QPushButton("📤 导出购物清单")
        btn_export.setObjectName("primaryBtn")
        btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_export.clicked.connect(self.export_shopping_list)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_export)
        btn_layout.addStretch()

        header_label = QLabel("🛒 购物清单助手")
        header_label.setStyleSheet("font-size:16px; font-weight:700; color:#1d6b43; margin-bottom:10px;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.addWidget(header_label)
        layout.addLayout(btn_layout)
        layout.addSpacing(8)
        layout.addWidget(self.shop_table)
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
            self.shopping_items.append({"name": name, "quantity": quantity, "unit": unit, "bought": bought})
            self.refresh_shop_table()
            dialog.accept()
        btn_confirm.clicked.connect(add_item)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def refresh_shop_table(self):
        self.shop_table.setRowCount(len(self.shopping_items))
        for row, item in enumerate(self.shopping_items):
            n_item = QTableWidgetItem(item["name"])
            q_item = QTableWidgetItem(item["quantity"])
            u_item = QTableWidgetItem(item["unit"])
            b_item = QTableWidgetItem("是" if item["bought"] else "否")
            for it in [n_item, q_item, u_item, b_item]:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.shop_table.setItem(row, 0, n_item)
            self.shop_table.setItem(row, 1, q_item)
            self.shop_table.setItem(row, 2, u_item)
            self.shop_table.setItem(row, 3, b_item)

    def delete_selected_shop_items(self):
        rows = sorted({idx.row() for idx in self.shop_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "删除购物项目", "请先选择要删除的购物项。")
            return
        for row in rows:
            if 0 <= row < len(self.shopping_items):
                del self.shopping_items[row]
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
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.knowledge_nav)
        splitter.addWidget(self.knowledge_content)
        splitter.setSizes([220, 700])
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        label = QLabel("💡 饮食健康知识库导航")
        label.setStyleSheet("font-size:14px; font-weight:bold; color:#27ae60; margin-bottom:5px;")
        layout.addWidget(label)
        layout.addWidget(splitter)
        self.knowledge_tab.setLayout(layout)
        self.addTab(self.knowledge_tab, "饮食知识")
        self.knowledge_nav.setCurrentRow(0)

    def update_knowledge_content(self, index):
        if index < 0:
            self.knowledge_content.clear()
            return
        key = self.knowledge_nav.item(index).text()
        self.knowledge_content.setHtml(f"<h3 style='color:#27ae60; margin-top:0px;'>📘 {key}</h3><p style='line-height:1.8; color:#444444;'>{self.knowledge_books.get(key, '').replace(chr(10), '<br>')}</p>")