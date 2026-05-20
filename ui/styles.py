# 文件路径：ui/styles.py
# PyQt6 美观样式表 - 现代绿色主题

GLOBAL_STYLE = """
/* ============ 全局基础设置 ============ */
* {
    margin: 0px;
    padding: 0px;
    box-sizing: border-box;
}

QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px;
    color: #2f3a3a;
    background-color: #f3f7f3;
}

QMainWindow, QDialog, QWidget {
    background-color: #f3f7f3;
}

QTabWidget#mainWindow {
    background-color: #f3f7f3;
    border: none;
}

QTabWidget::pane {
    border: none;
    background-color: #fcfdfc;
    border-radius: 18px;
    padding: 18px;
}

QTabBar {
    background-color: transparent;
    qproperty-drawBase: 0;
}

QTabBar::tab {
    background-color: #eef5ef;
    color: #4a5a52;
    border: 1px solid #d8e4da;
    border-bottom: none;
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
    padding: 10px 22px;
    margin-right: 8px;
    min-width: 120px;
}

QTabBar::tab:selected {
    background-color: #27ae60;
    color: #ffffff;
    font-weight: bold;
    border-color: #21a24f;
}

QTabBar::tab:hover {
    background-color: #d8eed9;
}

/* ============ 输入控件 ============ */
QLineEdit, QDateEdit, QComboBox {
    border: 1px solid #d8e4da;
    border-radius: 8px;
    padding: 10px 12px;
    background-color: #ffffff;
    color: #2f3a3a;
}

QLineEdit:focus, QDateEdit:focus, QComboBox:focus {
    border: 2px solid #27ae60;
    padding: 9px 11px;
    background-color: #fcfcfc;
}

QComboBox::drop-down {
    border: none;
    background: transparent;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    width: 0px;
}

QComboBox QAbstractItemView {
    border: 1px solid #d8e4da;
    background-color: #ffffff;
    selection-background-color: #d8eed9;
    color: #2f3a3a;
}

/* ============ 按钮 ============ */
QPushButton {
    background-color: #ffffff;
    color: #2f3a3a;
    border: 1px solid #d8e4da;
    border-radius: 10px;
    padding: 10px 18px;
    font-weight: 600;
    min-height: 34px;
}

QPushButton:hover {
    background-color: #f5f9f4;
    border-color: #bcd8b8;
}

QPushButton:pressed {
    background-color: #e9f4e8;
}

QPushButton#primaryBtn {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #4dc986, stop:1 #27ae60);
    color: #ffffff;
    border: none;
}

QPushButton#primaryBtn:hover {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #60d492, stop:1 #2ecc71);
}

QPushButton#primaryBtn:pressed {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #3bb571, stop:1 #229954);
}

QPushButton#dangerBtn {
    background-color: #fff5f5;
    color: #c0392b;
    border: 1px solid #f1c0be;
}

QPushButton#dangerBtn:hover {
    background-color: #fce9e8;
    border-color: #e59a98;
}

QPushButton#secondaryBtn {
    background-color: #ffffff;
    color: #27ae60;
    border: 1px solid #27ae60;
}

QPushButton#secondaryBtn:hover {
    background-color: #27ae60;
    border-color: #1f8f4b;
    color: #1f5a34;
}

/* ============ 表格 ============ */
QTableWidget {
    border: 1px solid #e3ece4;
    background-color: #ffffff;
    gridline-color: #eef3ed;
    border-radius: 14px;
}

QTableWidget::item {
    padding: 10px 8px;
    border-bottom: 1px solid #f0f5f0;
}

QTableWidget::item:selected {
    background-color: #d8eed9;
    color: #2f3a3a;
}

QTableWidget::item:hover {
    background-color: #f7faf7;
}

QHeaderView::section {
    background-color: #f3f8f4;
    color: #2f3a3a;
    padding: 12px 10px;
    border: none;
    border-bottom: 2px solid #27ae60;
    font-weight: bold;
}

QTableWidget::item:hover {
    background-color: #f7faf7;
}

QHeaderView {
    background-color: #f3f8f4;
}

QHeaderView::section {
    background-color: #f3f8f4;
    color: #2f3a3a;
    padding: 10px;
    border: none;
    border-bottom: 2px solid #27ae60;
    font-weight: bold;
}

/* ============ 标签页 ============ */
QTabWidget::pane {
    background-color: #fcfdfc;
}

QTabBar::tab {
    min-height: 34px;
}

/* ============ 标签 ============ */
QLabel {
    color: #2f3a3a;
    background-color: transparent;
}

/* ============ 分组框 ============ */
QGroupBox {
    border: 1px solid #dbe6da;
    border-radius: 14px;
    margin-top: 16px;
    padding: 18px;
    color: #2f3a3a;
    background-color: #fbfdfb;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: #23965a;
    font-weight: bold;
}

/* ============ 文本框和列表 ============ */
QTextEdit {
    border: 1px solid #d8e4da;
    border-radius: 10px;
    background-color: #ffffff;
    color: #2f3a3a;
    padding: 10px;
}

QTextEdit:focus {
    border: 2px solid #27ae60;
    padding: 9px;
}

QListWidget {
    border: 1px solid #d8e4da;
    border-radius: 10px;
    background-color: #ffffff;
    color: #2f3a3a;
}

QListWidget::item {
    padding: 10px 12px;
    border: none;
}

QListWidget::item:selected {
    background-color: #d8eed9;
    color: #27ae60;
    font-weight: bold;
}

QListWidget::item:hover {
    background-color: #f7faf7;
}

/* ============ 对话框 ============ */
QDialog {
    background-color: #ffffff;
}

QMessageBox {
    background-color: #ffffff;
}

/* ============ 滚动条 ============ */
QScrollBar:vertical {
    border: none;
    background: #f3f7f3;
    width: 10px;
}

QScrollBar::handle:vertical {
    background: #cfd9d4;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #a9bcb3;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}

QScrollBar:horizontal {
    border: none;
    background: #f3f7f3;
    height: 10px;
}

QScrollBar::handle:horizontal {
    background: #cfd9d4;
    border-radius: 5px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background: #a9bcb3;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    border: none;
    background: none;
}

/* ============ 分割线 ============ */
QSplitter::handle {
    background-color: #e4ece7;
}

QSplitter::handle:hover {
    background-color: #d3e1d7;
}
"""