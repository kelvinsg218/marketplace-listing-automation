"""Design tokens and the application stylesheet.

All colours, radii and type sizes come from here; widgets reference them by
objectName / dynamic properties, never with inline hex values.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from mla.config.paths import resource_path
from mla.core.enums import (
    CatalogStatus, ConnectionStatus, ImportAction, ImportStatus, ItemStatus, ListingStatus, Verification,
)


class T:
    # layers: canvas < sidebar < surface < raised
    canvas = "#0C0B10"
    sidebar = "#111016"
    surface = "#16151C"
    raised = "#1E1C26"
    raised_hi = "#282532"
    line = "#2A2733"
    line_strong = "#3B3747"
    # text
    text = "#EDEAF3"
    text_2 = "#A7A1B3"
    text_3 = "#6F6A7B"
    # brand
    violet = "#7B5CFF"
    violet_hi = "#9A82FF"
    violet_lo = "#6546E6"
    violet_wash = "#221B3B"
    violet_text = "#CBBFFF"
    # semantic
    success = "#3DD68C"
    success_wash = "#11281E"
    warning = "#E8A93C"
    warning_wash = "#2C2211"
    danger = "#F0645A"
    danger_wash = "#2D1514"
    # type
    display_family = "Manrope"
    body_family = "Segoe UI Variable Text"
    # radii: hierarchy, not one radius everywhere
    r_panel = 10
    r_control = 6


# tone name -> (foreground, background)
TONES = {
    "neutral": (T.text_2, T.raised),
    "violet": (T.violet_text, T.violet_wash),
    "active": (T.text, T.violet_lo),
    "warning": (T.warning, T.warning_wash),
    "success": (T.success, T.success_wash),
    "danger": (T.danger, T.danger_wash),
    "muted": (T.text_3, T.surface),
}

STATUS_TONE = {
    CatalogStatus.DRAFT: "neutral", CatalogStatus.INCOMPLETE: "warning", CatalogStatus.READY: "violet",
    ListingStatus.DRAFT: "neutral", ListingStatus.INCOMPLETE: "warning", ListingStatus.READY: "violet",
    ListingStatus.QUEUED: "violet", ListingStatus.RUNNING: "active",
    ListingStatus.AWAITING_REVIEW: "warning", ListingStatus.PUBLISHED: "success",
    ListingStatus.FAILED: "danger", ListingStatus.CANCELLED: "muted",
    ListingStatus.APPROVED: "active", ListingStatus.NEEDS_ATTENTION: "danger",
    ItemStatus.QUEUED: "violet", ItemStatus.RUNNING: "active", ItemStatus.AWAITING_REVIEW: "warning",
    ItemStatus.PUBLISHED: "success", ItemStatus.FAILED: "danger", ItemStatus.CANCELLED: "muted",
    ItemStatus.SKIPPED: "muted", ItemStatus.NEEDS_ATTENTION: "danger",
    ImportAction.CREATE: "violet", ImportAction.UPDATE: "active", ImportAction.UNCHANGED: "muted",
    ImportAction.SKIP: "muted", ImportAction.ERROR: "danger", ImportAction.REVIEW: "warning",
    ImportStatus.PLANNING: "active", ImportStatus.PLANNED: "warning", ImportStatus.COMMITTING: "active",
    ImportStatus.COMPLETED: "success", ImportStatus.DISCARDED: "muted",
    Verification.CONFIRMED: "success", Verification.UNVERIFIED: "warning", Verification.REJECTED: "muted",
    ConnectionStatus.UNKNOWN: "neutral", ConnectionStatus.CONNECTED: "success",
    ConnectionStatus.LOGIN_REQUIRED: "warning", ConnectionStatus.EXPIRED: "warning",
}


def tone_for(status) -> tuple[str, str]:
    return TONES[STATUS_TONE.get(status, "neutral")]


def display_font(px: int, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    font = QFont(T.display_family)
    font.setPixelSize(px)
    font.setWeight(weight)
    return font


def load_fonts() -> None:
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "Manrope.ttf")))
    families = set(QFontDatabase.families())
    if T.body_family not in families:
        T.body_family = "Segoe UI" if "Segoe UI" in families else QFont().defaultFamily()
    if T.display_family not in families:
        T.display_family = T.body_family


def stylesheet() -> str:
    return f"""
