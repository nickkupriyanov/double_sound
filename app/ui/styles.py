"""Темы оформления интерфейса (светлая и тёмная)."""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

PALETTES = {
    "light": {
        "bg": "#F3F5F9",
        "panel": "#FFFFFF",
        "panel_alt": "#F7F9FC",
        "border": "#DDE3EC",
        "text": "#1C2536",
        "muted": "#6C788B",
        "accent": "#2F6FED",
        "accent_hover": "#245FD2",
        "accent_soft": "#E8EFFD",
        "danger": "#D64545",
        "danger_hover": "#BE3939",
        "danger_soft": "#FDECEC",
        "success": "#147A4B",
        "warning": "#B26A00",
        "selection": "#E4EDFD",
        "group": "#EEF3FB",
        "white": "#FFFFFF",
    },
    "dark": {
        "bg": "#14181F",
        "panel": "#1D232D",
        "panel_alt": "#232A36",
        "border": "#2E3847",
        "text": "#E7ECF4",
        "muted": "#93A0B3",
        "accent": "#5B8DEF",
        "accent_hover": "#6F9BF2",
        "accent_soft": "#25324A",
        "danger": "#EF6A6A",
        "danger_hover": "#F28282",
        "danger_soft": "#3D2226",
        "success": "#63D69B",
        "warning": "#E0A64B",
        "selection": "#2A374B",
        "group": "#232C3A",
        "white": "#FFFFFF",
    },
}

