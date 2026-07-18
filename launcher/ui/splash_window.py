# launcher/ui/splash_window.py
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class RoundedImageCard(QWidget):

    def __init__(
            self,
            image_path: str | Path,
            width: int = 700,
            height: int = 420,
            radius: int = 24,
            padding: int = 8,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.image_path = Path(image_path)
        self.radius = radius
        self.padding = padding
        self.pixmap = QPixmap(str(self.image_path))

        self.setFixedSize(width, height)
        self.setStyleSheet(
            "background: transparent;"
        )

    def set_image(
            self,
            image_path: str | Path,
    ) -> None:
        """
        이미지 카드에 표시되는 이미지를 변경한다.
        """
        self.image_path = Path(image_path)
        self.pixmap = QPixmap(
            str(self.image_path)
        )

        self.update()

    def paintEvent(self, event) -> None:
        """이미지 전체와 둥근 테두리를 직접 그린다."""

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            True,
        )

        # 테두리가 잘리지 않도록 위젯 안쪽으로 1픽셀 들어온다.
        card_rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        card_path = QPainterPath()
        card_path.addRoundedRect(
            card_rect,
            self.radius,
            self.radius,
        )

        # 둥근 카드 배경
        painter.fillPath(card_path, QColor("#ffffff"))

        # 둥근 영역 안에서만 이미지가 보이도록 제한한다.
        painter.save()
        painter.setClipPath(card_path)

        if self.pixmap.isNull():
            painter.setPen(QColor("#111111"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "GB7",
            )
        else:
            # 이미지가 모서리에서 잘리지 않도록 안쪽 여백을 둔다.
            image_rect = card_rect.adjusted(
                self.padding,
                self.padding,
                -self.padding,
                -self.padding,
            )

            # 원본 비율을 유지하므로 위·아래 또는 좌·우가 잘리지 않는다.
            scaled_pixmap = self.pixmap.scaled(
                int(image_rect.width()),
                int(image_rect.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # 이미지 영역의 중앙에 배치한다.
            image_x = image_rect.x() + (
                    image_rect.width() - scaled_pixmap.width()
            ) / 2
            image_y = image_rect.y() + (
                    image_rect.height() - scaled_pixmap.height()
            ) / 2

            painter.drawPixmap(
                int(image_x),
                int(image_y),
                scaled_pixmap,
            )

        painter.restore()

        # 흰 배경에서도 둥근 모서리가 보이도록 연한 테두리를 그린다.
        border_pen = QPen(QColor("#dfe4ea"))
        border_pen.setWidthF(1.2)

        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(card_path)

        painter.end()


class SplashWindow(QWidget):
    """
    프로그램 실행 시 표시되는 시작 화면.

    실행 순서:
    1. 흰색 시작 화면 표시
    2. 로고 이미지 페이드 인
    3. GB7 문구 표시
    4. GoodBye772 문구를 한 글자씩 표시
    5. 저작권 문구 표시
    6. 전체 화면 페이드 아웃
    7. finished 시그널 발생

    이미지, 이름, 저작권 영역은 처음부터 고정된 공간을 가진다.
    따라서 문구가 나타날 때 이미지 위치가 움직이지 않는다.
    """

    finished = Signal()

    def __init__(
            self,
            image_path: str | Path,
            wink_image_path: str | Path,
    ) -> None:
        super().__init__()

        self.image_path = Path(image_path)
        self.wink_image_path = Path(
            wink_image_path
        )

        # 애니메이션 중복 실행 방지
        self._animation_started = False

        # 타이핑 애니메이션에 사용할 최종 문구
        self._final_text = "GoodBye772"
        self._typing_index = 0

        self._init_window()
        self._init_ui()
        self._init_timer()

    def _init_window(self) -> None:
        """스플래시 창의 기본 모양을 설정한다."""

        # 제목 표시줄과 테두리가 없는 시작 화면
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint
        )

        # 스플래시 화면 크기
        self.setFixedSize(760, 620)

        # 전체 배경은 흰색
        self.setStyleSheet("background-color: #ffffff;")

        # 전체 화면 페이드 아웃 전 기본 투명도
        self.setWindowOpacity(1.0)

    def _init_ui(self) -> None:
        """스플래시 화면의 위젯을 생성하고 배치한다."""

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 20)
        root.setSpacing(0)

        root.addStretch(1)

        # ====================================================
        # 1. 이미지 전용 공간
        # ====================================================
        image_area = QWidget()
        image_area.setFixedHeight(440)
        image_area.setStyleSheet("background: transparent;")

        image_layout = QVBoxLayout(image_area)
        image_layout.setContentsMargins(0, 10, 0, 10)
        image_layout.setSpacing(0)

        self.image_card = RoundedImageCard(
            image_path=self.image_path,
            width=700,
            height=420,
            radius=24,
            padding=8,
        )

        # 이미지 페이드 인 효과
        self.image_opacity_effect = QGraphicsOpacityEffect(
            self.image_card
        )
        self.image_opacity_effect.setOpacity(0.0)
        self.image_card.setGraphicsEffect(
            self.image_opacity_effect
        )

        image_layout.addWidget(
            self.image_card,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        root.addWidget(image_area)

        # ====================================================
        # 2. GB7 / GoodBye772 전용 공간
        # ====================================================
        name_area = QWidget()
        name_area.setFixedHeight(66)
        name_area.setStyleSheet("background: transparent;")

        name_layout = QVBoxLayout(name_area)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(0)

        self.lbl_name = QLabel("")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_name.setStyleSheet(
            """
            QLabel {
                background: transparent;
                font-family: "Segoe UI";
                font-size: 34px;
                font-weight: 800;
            }
            """
        )

        # 이름 영역은 처음부터 존재하고 투명도만 변경한다.
        self.text_opacity_effect = QGraphicsOpacityEffect(
            self.lbl_name
        )
        self.text_opacity_effect.setOpacity(0.0)
        self.lbl_name.setGraphicsEffect(
            self.text_opacity_effect
        )

        name_layout.addWidget(self.lbl_name)
        root.addWidget(name_area)

        # ====================================================
        # 3. 저작권 문구 전용 공간
        # ====================================================
        copyright_area = QWidget()
        copyright_area.setFixedHeight(30)
        copyright_area.setStyleSheet("background: transparent;")

        copyright_layout = QVBoxLayout(copyright_area)
        copyright_layout.setContentsMargins(0, 0, 0, 0)
        copyright_layout.setSpacing(0)

        start_year = 2026
        current_year = datetime.now().year

        if current_year <= start_year:
            copyright_year = str(start_year)
        else:
            copyright_year = f"{start_year}–{current_year}"

        self.lbl_copyright = QLabel(
            f"© {copyright_year} GB7. All rights reserved."
        )
        self.lbl_copyright.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.lbl_copyright.setStyleSheet(
            """
            QLabel {
                color: #888888;
                background: transparent;
                font-family: "Segoe UI";
                font-size: 11px;
                font-weight: 400;
            }
            """
        )

        # setVisible(False)를 사용하지 않는다.
        # 처음부터 레이아웃 공간을 유지하고 투명도만 0으로 둔다.
        self.copyright_opacity_effect = QGraphicsOpacityEffect(
            self.lbl_copyright
        )
        self.copyright_opacity_effect.setOpacity(0.0)
        self.lbl_copyright.setGraphicsEffect(
            self.copyright_opacity_effect
        )

        copyright_layout.addWidget(self.lbl_copyright)
        root.addWidget(copyright_area)

        root.addStretch(1)

    def _init_timer(self) -> None:
        """GoodBye772 타이핑 애니메이션용 타이머를 준비한다."""

        self.typing_timer = QTimer(self)
        self.typing_timer.setInterval(70)
        self.typing_timer.timeout.connect(
            self._type_next_character
        )

    def showEvent(self, event) -> None:
        """스플래시 창이 표시될 때 화면 중앙으로 이동한다."""

        super().showEvent(event)
        self._move_to_center()

    def _move_to_center(self) -> None:
        """스플래시 창을 현재 기본 화면의 중앙으로 이동한다."""

        screen = QApplication.primaryScreen()

        if screen is None:
            return

        screen_rect = screen.availableGeometry()

        x = screen_rect.center().x() - (self.width() // 2)
        y = screen_rect.center().y() - (self.height() // 2)

        self.move(x, y)

    def start_animation(self) -> None:
        """전체 시작 애니메이션을 실행한다."""

        if self._animation_started:
            return

        self._animation_started = True

        # 1. 로고 이미지 페이드 인
        self.image_fade_in = QPropertyAnimation(
            self.image_opacity_effect,
            b"opacity",
            self,
        )
        self.image_fade_in.setDuration(700)
        self.image_fade_in.setStartValue(0.0)
        self.image_fade_in.setEndValue(1.0)
        self.image_fade_in.setEasingCurve(
            QEasingCurve.Type.InOutCubic
        )
        self.image_fade_in.start()

        # 이미지가 어느 정도 표시된 뒤 GB7 문구를 보여준다.
        QTimer.singleShot(500, self._show_gb7)

    def _show_gb7(self) -> None:
        """GB7 문구를 표시한다."""

        self._set_colored_text("GB7")

        self.text_fade_in = QPropertyAnimation(
            self.text_opacity_effect,
            b"opacity",
            self,
        )
        self.text_fade_in.setDuration(250)
        self.text_fade_in.setStartValue(0.0)
        self.text_fade_in.setEndValue(1.0)
        self.text_fade_in.setEasingCurve(
            QEasingCurve.Type.InOutCubic
        )
        self.text_fade_in.start()

        # 잠시 GB7을 보여준 뒤 GoodBye772로 전환한다.
        QTimer.singleShot(750, self._hide_gb7)

    def _hide_gb7(self) -> None:
        """GB7 문구를 페이드 아웃한다."""

        self.text_fade_out = QPropertyAnimation(
            self.text_opacity_effect,
            b"opacity",
            self,
        )
        self.text_fade_out.setDuration(200)
        self.text_fade_out.setStartValue(1.0)
        self.text_fade_out.setEndValue(0.0)
        self.text_fade_out.setEasingCurve(
            QEasingCurve.Type.InOutCubic
        )
        self.text_fade_out.finished.connect(
            self._start_typing
        )
        self.text_fade_out.start()

    def _start_typing(self) -> None:
        """GoodBye772 타이핑 애니메이션을 시작한다."""

        self._typing_index = 0
        self.lbl_name.clear()

        # 타이핑 문구가 바로 보이도록 투명도를 1로 설정한다.
        self.text_opacity_effect.setOpacity(1.0)

        self.typing_timer.start()

    def _type_next_character(self) -> None:
        """GoodBye772 문구를 한 글자씩 추가한다."""

        self._typing_index += 1

        current_text = self._final_text[:self._typing_index]
        self._set_colored_text(current_text)

        if self._typing_index >= len(self._final_text):
            self.typing_timer.stop()

            # 최종 문구가 완성되면 저작권 문구를 표시한다.
            self._show_copyright()

    def _set_colored_text(self, text: str) -> None:
        """
        영문은 검은색, 숫자는 빨간색으로 표시한다.

        GB7:
        GB = 검은색
        7  = 빨간색

        GoodBye772:
        GoodBye = 검은색
        772     = 빨간색
        """

        html_parts: list[str] = []

        for char in text:
            safe_char = escape(char)

            if char.isdigit():
                color = "#e00000"
            else:
                color = "#111111"

            html_parts.append(
                f'<span style="color:{color};">{safe_char}</span>'
            )

        self.lbl_name.setText("".join(html_parts))

    def _show_copyright(self) -> None:
        """GoodBye772 아래에 저작권 문구를 페이드 인한다."""

        self.copyright_fade_in = QPropertyAnimation(
            self.copyright_opacity_effect,
            b"opacity",
            self,
        )
        self.copyright_fade_in.setDuration(300)
        self.copyright_fade_in.setStartValue(0.0)
        self.copyright_fade_in.setEndValue(1.0)
        self.copyright_fade_in.setEasingCurve(
            QEasingCurve.Type.InOutCubic
        )
        self.copyright_fade_in.finished.connect(
            self._wait_before_finish
        )
        self.copyright_fade_in.start()

    def _wait_before_finish(self) -> None:
        """
        마지막에 윙크 이미지로 변경한 뒤
        잠시 보여주고 스플래시를 종료한다.
        """

        if self.wink_image_path.is_file():
            self.image_card.set_image(
                self.wink_image_path
            )

        QTimer.singleShot(
            1200,
            self._fade_out_splash,
        )

    def _fade_out_splash(self) -> None:
        """스플래시 화면 전체를 페이드 아웃한다."""

        self.window_fade_out = QPropertyAnimation(
            self,
            b"windowOpacity",
            self,
        )
        self.window_fade_out.setDuration(350)
        self.window_fade_out.setStartValue(1.0)
        self.window_fade_out.setEndValue(0.0)
        self.window_fade_out.setEasingCurve(
            QEasingCurve.Type.InOutCubic
        )
        self.window_fade_out.finished.connect(self._finish)
        self.window_fade_out.start()

    def _finish(self) -> None:
        """메인 화면을 열도록 완료 시그널을 전달하고 종료한다."""

        # finished 시그널에 연결된 함수가 메인 화면을 생성한다.
        self.finished.emit()

        # 메인 화면 생성 후 스플래시 화면을 닫는다.
        self.close()