* {{ font-family: "{T.body_family}"; font-size: 13px; color: {T.text}; }}
QMainWindow, QDialog, #canvas {{ background: {T.canvas}; }}
QToolTip {{ background: {T.raised_hi}; color: {T.text}; border: 1px solid {T.line_strong}; padding: 6px 8px; }}

/* sidebar */
#sidebar {{ background: {T.sidebar}; border-right: 1px solid {T.line}; }}
#brand {{ font-family: "{T.display_family}"; font-size: 20px; font-weight: 800; color: {T.text}; }}
#brandSub {{ color: {T.text_3}; font-size: 11px; }}
#navButton {{
    text-align: left; padding: 9px 12px; border: none; border-left: 2px solid transparent;
    border-radius: 0; color: {T.text_2}; background: transparent; font-size: 13px;
}}
#navButton:hover {{ color: {T.text}; background: {T.surface}; }}
#navButton:checked {{ color: {T.text}; background: {T.violet_wash}; border-left: 2px solid {T.violet}; }}
#navButton:focus {{ outline: none; }}
#sidebarFoot {{ color: {T.text_3}; font-size: 11px; }}
#companyButton {{
    text-align: left; padding: 7px 26px 7px 10px; border: 1px solid {T.line}; border-radius: {T.r_control}px;
    color: {T.text}; background: {T.surface}; font-size: 12px;
}}
#companyButton:hover {{ border-color: {T.line_strong}; background: {T.raised}; }}
#companyButton::menu-indicator {{
    image: url(__CHEVRON__); subcontrol-origin: padding; subcontrol-position: right center;
    right: 8px; width: 12px; height: 12px;
}}

/* page header */
#pageTitle {{ font-family: "{T.display_family}"; font-size: 24px; font-weight: 700; }}
#pageSubtitle {{ color: {T.text_2}; }}
#sectionTitle {{ font-family: "{T.display_family}"; font-size: 15px; font-weight: 700; }}
#hint, QLabel[role="hint"] {{ color: {T.text_3}; font-size: 12px; }}
QLabel[role="muted"] {{ color: {T.text_2}; }}
QLabel[role="metric"] {{ font-family: "{T.display_family}"; font-size: 28px; font-weight: 800; }}
QLabel[role="error"] {{ color: {T.danger}; }}

/* panels */
#panel {{ background: {T.surface}; border: 1px solid {T.line}; border-radius: {T.r_panel}px; }}
#panelFlat {{ background: transparent; border: 1px solid {T.line}; border-radius: {T.r_panel}px; }}
#divider {{ background: {T.line}; max-height: 1px; min-height: 1px; border: none; }}

