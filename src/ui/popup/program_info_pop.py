# src/ui/popup/program_info_pop.py
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.popup.program_info_detail_pop import ProgramInfoDetailPop
from src.ui.style.style import create_common_button
from src.utils.program_notice_read_store import ProgramNoticeReadStore
from src.workers.program_notice_worker import ProgramNotice


class NoticeCard(QFrame):
    """공지사항 목록에서 사용하는 클릭 가능한 카드."""

    clicked = Signal(object)  # ProgramNotice

    def __init__(
            self,
            notice: ProgramNotice,
            unread: bool,
            parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.notice = notice
        self.unread = unread

        self.setObjectName("noticeCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(88)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.setStyleSheet(
            """
            QFrame#noticeCard {
                background-color: #ffffff;
                border: 1px solid #d9d9d9;
                border-radius: 10px;
            }
            QFrame#noticeCard:hover {
                background-color: #f8f8f8;
                border: 1px solid #bdbdbd;
            }
            QLabel {
                background-color: transparent;
                border: none;
            }
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 14, 12)
        root.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        level_label = QLabel(self.level_text(notice.level))
        level_label.setFixedHeight(24)
        level_label.setStyleSheet(self.level_style(notice.level))
        level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        level_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        top_row.addWidget(level_label)

        if notice.program_id:
            target_label = QLabel(
                "전체 공지"
                if notice.program_id.upper() == "ALL"
                else "프로그램 공지"
            )
            target_label.setStyleSheet(
                "font-size: 12px; color: #888888;"
            )
            target_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )
            top_row.addWidget(target_label)

        # 읽지 않은 공지만 NEW 표시한다.
        # 최신 공지는 서버에서 최신순으로 내려오므로 읽지 않았다면 최상단에 NEW가 보인다.
        if unread:
            new_label = QLabel("NEW")
            new_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            new_label.setFixedHeight(22)
            new_label.setStyleSheet(
                """
                QLabel {
                    min-width: 34px;
                    padding: 0 6px;
                    background-color: #e53935;
                    color: #ffffff;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 700;
                }
                """
            )
            new_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )
            top_row.addWidget(new_label)

        top_row.addStretch(1)

        date_label = QLabel(self.format_date(notice.created_at))
        date_label.setStyleSheet(
            "font-size: 12px; color: #888888;"
        )
        date_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        top_row.addWidget(date_label)

        text_layout.addLayout(top_row)

        title_label = QLabel(notice.title or "제목 없음")
        title_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #222222;"
        )
        title_label.setWordWrap(False)
        title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        text_layout.addWidget(title_label)

        root.addLayout(text_layout, 1)

        arrow = QLabel("›")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setFixedWidth(20)
        arrow.setStyleSheet(
            "font-size: 24px; font-weight: 500; color: #999999;"
        )
        arrow.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        root.addWidget(arrow)

    @staticmethod
    def level_text(level: str) -> str:
        value = (level or "INFO").upper()
        if value == "CRITICAL":
            return "긴급"
        if value == "IMPORTANT":
            return "중요"
        return "안내"

    @staticmethod
    def level_style(level: str) -> str:
        value = (level or "INFO").upper()

        if value == "CRITICAL":
            return """
                QLabel {
                    min-width: 42px;
                    padding: 0 7px;
                    border-radius: 6px;
                    background-color: #fff0f0;
                    color: #d32f2f;
                    font-size: 12px;
                    font-weight: 700;
                }
            """

        if value == "IMPORTANT":
            return """
                QLabel {
                    min-width: 42px;
                    padding: 0 7px;
                    border-radius: 6px;
                    background-color: #fff8e6;
                    color: #9a6700;
                    font-size: 12px;
                    font-weight: 700;
                }
            """

        return """
            QLabel {
                min-width: 42px;
                padding: 0 7px;
                border-radius: 6px;
                background-color: #f2f4f6;
                color: #555555;
                font-size: 12px;
                font-weight: 700;
            }
        """

    @staticmethod
    def format_date(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        if "T" in text:
            return text.split("T", 1)[0]
        if " " in text:
            return text.split(" ", 1)[0]
        return text

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.notice)
            event.accept()
            return
        super().mousePressEvent(event)


class ProgramInfoPop(QDialog):
    """
    프로그램 정보 팝업.

    - 공지사항: MainWindow에서 미리 조회한 데이터를 즉시 표시한다.
    - 릴리즈 노트: 탭 최초 진입 시 조회하도록 자리만 준비한다.
    - 프로그램 설명: 탭 최초 진입 시 조회하도록 자리만 준비한다.
    """

    TAB_NOTICE = 0
    TAB_RELEASE = 1
    TAB_DESCRIPTION = 2

    notice_read = Signal(str)  # notice_id

    def __init__(
            self,
            parent: Optional[QWidget],
            server_url: str,
            program_id: str,
            site: str,
            notices: Optional[list[ProgramNotice]] = None,
            read_store: Optional[ProgramNoticeReadStore] = None,
            color: Optional[str] = None,
            notice_loaded: bool = True,
    ) -> None:
        super().__init__(parent)

        self.server_url = server_url
        self.program_id = (program_id or "").strip()
        self.site = (site or "").strip()
        self.color = color or "#888888"

        self.notices: list[ProgramNotice] = list(notices or [])
        self.read_store = read_store or ProgramNoticeReadStore(self.site)
        self.notice_loaded = notice_loaded

        self.release_loaded = False
        self.description_loaded = False

        self.tab_buttons: list[QPushButton] = []

        self.setWindowTitle("프로그램 정보")
        self.resize(760, 620)
        self.setMinimumSize(700, 560)
        self.setStyleSheet("background-color: white; color: #111;")

        self._init_ui()
        self._select_tab(self.TAB_NOTICE)
        self._render_notice_cards()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("프로그램 정보")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #111; padding: 4px;"
        )
        root.addWidget(title)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)

        for text, index in [
            ("공지사항", self.TAB_NOTICE),
            ("릴리즈 노트", self.TAB_RELEASE),
            ("프로그램 설명", self.TAB_DESCRIPTION),
        ]:
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(40)
            button.setMinimumWidth(145)
            button.clicked.connect(
                lambda _checked=False, tab_index=index: self._select_tab(tab_index)
            )
            self.tab_buttons.append(button)
            tab_row.addWidget(button)

        tab_row.addStretch(1)
        root.addLayout(tab_row)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: white;")

        self.notice_page = self._create_notice_page()
        self.release_page = self._create_release_page()
        self.description_page = self._create_description_page()

        self.stack.addWidget(self.notice_page)
        self.stack.addWidget(self.release_page)
        self.stack.addWidget(self.description_page)

        root.addWidget(self.stack, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(
            create_common_button("닫기", self.reject, "black", 120)
        )
        root.addLayout(button_row)

    @staticmethod
    def _create_content_frame() -> tuple[QFrame, QVBoxLayout]:
        """세 탭이 동일하게 사용하는 항상 보이는 외곽 네모 영역."""
        frame = QFrame()
        frame.setObjectName("programInfoContentFrame")
        frame.setStyleSheet(
            """
            QFrame#programInfoContentFrame {
                background-color: #ffffff;
                border: 1px solid #d9d9d9;
                border-radius: 10px;
            }
            """
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        return frame, layout

    @staticmethod
    def _scroll_style() -> str:
        return """
            QScrollArea {
                background-color: #ffffff;
                border: none;
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
                margin: 8px 2px 8px 0px;
            }
            QScrollBar::handle:vertical {
                min-height: 24px;
                background: rgba(120, 120, 120, 160);
                border-radius: 4px;
            }
            QScrollBar::add-line,
            QScrollBar::sub-line,
            QScrollBar::add-page,
            QScrollBar::sub-page {
                border: none;
                background: transparent;
                height: 0px;
            }
        """

    def _create_notice_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: white;")

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        frame, frame_layout = self._create_content_frame()

        self.notice_status_label = QLabel("")
        self.notice_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notice_status_label.setWordWrap(True)
        self.notice_status_label.setStyleSheet(
            "font-size: 13px; color: #777777; padding: 20px; border: none;"
        )
        frame_layout.addWidget(self.notice_status_label)

        self.notice_scroll = QScrollArea()
        self.notice_scroll.setWidgetResizable(True)
        self.notice_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.notice_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.notice_scroll.setStyleSheet(self._scroll_style())

        self.notice_list_widget = QWidget()
        self.notice_list_widget.setStyleSheet("background-color: #ffffff;")
        self.notice_list_layout = QVBoxLayout(self.notice_list_widget)
        self.notice_list_layout.setContentsMargins(0, 0, 4, 0)
        self.notice_list_layout.setSpacing(8)
        self.notice_list_layout.addStretch(1)

        self.notice_scroll.setWidget(self.notice_list_widget)
        frame_layout.addWidget(self.notice_scroll, 1)

        page_layout.addWidget(frame, 1)
        return page

    def _create_release_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: white;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        frame, frame_layout = self._create_content_frame()

        self.release_status_label = QLabel("등록된 릴리즈 노트가 없습니다.")
        self.release_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.release_status_label.setStyleSheet(
            "font-size: 13px; color: #777777; padding: 20px; border: none;"
        )
        frame_layout.addWidget(self.release_status_label, 1)

        page_layout.addWidget(frame, 1)
        return page

    def _create_description_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: white;")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        frame, frame_layout = self._create_content_frame()

        self.description_text = QTextEdit()
        self.description_text.setReadOnly(True)
        self.description_text.setPlainText("")
        self.description_text.setFrameShape(QFrame.Shape.NoFrame)
        self.description_text.setStyleSheet(
            """
            QTextEdit {
                border: none;
                background-color: #ffffff;
                color: #222222;
                padding: 4px;
                font-size: 13px;
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                min-height: 24px;
                background: rgba(120, 120, 120, 160);
                border-radius: 4px;
            }
            """
        )
        frame_layout.addWidget(self.description_text, 1)

        page_layout.addWidget(frame, 1)
        return page

    def _select_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

        for button_index, button in enumerate(self.tab_buttons):
            button.setStyleSheet(
                self._active_tab_style()
                if button_index == index
                else self._inactive_tab_style()
            )

        # 공지는 MainWindow에서 이미 선조회한다.
        # 릴리즈/설명은 해당 탭에 최초 진입했을 때만 API를 호출하도록 분리한다.
        if index == self.TAB_RELEASE and not self.release_loaded:
            self._load_release_notes_once()
        elif index == self.TAB_DESCRIPTION and not self.description_loaded:
            self._load_program_description_once()

    @staticmethod
    def _active_tab_style() -> str:
        return """
            QPushButton {
                border-radius: 10px;
                border: 2px solid black;
                background-color: black;
                padding: 8px 14px;
                font-weight: 600;
                font-size: 14px;
                color: white;
            }
        """

    @staticmethod
    def _inactive_tab_style() -> str:
        return """
            QPushButton {
                border-radius: 10px;
                border: 2px solid #cccccc;
                background-color: #ffffff;
                padding: 8px 14px;
                font-weight: 490;
                font-size: 14px;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #f7f7f7;
                border-color: #aaaaaa;
            }
        """

    def set_notices(self, notices: list[ProgramNotice], loaded: bool = True) -> None:
        """팝업이 열린 상태에서 MainWindow 선조회가 완료된 경우에도 즉시 반영한다."""
        self.notices = list(notices or [])
        self.notice_loaded = loaded
        self._render_notice_cards()

    def _clear_notice_cards(self) -> None:
        while self.notice_list_layout.count() > 1:
            item = self.notice_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _render_notice_cards(self) -> None:
        self._clear_notice_cards()

        if not self.notice_loaded:
            self.notice_status_label.setText("공지사항을 불러오는 중입니다...")
            self.notice_status_label.setVisible(True)
            self.notice_scroll.setVisible(False)
            return

        if not self.notices:
            self.notice_status_label.setText("등록된 공지사항이 없습니다.")
            self.notice_status_label.setVisible(True)
            self.notice_scroll.setVisible(False)
            return

        unread_ids = self.read_store.get_unread_ids(self.notices)

        self.notice_status_label.setVisible(False)
        self.notice_scroll.setVisible(True)

        for notice in self.notices:
            card = NoticeCard(
                notice=notice,
                unread=notice.notice_id in unread_ids,
            )
            card.clicked.connect(self._open_notice_detail)
            self.notice_list_layout.insertWidget(
                self.notice_list_layout.count() - 1,
                card,
            )

    def _open_notice_detail(self, notice: ProgramNotice) -> None:
        # 실제 상세를 여는 순간 읽음으로 저장한다.
        was_unread = not self.read_store.is_read(notice.notice_id)
        if was_unread:
            self.read_store.mark_read(notice.notice_id)
            self.notice_read.emit(notice.notice_id)
            self._render_notice_cards()

        meta_parts: list[str] = []
        if notice.program_id:
            meta_parts.append(
                "전체 프로그램"
                if notice.program_id.upper() == "ALL"
                else notice.program_id
            )
        if notice.created_at:
            meta_parts.append(notice.created_at)

        dialog = ProgramInfoDetailPop(
            parent=self,
            window_title="공지사항 상세",
            title=notice.title,
            content=notice.content,
            meta_text="  ·  ".join(meta_parts),
            badge_text=NoticeCard.level_text(notice.level),
        )
        dialog.exec()

    def _load_release_notes_once(self) -> None:
        """
        릴리즈 노트 탭 최초 진입 시 호출된다.

        TODO: 서버 릴리즈 노트 API가 추가되면 여기에서 Worker를 시작한다.
        공지와 달리 MainWindow 시작 시에는 호출하지 않는다.
        """
        self.release_loaded = True
        self.release_status_label.setText("등록된 릴리즈 노트가 없습니다.")

    def _load_program_description_once(self) -> None:
        """
        프로그램 설명 탭 최초 진입 시 호출된다.

        TODO: 서버 프로그램 설명 API가 추가되면 여기에서 Worker를 시작하고
        서버 문자열을 self.description_text.setPlainText(...)로 그대로 출력한다.
        """
        self.description_loaded = True
        self.description_text.setPlainText("")
