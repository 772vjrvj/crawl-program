# launcher/ui/style/style.py
from __future__ import annotations
from PySide6.QtGui import QColor
# =========================
# === 신규 === Style tokens
# =========================
BTN_PRIMARY = "#2F80ED"
BTN_SUCCESS = "#27AE60"
BTN_DANGER = "#EB5757"
BTN_GRAY = "#BDBDBD"

TEXT_MAIN = "#333333"
TEXT_SUB = "#666666"
BORDER_DISABLED = "#E0E0E0"
BG_WHITE = "#ffffff"


# =========================
# === 신규 === Base styles
# =========================
def main_style(color: str) -> str:
    return f"""
        border-radius: 5px;
        border: 1px solid {color};
        padding: 1px 12px;
        font-weight: 500;
        font-size: 12.5px;
        color: {TEXT_MAIN};
        background-color: #ffffff;
        min-height: 30px;
    """


def disabled_style() -> str:
    return f"""
        border-radius: 5px;
        border: 1px solid {BORDER_DISABLED};
        padding: 5px 12px;
        font-weight: 500;
        font-size: 12.5px;
        color: #9e9e9e;
        background-color: #f5f5f5;
        min-height: 30px;
    """


# =========================
# === 신규 === Button stylesheet
# =========================

def _rgba_with_alpha(hex_color: str, alpha: float) -> str:
    """
    hex → rgba 문자열 변환
    alpha: 0.0 ~ 1.0
    """
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def btn_style(color: str) -> str:
    hover_bg = _rgba_with_alpha(color, 0.2)  # === 신규 === 20% 투명도

    return (
            "QPushButton {"
            + main_style(color)
            + "}"
            + f"""
        QPushButton:hover {{
            background-color: {hover_bg};
        }}
        QPushButton:pressed {{
            padding-top: 11px;
            padding-bottom: 9px;
        }}
        QPushButton:disabled {{
            {disabled_style()}
        }}
        """
    )


# =========================
# === 신규 === Dialog / QMessageBox common stylesheet
# =========================
def msgbox_style(primary_color: str = BTN_PRIMARY) -> str:
    # QMessageBox / QDialog 공통 스타일
    # (QMessageBox 내부 버튼도 QPushButton이라 같이 먹음)
    return f"""
        QMessageBox, QDialog {{
            font-size: 13px;
            color: {TEXT_MAIN};
        }}
        QLabel {{
            color: {TEXT_MAIN};
        }}
        QTextEdit {{
            border-radius: 10px;
            border: 1px solid #e0e0e0;
            padding: 10px;
            color: {TEXT_MAIN};
            background: {BG_WHITE};
        }}
        QCheckBox {{
            spacing: 8px;
            color: {TEXT_MAIN};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
        }}

        QPushButton {{
            {main_style(primary_color)}
        }}
        QPushButton:hover {{
            border: 2px solid {primary_color};
        }}
        QPushButton:disabled {{
            {disabled_style()}
        }}
    """


# =========================
# === 신규 === Banner style
# =========================
def notice_banner_style(color: str = BTN_PRIMARY) -> str:
    return (
        f"padding: 1px 12px;"
        f"border-radius: 5px;"
        f"border: 1px solid {color};"
        f"background: {BG_WHITE};"
        f"color: {TEXT_MAIN};"
        f"min-height: 30px;"
    )