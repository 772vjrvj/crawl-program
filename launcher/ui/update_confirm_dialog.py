# launcher/ui/update_confirm_dialog.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from launcher.ui.style.style import (
    BTN_GRAY,
    BTN_PRIMARY,
    btn_style,
)


class UpdateConfirmDialog(QDialog):
    """
    새 버전이 있을 때 표시하는 업데이트 확인창.
    """

    def __init__(
            self,
            parent: QWidget,
            current_version: str,
            latest_version: str,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("업데이트 안내")
        self.setModal(True)
        self.setFixedWidth(470)

        # 제목 표시줄의 도움말 버튼 제거
        self.setWindowFlag(
            Qt.WindowType.WindowContextHelpButtonHint,
            False,
        )

        self.setStyleSheet(
            """
            QDialog {
                background-color: #ffffff;
            }

            QLabel {
                background-color: transparent;
            }

            QFrame#versionBox {
                background-color: #f6f7f9;
                border: 1px solid #e2e5e9;
                border-radius: 10px;
            }

            QLabel#dialogTitle {
                color: #222222;
                font-size: 18px;
                font-weight: 700;
            }

            QLabel#dialogDescription {
                color: #666666;
                font-size: 13px;
            }

            QLabel#versionLabel {
                color: #777777;
                font-size: 12px;
            }

            QLabel#versionValue {
                color: #222222;
                font-size: 16px;
                font-weight: 700;
            }

            QLabel#arrowLabel {
                color: #888888;
                font-size: 18px;
                font-weight: 700;
            }

            QLabel#guideLabel {
                color: #777777;
                font-size: 12px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(18)

        # ============================================================
        # 제목 영역
        # ============================================================
        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        icon_label = QLabel("🔄")
        icon_label.setFixedWidth(34)
        icon_label.setAlignment(
            Qt.AlignmentFlag.AlignTop
            | Qt.AlignmentFlag.AlignHCenter
        )
        icon_label.setStyleSheet(
            """
            font-size: 25px;
            padding-top: 1px;
            """
        )
        title_row.addWidget(icon_label)

        title_text_layout = QVBoxLayout()
        title_text_layout.setSpacing(5)

        title = QLabel("새로운 버전이 있습니다")
        title.setObjectName("dialogTitle")
        title_text_layout.addWidget(title)

        description = QLabel(
            "안정적인 프로그램 사용을 위해 "
            "최신 버전으로 업데이트해 주세요."
        )
        description.setObjectName("dialogDescription")
        description.setWordWrap(True)
        title_text_layout.addWidget(description)

        title_row.addLayout(title_text_layout)
        title_row.addStretch(1)

        root.addLayout(title_row)

        # ============================================================
        # 버전 정보 영역
        # ============================================================
        version_box = QFrame()
        version_box.setObjectName("versionBox")

        version_box_layout = QHBoxLayout(version_box)
        version_box_layout.setContentsMargins(
            18,
            15,
            18,
            15,
        )
        version_box_layout.setSpacing(15)

        # 현재 버전
        current_layout = QVBoxLayout()
        current_layout.setSpacing(4)

        current_label = QLabel("현재 버전")
        current_label.setObjectName("versionLabel")
        current_layout.addWidget(current_label)

        current_value = QLabel(current_version)
        current_value.setObjectName("versionValue")
        current_layout.addWidget(current_value)

        version_box_layout.addLayout(current_layout)
        version_box_layout.addStretch(1)

        # 화살표
        arrow_label = QLabel("→")
        arrow_label.setObjectName("arrowLabel")
        arrow_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        version_box_layout.addWidget(arrow_label)

        version_box_layout.addStretch(1)

        # 최신 버전
        latest_layout = QVBoxLayout()
        latest_layout.setSpacing(4)

        latest_label = QLabel("최신 버전")
        latest_label.setObjectName("versionLabel")
        latest_layout.addWidget(latest_label)

        latest_value = QLabel(latest_version)
        latest_value.setObjectName("versionValue")
        latest_layout.addWidget(latest_value)

        version_box_layout.addLayout(latest_layout)

        root.addWidget(version_box)

        # ============================================================
        # 안내 문구
        # ============================================================
        guide = QLabel(
            "지금 업데이트하지 않아도 현재 설치된 버전을 "
            "계속 실행할 수 있습니다."
        )
        guide.setObjectName("guideLabel")
        guide.setWordWrap(True)
        root.addWidget(guide)

        # ============================================================
        # 버튼 영역
        # ============================================================
        button_row = QHBoxLayout()
        button_row.setSpacing(9)
        button_row.addStretch(1)

        self.btn_skip = QPushButton("현재 버전 실행")
        self.btn_skip.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_skip.setMinimumWidth(125)
        self.btn_skip.setMinimumHeight(40)
        self.btn_skip.setStyleSheet(
            btn_style(BTN_GRAY)
        )
        self.btn_skip.clicked.connect(
            self.reject
        )
        button_row.addWidget(self.btn_skip)

        self.btn_update = QPushButton("지금 업데이트")
        self.btn_update.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_update.setMinimumWidth(125)
        self.btn_update.setMinimumHeight(40)
        self.btn_update.setStyleSheet(
            btn_style(BTN_PRIMARY)
        )
        self.btn_update.clicked.connect(
            self.accept
        )

        # 엔터키를 누르면 업데이트 진행
        self.btn_update.setDefault(True)
        self.btn_update.setAutoDefault(True)

        button_row.addWidget(self.btn_update)

        root.addLayout(button_row)