# 文件路径：ui/styles.py
# 现代清爽主题 — 食材助手（refresh 版）

GLOBAL_STYLE = """
/* ============ 全局 ============ */
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
    color: #1f2937;
    background-color: #f4f7f6;
}

QMainWindow, QDialog {
    background-color: #f4f7f6;
}

/* ============ 页面标题 ============ */
QLabel#pageTitle {
    font-size: 22px;
    font-weight: 700;
    color: #0f766e;
    padding: 0;
    background: transparent;
}

QLabel#pageSubtitle {
    font-size: 13px;
    color: #64748b;
    background: transparent;
}

QLabel#sectionLabel {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
    background: transparent;
    padding: 2px 0;
}

QLabel#statusChip {
    background-color: #ecfeff;
    color: #0f766e;
    border: 1px solid #99f6e4;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#statusChipMuted {
    background-color: #f1f5f9;
    color: #64748b;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
}

/* ============ 卡片 ============ */
QFrame#contentCard, QFrame#toolbarCard {
    background-color: #ffffff;
    border: 1px solid #e5eaef;
    border-radius: 14px;
}

QFrame#toolbarCard {
    background-color: #ffffff;
}

QWidget#loginContainer {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
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
QTabWidget#mainWindow::pane {
    border: none;
    background-color: #f4f7f6;
    top: -1px;
}

QTabWidget::pane {
    border: none;
    background-color: #f4f7f6;
}

QTabBar {
    background-color: transparent;
    qproperty-drawBase: 0;
}

QTabBar::tab {
    background-color: transparent;
    color: #64748b;
    border: none;
    border-radius: 10px;
    padding: 9px 22px;
    margin: 6px 4px 4px 4px;
    min-width: 96px;
    min-height: 26px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #0d9488;
    color: #ffffff;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: #e2efec;
    color: #0f766e;
}

/* ============ 输入控件 ============ */
QLineEdit, QDateEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    border: 1px solid #d6dde5;
    border-radius: 8px;
    padding: 7px 12px;
    background-color: #ffffff;
    color: #1f2937;
    min-height: 30px;
    selection-background-color: #99f6e4;
}

QLineEdit:hover, QDateEdit:hover, QComboBox:hover,
QDoubleSpinBox:hover, QSpinBox:hover {
    border-color: #94a3b8;
}

QLineEdit:focus, QDateEdit:focus, QComboBox:focus,
QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #14b8a6;
    background-color: #ffffff;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
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

QDateEdit::drop-down { border: none; width: 22px; }

/* ============ 按钮 ============ */
QPushButton {
    background-color: #ffffff;
    color: #334155;
    border: 1px solid #d6dde5;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 500;
    min-height: 30px;
}

QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
    color: #0f172a;
}

QPushButton:pressed {
    background-color: #eef2f6;
}

QPushButton:disabled {
    background-color: #f1f5f9;
    color: #94a3b8;
    border-color: #e2e8f0;
}

QPushButton#primaryBtn {
    background-color: #0d9488;
    color: #ffffff;
    border: 1px solid #0d9488;
    font-weight: 600;
}
QPushButton#primaryBtn:hover  { background-color: #14b8a6; border-color: #14b8a6; }
QPushButton#primaryBtn:pressed{ background-color: #0f766e; border-color: #0f766e; }
QPushButton#primaryBtn:disabled {
    background-color: #cbd5e1; color: #ffffff; border-color: #cbd5e1;
}

QPushButton#dangerBtn {
    background-color: #fff1f2;
    color: #be123c;
    border: 1px solid #fecdd3;
    font-weight: 500;
}
QPushButton#dangerBtn:hover { background-color: #ffe4e6; border-color: #fda4af; }

QPushButton#secondaryBtn {
    background-color: #ffffff;
    color: #0d9488;
    border: 1px solid #0d9488;
    font-weight: 600;
}
QPushButton#secondaryBtn:hover { background-color: #ccfbf1; }
QPushButton#secondaryBtn:disabled {
    color: #94a3b8; border-color: #cbd5e1; background-color: #f1f5f9;
}

QPushButton#ghostBtn {
    background-color: transparent;
    color: #475569;
    border: 1px solid transparent;
    font-weight: 500;
}
QPushButton#ghostBtn:hover { background-color: #eef2f6; color: #0f172a; }

QPushButton#compactBtn {
    padding: 4px 12px;
    min-height: 26px;
    font-size: 12px;
    border-radius: 6px;
}

/* 表格行内操作按钮 */
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
    border-radius: 10px;
    alternate-background-color: #f8fafc;
    selection-background-color: #ccfbf1;
    selection-color: #134e4a;
}

QTableWidget::item { padding: 8px 6px; border: none; }
QTableWidget::item:selected { background-color: #ccfbf1; color: #134e4a; }

QHeaderView::section {
    background-color: #f8fafc;
    color: #475569;
    padding: 10px 8px;
    border: none;
    border-bottom: 2px solid #14b8a6;
    font-weight: 600;
    font-size: 12px;
}

/* ============ 分组框 ============ */
QGroupBox {
    border: 1px solid #e5eaef;
    border-radius: 12px;
    margin-top: 16px;
    padding: 16px 14px 12px 14px;
    background-color: #ffffff;
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
    background-color: #f4f7f6;
}

/* ============ 文本与列表 ============ */
QTextEdit {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background-color: #ffffff;
    color: #334155;
    padding: 12px;
}

QTextEdit:focus { border: 1px solid #14b8a6; }

QListWidget {
    border: 1px solid #e5eaef;
    border-radius: 10px;
    background-color: #ffffff;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 9px 12px;
    border-radius: 6px;
    margin: 2px 4px;
}

QListWidget::item:selected {
    background-color: #ccfbf1;
    color: #0f766e;
    font-weight: 600;
}

QListWidget::item:hover { background-color: #f0fdfa; }

/* ============ 表单 ============ */
QFormLayout QLabel { color: #475569; font-weight: 500; }

/* ============ 对话框 ============ */
QDialog { background-color: #ffffff; }
QMessageBox { background-color: #ffffff; }

/* ============ 复选框 ============ */
QCheckBox { spacing: 6px; color: #334155; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:hover { border-color: #14b8a6; }
QCheckBox::indicator:checked {
    background: #0d9488;
    border-color: #0d9488;
    image: none;
}

/* ============ 滚动条 ============ */
QScrollBar:vertical {
    border: none; background: transparent;
    width: 10px; margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #94a3b8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0; border: none; background: none;
}

QScrollBar:horizontal {
    border: none; background: transparent;
    height: 10px; margin: 2px 4px;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1; border-radius: 5px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #94a3b8; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0; border: none; background: none;
}

/* ============ 分割条 ============ */
QSplitter::handle {
    background-color: transparent;
    width: 6px;
}
QSplitter::handle:hover { background-color: #ccfbf1; }
"""
