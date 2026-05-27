# 文件路径：ui/styles.py
# 现代清爽主题 — 食材助手

GLOBAL_STYLE = """
/* ============ 全局 ============ */
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #1e293b;
    background-color: #f1f5f4;
}

QMainWindow, QDialog {
    background-color: #f1f5f4;
}

/* ============ 页面标题 ============ */
QLabel#pageTitle {
    font-size: 20px;
    font-weight: 700;
    color: #0f766e;
    padding: 0 0 4px 0;
    background: transparent;
}

QLabel#pageSubtitle {
    font-size: 13px;
    color: #64748b;
    padding-bottom: 8px;
    background: transparent;
}

QLabel#sectionLabel {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
    background: transparent;
}

/* ============ 内容卡片 ============ */
QFrame#contentCard {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}

QWidget#loginContainer {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}

QLabel#loginTitle {
    font-size: 22px;
    font-weight: 700;
    color: #0f766e;
    letter-spacing: 0.5px;
    background: transparent;
}

QLabel#loginSubtitle {
    font-size: 13px;
    color: #64748b;
    background: transparent;
}

QLabel#loginStatus {
    font-size: 13px;
    background: transparent;
    padding: 4px 8px;
}

QLabel#formLabel {
    font-size: 13px;
    font-weight: 600;
    color: #475569;
    background: transparent;
    margin-top: 4px;
}

/* ============ 标签页 ============ */
QTabWidget#mainWindow {
    background-color: #f1f5f4;
    border: none;
}

QTabWidget#mainWindow::pane {
    border: none;
    background-color: #f1f5f4;
    top: -1px;
    padding: 0;
}

QTabWidget#mainWindow::tab-bar {
    background-color: #f1f5f4;
    alignment: left;
}

QTabWidget::pane {
    border: none;
    background-color: #f1f5f4;
}

QTabBar {
    background-color: #f1f5f4;
    qproperty-drawBase: 0;
}

QTabBar::tab {
    background-color: #e8f0ee;
    color: #475569;
    border: none;
    border-radius: 10px;
    padding: 8px 20px;
    margin-right: 6px;
    margin-top: 4px;
    margin-bottom: 4px;
    min-width: 100px;
    min-height: 28px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #0d9488;
    color: #ffffff;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: #d1eae6;
    color: #0f766e;
}

/* ============ 输入控件 ============ */
QLineEdit, QDateEdit, QComboBox {
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 12px;
    background-color: #ffffff;
    color: #1e293b;
    min-height: 32px;
    selection-background-color: #99f6e4;
}

QLineEdit:hover, QDateEdit:hover, QComboBox:hover {
    border-color: #94a3b8;
}

QLineEdit:focus, QDateEdit:focus, QComboBox:focus {
    border: 2px solid #14b8a6;
    padding: 7px 11px;
}

QLineEdit::placeholder {
    color: #94a3b8;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}

QComboBox QAbstractItemView {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background-color: #ffffff;
    padding: 4px;
    selection-background-color: #ccfbf1;
    selection-color: #0f766e;
    outline: none;
}

QDateEdit::drop-down {
    border: none;
    width: 24px;
}

/* ============ 按钮 ============ */
QPushButton {
    background-color: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
    color: #0f172a;
}

QPushButton:pressed {
    background-color: #f1f5f9;
}

QPushButton:disabled {
    background-color: #f1f5f9;
    color: #94a3b8;
    border-color: #e2e8f0;
}

QPushButton#primaryBtn {
    background-color: #0d9488;
    color: #ffffff;
    border: none;
    font-weight: 600;
}

QPushButton#primaryBtn:hover {
    background-color: #14b8a6;
}

QPushButton#primaryBtn:pressed {
    background-color: #0f766e;
}

QPushButton#dangerBtn {
    background-color: #fff1f2;
    color: #be123c;
    border: 1px solid #fecdd3;
    font-weight: 500;
}

QPushButton#dangerBtn:hover {
    background-color: #ffe4e6;
    border-color: #fda4af;
}

QPushButton#secondaryBtn {
    background-color: transparent;
    color: #0d9488;
    border: 2px solid #0d9488;
    font-weight: 600;
}

QPushButton#secondaryBtn:hover {
    background-color: #0d9488;
    color: #ffffff;
}

QPushButton#compactBtn {
    padding: 4px 12px;
    min-height: 26px;
    font-size: 12px;
    border-radius: 6px;
}

/* 表格行内操作按钮（避免被行高裁切） */
QTableWidget QPushButton,
QPushButton#tableActionBtn {
    min-height: 0;
    max-height: 24px;
    padding: 2px 10px;
    font-size: 12px;
    border-radius: 6px;
}

/* ============ 表格 ============ */
QTableWidget {
    border: none;
    background-color: #ffffff;
    gridline-color: #f1f5f9;
    border-radius: 8px;
    alternate-background-color: #f8fafc;
    selection-background-color: #ccfbf1;
    selection-color: #134e4a;
}

QTableWidget::item {
    padding: 8px 6px;
    border: none;
}

QTableWidget::item:selected {
    background-color: #ccfbf1;
    color: #134e4a;
}

QHeaderView::section {
    background-color: #f8fafc;
    color: #475569;
    padding: 10px 8px;
    border: none;
    border-bottom: 2px solid #14b8a6;
    font-weight: 600;
    font-size: 12px;
}

QHeaderView::section:first {
    border-top-left-radius: 8px;
}

/* ============ 分组框 ============ */
QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    margin-top: 18px;
    padding: 20px 16px 12px 16px;
    background-color: #fafafa;
    font-weight: 600;
    color: #334155;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 8px;
    color: #0d9488;
    font-weight: 600;
    font-size: 13px;
}

/* ============ 文本与列表 ============ */
QTextEdit {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background-color: #ffffff;
    color: #334155;
    padding: 12px;
    line-height: 1.5;
}

QTextEdit:focus {
    border: 2px solid #14b8a6;
    padding: 11px;
}

QListWidget {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background-color: #ffffff;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 10px 14px;
    border-radius: 6px;
    margin: 2px 4px;
}

QListWidget::item:selected {
    background-color: #ccfbf1;
    color: #0f766e;
    font-weight: 600;
}

QListWidget::item:hover {
    background-color: #f0fdfa;
}

/* ============ 表单布局 ============ */
QFormLayout QLabel {
    color: #475569;
    font-weight: 500;
}

/* ============ 对话框与消息框 ============ */
QDialog {
    background-color: #ffffff;
}

QMessageBox {
    background-color: #ffffff;
}

/* ============ 滚动条 ============ */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    border: none;
    background: none;
}

QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 4px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
    background: none;
}

/* ============ 分割条 ============ */
QSplitter::handle {
    background-color: #e2e8f0;
    width: 2px;
    margin: 8px 4px;
}

QSplitter::handle:hover {
    background-color: #14b8a6;
}
"""