QSS = Template(
    """
* {
    outline: 0;
}
QMainWindow, QDialog {
    background: $bg;
    color: $text;
}
QWidget#Root {
    background: $bg;
}
QWidget {
    color: $text;
}
QFrame#TopBar {
    background: $panel;
    border-bottom: 1px solid $border;
}
QFrame#Card {
    background: $panel;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame#ComparePanel {
    background: $panel;
    border: 1px solid $border;
    border-radius: 12px;
}
QWidget#CompareContent {
    background: transparent;
}
QScrollArea {
    background: transparent;
    border: none;
}
QFrame#Divider {
    background: $border;
    max-height: 1px;
    min-height: 1px;
    border: none;
}
QLabel {
    background: transparent;
}
QLabel#AppTitle {
    font-size: 18px;
    font-weight: 700;
    color: $text;
}
QLabel#AppSubtitle {
    font-size: 11px;
    color: $muted;
}
QLabel#SectionTitle {
    font-size: 12px;
    font-weight: 700;
    color: $muted;
    letter-spacing: 0.6px;
}
QLabel#TitleLabel {
    font-size: 16px;
    font-weight: 700;
}
QLabel#ArtistLabel {
    font-size: 12px;
    color: $muted;
}
QLabel#Muted {
    color: $muted;
    font-size: 11px;
}
QLabel#StatLabel {
    color: $muted;
    font-size: 11px;
}
QLabel#SummaryLabel {
    font-size: 12px;
    font-weight: 600;
}
QLabel#InfoKey {
    color: $muted;
    font-size: 11px;
}
QLabel#InfoValue {
    font-size: 11px;
    font-weight: 600;
}
QLabel#Cover {
    background: $panel_alt;
    border: 1px solid $border;
    border-radius: 12px;
}
QLabel#PlaceholderIcon {
    background: $panel;
    color: $accent;
    border: 1px solid $border;
    border-radius: 38px;
    font-size: 34px;
}
QLabel#PlaceholderTitle {
    font-size: 16px;
    font-weight: 700;
}
QLabel#PlaceholderText {
    color: $muted;
    font-size: 12px;
}
QLabel#StageLabel {
    color: $muted;
    font-size: 11px;
}
QLabel#Badge {
    background: $accent_soft;
    color: $accent;
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 10px;
    font-weight: 700;
}
QLabel#MatchBadge {
    background: $accent_soft;
    color: $accent;
    border-radius: 9px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 700;
}
QPushButton {
    background: $panel;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 12px;
}
QPushButton:hover {
    background: $panel_alt;
    border-color: $muted;
}
QPushButton:pressed {
    background: $accent_soft;
}
QPushButton:disabled {
    color: $muted;
    background: $panel_alt;
    border-color: $border;
}
QPushButton#Primary {
    background: $accent;
    color: #FFFFFF;
    border: 1px solid $accent;
    font-weight: 700;
}
QPushButton#Primary:hover {
    background: $accent_hover;
    border-color: $accent_hover;
}
QPushButton#Primary:disabled {
    background: $border;
    border-color: $border;
    color: $muted;
}
QPushButton#Danger {
    background: $danger;
    color: #FFFFFF;
    border: 1px solid $danger;
    font-weight: 700;
}
QPushButton#Danger:hover {
    background: $danger_hover;
    border-color: $danger_hover;
}
QPushButton#Danger:disabled {
    background: $panel_alt;
    border-color: $border;
    color: $muted;
}
QPushButton#Ghost {
    background: transparent;
    border: none;
    color: $accent;
    padding: 5px 7px;
    font-weight: 600;
}
QPushButton#Ghost:hover {
    background: $accent_soft;
}
QPushButton#Ghost:disabled {
    color: $muted;
    background: transparent;
}
QPushButton#Small {
    padding: 5px 10px;
    font-size: 11px;
}
QPushButton#IconButton {
    padding: 5px 9px;
    font-size: 14px;
    font-weight: 700;
}
QLineEdit, QComboBox, QSpinBox {
    background: $panel;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 12px;
    selection-background-color: $accent;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: $accent;
}
QLineEdit#Search {
    background: $panel_alt;
    padding-left: 11px;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background: $panel;
    border: 1px solid $border;
    selection-background-color: $accent_soft;
    selection-color: $text;
    padding: 4px;
    outline: 0;
}
QListWidget#Folders {
    background: $panel_alt;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
    font-size: 11px;
}
QListWidget#Folders::item {
    padding: 7px 8px;
    border-radius: 6px;
    color: $text;
}
QListWidget#Folders::item:selected {
    background: $accent_soft;
    color: $text;
}
QTreeWidget#Results {
    background: $panel;
    border: none;
    alternate-background-color: $panel_alt;
    font-size: 12px;
}
QTreeWidget#Results::item {
    height: 30px;
    border-bottom: 1px solid $border;
}
QTreeWidget#Results::item:selected {
    background: $selection;
    color: $text;
}
QHeaderView::section {
    background: $panel_alt;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 8px 8px;
    font-size: 11px;
    font-weight: 700;
}
QTreeWidget QHeaderView::section:first {
    border-top-left-radius: 8px;
}
QSplitter::handle {
    background: transparent;
}
QSplitter::handle:horizontal {
    width: 10px;
}
QSplitter::handle:hover {
    background: $border;
}
QProgressBar {
    background: $border;
    border: none;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background: $accent;
    border-radius: 4px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: $border;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: $accent;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: $panel;
    border: 2px solid $accent;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: $border;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: $muted;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: $border;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
QStatusBar {
    background: $panel;
    border-top: 1px solid $border;
    color: $muted;
    font-size: 11px;
}
QStatusBar::item {
    border: none;
}
QMenu {
    background: $panel;
    border: 1px solid $border;
    padding: 5px;
}
QMenu::item {
    padding: 7px 22px 7px 12px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: $accent_soft;
}
QToolTip {
    background: $panel;
    color: $text;
    border: 1px solid $border;
    padding: 5px 7px;
}
QCheckBox {
    font-size: 12px;
    spacing: 8px;
}
QGroupBox {
    border: 1px solid $border;
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: $muted;
}
QMessageBox {
    background: $panel;
}
QMessageBox QLabel {
    color: $text;
}
"""
)


def apply_theme(app: QApplication, theme: str) -> None:
    palette_data = PALETTES.get(theme, PALETTES["light"])
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(palette_data["bg"]))
    palette.setColor(QPalette.WindowText, QColor(palette_data["text"]))
    palette.setColor(QPalette.Base, QColor(palette_data["panel"]))
    palette.setColor(QPalette.AlternateBase, QColor(palette_data["panel_alt"]))
    palette.setColor(QPalette.Text, QColor(palette_data["text"]))
    palette.setColor(QPalette.Button, QColor(palette_data["panel"]))
    palette.setColor(QPalette.ButtonText, QColor(palette_data["text"]))
    palette.setColor(QPalette.Highlight, QColor(palette_data["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipBase, QColor(palette_data["panel"]))
    palette.setColor(QPalette.ToolTipText, QColor(palette_data["text"]))
    palette.setColor(QPalette.PlaceholderText, QColor(palette_data["muted"]))
    palette.setColor(QPalette.Link, QColor(palette_data["accent"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(palette_data["muted"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(palette_data["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(QSS.substitute(**palette_data))


def theme_colors(theme: str) -> dict[str, str]:
    return PALETTES.get(theme, PALETTES["light"])