/* buttons */
QPushButton {{
    background: {T.raised}; border: 1px solid {T.line_strong}; border-radius: {T.r_control}px;
    padding: 7px 14px; color: {T.text}; min-height: 18px;
}}
QPushButton:hover {{ background: {T.raised_hi}; }}
QPushButton:pressed {{ background: {T.surface}; }}
QPushButton:focus {{ border: 1px solid {T.violet_hi}; }}
QPushButton:disabled {{ color: {T.text_3}; background: {T.surface}; border-color: {T.line}; }}
QPushButton[variant="primary"] {{ background: {T.violet}; border: 1px solid {T.violet}; color: #FFFFFF; font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {T.violet_hi}; border-color: {T.violet_hi}; }}
QPushButton[variant="primary"]:pressed {{ background: {T.violet_lo}; }}
QPushButton[variant="primary"]:focus {{ border: 1px solid #FFFFFF; }}
QPushButton[variant="primary"]:disabled {{ background: {T.violet_wash}; border-color: {T.violet_wash}; color: {T.text_3}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {T.text_2}; }}
QPushButton[variant="ghost"]:hover {{ background: {T.raised}; color: {T.text}; }}
QPushButton[variant="danger"] {{ background: transparent; border: 1px solid {T.danger_wash}; color: {T.danger}; }}
QPushButton[variant="danger"]:hover {{ background: {T.danger_wash}; }}
QPushButton[variant="success"] {{ background: {T.success}; border: 1px solid {T.success}; color: #06140D; font-weight: 600; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

/* inputs */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {T.canvas}; border: 1px solid {T.line_strong}; border-radius: {T.r_control}px;
    padding: 6px 8px; selection-background-color: {T.violet_lo}; selection-color: #FFFFFF;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {T.violet};
}}
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{ border: 1px solid {T.danger}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {T.text_3}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {T.raised}; border: 1px solid {T.line_strong}; selection-background-color: {T.violet_wash};
    selection-color: {T.text}; outline: none; padding: 4px;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {T.line_strong}; background: {T.canvas}; }}
QCheckBox::indicator:checked {{ background: {T.violet}; border-color: {T.violet}; image: url(__CHECK__); }}
QCheckBox::indicator:focus {{ border-color: {T.violet_hi}; }}

/* tables and lists */
QTableView, QListView, QListWidget, QTreeView {{
    background: {T.surface}; border: 1px solid {T.line}; border-radius: {T.r_panel}px;
    gridline-color: transparent; selection-background-color: {T.violet_wash}; selection-color: {T.text};
    alternate-background-color: {T.surface}; outline: none;
}}
QTableView::item, QListWidget::item {{ padding: 4px 8px; border-bottom: 1px solid {T.line}; }}
QTableView::item:selected, QListWidget::item:selected {{ background: {T.violet_wash}; }}
QListWidget::item:hover, QTableView::item:hover {{ background: {T.raised}; }}
QHeaderView::section {{
    background: {T.surface}; color: {T.text_3}; border: none; border-bottom: 1px solid {T.line};
    padding: 8px; font-size: 12px; font-weight: 600;
}}
QHeaderView::section:hover {{ color: {T.text_2}; }}
QTableCornerButton::section {{ background: {T.surface}; border: none; }}

/* tabs */
QTabWidget::pane {{ border: none; border-top: 1px solid {T.line}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {T.text_2}; padding: 9px 14px; border: none;
    border-bottom: 2px solid transparent; margin-right: 4px;
}}
QTabBar::tab:hover {{ color: {T.text}; }}
QTabBar::tab:selected {{ color: {T.text}; border-bottom: 2px solid {T.violet}; }}

/* scrollbars */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {T.line_strong}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {T.text_3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {T.line_strong}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; height: 0; width: 0; }}

/* misc */
QProgressBar {{ background: {T.raised}; border: none; border-radius: 3px; height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {T.violet}; border-radius: 3px; }}
QMenu {{ background: {T.raised}; border: 1px solid {T.line_strong}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {T.violet_wash}; }}
QMessageBox {{ background: {T.surface}; }}
#toast {{ background: {T.raised_hi}; border: 1px solid {T.line_strong}; border-radius: 8px; padding: 10px 14px; }}
QLabel[step="todo"] {{ color: {T.text_3}; padding: 6px 2px; border-bottom: 2px solid {T.line}; }}
QLabel[step="current"] {{ color: {T.text}; font-weight: 600; padding: 6px 2px; border-bottom: 2px solid {T.violet}; }}
QLabel[step="done"] {{ color: {T.violet_text}; padding: 6px 2px; border-bottom: 2px solid {T.violet_lo}; }}
QFrame#callout {{ background: {T.violet_wash}; border: 1px solid {T.violet_lo}; border-radius: {T.r_control}px; }}
QFrame#calloutWarn {{ background: {T.warning_wash}; border: 1px solid {T.warning}; border-radius: {T.r_control}px; }}
#dropZone {{ border: 1px dashed {T.line_strong}; border-radius: {T.r_panel}px; background: {T.canvas}; }}
#dropZone[active="true"] {{ border: 1px dashed {T.violet}; background: {T.violet_wash}; }}
"""


def apply_theme(app: QApplication) -> None:
    load_fonts()
    app.setStyle("Fusion")
    body = QFont(T.body_family)
    body.setPixelSize(13)
    app.setFont(body)
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, T.canvas), (QPalette.ColorRole.Base, T.canvas),
        (QPalette.ColorRole.AlternateBase, T.surface), (QPalette.ColorRole.Text, T.text),
        (QPalette.ColorRole.WindowText, T.text), (QPalette.ColorRole.Button, T.raised),
        (QPalette.ColorRole.ButtonText, T.text), (QPalette.ColorRole.Highlight, T.violet_lo),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"), (QPalette.ColorRole.PlaceholderText, T.text_3),
        (QPalette.ColorRole.ToolTipBase, T.raised_hi), (QPalette.ColorRole.ToolTipText, T.text),
        (QPalette.ColorRole.Link, T.violet_hi),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    from mla.ui.icons import icon_file
    check = icon_file("check", "#FFFFFF", 14).replace("\\", "/")
    chevron = icon_file("chevron-down", T.text_3, 12).replace("\\", "/")
    app.setStyleSheet(stylesheet().replace("__CHECK__", check).replace("__CHEVRON__", chevron))
