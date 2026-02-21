# src/ui/select_window.py
from __future__ import annotations  # === 신규 ===

from functools import partial
from typing import List, Optional, Any

from PySide6.QtCore import Qt                     # 정렬, 스크롤바 정책 등 Qt 상수
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor   # 아이콘/픽스맵/도형 그리기
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QScrollArea, QSizePolicy,
    QStyle, QFrame, QLineEdit,
)
from src.core.global_state import GlobalState                # 전역 상태 저장/조회
from src.ui.style.style import create_common_button, main_style  # 공통 버튼/입력창 스타일
from src.vo.site import Site                                 # 사이트 정보 VO(레이블/키/컬러 등)


class SelectWindow(QWidget):
    """
    사이트 선택 창.
    - 상단 검색 입력창(Enter로 검색 실행)
    - 검색창 아래 얇은 구분선
    - 스크롤 가능한 사이트 버튼 목록(가로 300px 고정, 중앙 정렬)
    - 창 최소 크기: 화면 높이의 1/2, 너비 500px (이하로는 축소 불가)
    """

    def __init__(self, app_manager: Any, site_list: List[Site]):
        """
        :param app_manager: 화면 전환/라우팅을 담당하는 AppManager 인스턴스
        :param site_list:   초기 전체 사이트 목록(list[Site])
        """
        super().__init__()
        self.app_manager = app_manager
        self.sites: List[Site] = list(site_list)
        self.filtered_sites: List[Site] = list(site_list)

        # 창 크기 관련 고정값(최소값) — _init_window_metrics()에서 채워짐
        self.fixed_w: int = 0
        self.fixed_h: int = 0

        # UI 위젯 핸들
        self.search_edit: Optional[QLineEdit] = None
        self.search_btn: Optional[QWidget] = None  # (사용 안 함) 버튼 제거했지만 멤버 유지
        self.scroll_area: Optional[QScrollArea] = None
        self.scroll_host: Optional[QWidget] = None
        self.scroll_layout: Optional[QVBoxLayout] = None

        self._init_window_metrics()
        self._build_ui()
        self.center_window()

    # ─────────────────────────────────────────
    # 레이아웃/창 크기 초기화
    # ─────────────────────────────────────────
    def _init_window_metrics(self) -> None:
        """
        화면(모니터)의 전체 지오메트리를 참조해
        - 창 최소 높이: 화면 높이의 1/2
        - 창 최소 너비: 500
        를 계산해 둔다.
        """
        self.fixed_h = 500  # 600
        self.fixed_w = 500  # 최소 너비(500px 고정)

    # ─────────────────────────────────────────
    # UI 빌드
    # ─────────────────────────────────────────
    def _build_ui(self) -> None:
        """검색창/구분선/스크롤 리스트까지 메인 UI를 구성한다."""
        # 1) 윈도우 아이콘(회색 사각형 32x32) 그리기
        icon_pixmap = QPixmap(32, 32)
        icon_pixmap.fill(Qt.transparent)
        p = QPainter(icon_pixmap)
        p.setBrush(QColor("#e0e0e0"))
        p.setPen(QColor("#e0e0e0"))
        p.drawRect(0, 0, 32, 32)
        p.end()
        self.setWindowIcon(QIcon(icon_pixmap))

        # 2) 창 타이틀/크기/배경
        self.setWindowTitle("사이트")
        self.resize(self.fixed_w, self.fixed_h)
        self.setMinimumHeight(self.fixed_h)
        self.setMinimumWidth(self.fixed_w)
        self.setStyleSheet("background-color: #ffffff;")

        # 3) 메인 수직 레이아웃 구성
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # (검색 UI는 주석처리 그대로 유지)

        # 6) 스크롤 가능한 사이트 버튼 리스트
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.scroll_host = QWidget()
        self.scroll_host.setFixedWidth(300)
        self.scroll_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        self.scroll_layout = QVBoxLayout(self.scroll_host)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(12)

        self.scroll_area.setWidget(self.scroll_host)
        layout.addWidget(self.scroll_area, stretch=1)

        # 7) 스크롤바 등장/제거 시 중앙 보정
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)

        # 8) 초기 렌더링 및 마진 보정
        self._rebuild_buttons()

    # ─────────────────────────────────────────
    # 스크롤바 범위 변경
    # ─────────────────────────────────────────
    def _on_scroll_range_changed(self, minimum: int, maximum: int) -> None:
        self._adjust_scrollbar_margin()

    # ─────────────────────────────────────────
    # 검색/필터링
    # ─────────────────────────────────────────
    def _run_search(self) -> None:
        if self.search_edit is None:
            return
        q = (self.search_edit.text() or "").strip()
        self._apply_search(q)

    def _apply_search(self, q: str) -> None:
        q_norm = self._norm_text(q)
        if not q_norm:
            self.filtered_sites = list(self.sites)
        else:
            self.filtered_sites = [
                s for s in self.sites
                if (q_norm in self._norm_text(s.label)) or (q_norm in self._norm_text(getattr(s, "key", "")))
            ]
        self._rebuild_buttons()

    def _norm_text(self, s: str) -> str:
        return (s or "").casefold()

    # ─────────────────────────────────────────
    # 버튼 리스트 렌더링
    # ─────────────────────────────────────────
    def _rebuild_buttons(self) -> None:
        if self.scroll_layout is None:
            return

        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.scroll_layout.addStretch(1)

        for site in self.filtered_sites:
            btn = create_common_button(
                site.label,
                partial(self.select_site, site),
                site.color,
                300,
                site.enabled
            )
            btn.setFixedWidth(300)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.scroll_layout.addWidget(btn, alignment=Qt.AlignHCenter)

        self.scroll_layout.addStretch(1)
        self._adjust_scrollbar_margin()

    # ─────────────────────────────────────────
    # 스크롤 뷰포트 마진 보정
    # ─────────────────────────────────────────
    def _adjust_scrollbar_margin(self) -> None:
        if self.scroll_area is None:
            return
        extent = self.scroll_area.style().pixelMetric(QStyle.PM_ScrollBarExtent)
        has_scroll = self.scroll_area.verticalScrollBar().maximum() > 0
        self.scroll_area.setViewportMargins(extent if has_scroll else 0, 0, 0, 0)

    # ─────────────────────────────────────────
    # 창 중앙 배치 (PySide6 방식)
    # ─────────────────────────────────────────
    def center_window(self) -> None:
        # === 신규 === QDesktopWidget 제거. 현재 창이 올라간 모니터 기준
        scr = self.screen()
        if scr is None:
            return

        screen_geo = scr.availableGeometry()
        win_geo = self.frameGeometry()

        win_geo.moveCenter(screen_geo.center())
        self.move(win_geo.topLeft())

    # ─────────────────────────────────────────
    # 메시지 유틸
    # ─────────────────────────────────────────
    def show_message(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    # ─────────────────────────────────────────
    # 사이트 선택(메인 화면 진입)
    # ─────────────────────────────────────────
    def select_site(self, site: Site) -> None:
        if not site.is_enabled():
            self.show_message("접속실패", f"{site.label}은(는) 준비 중입니다.")
            return

        state = GlobalState()
        state.set(GlobalState.NAME, site.label)
        state.set(GlobalState.SITE, site.key)
        state.set(GlobalState.COLOR, site.color)
        state.set(GlobalState.SETTING, site.setting)
        state.set(GlobalState.SETTING_DETAIL, site.setting_detail)
        state.set(GlobalState.COLUMNS, site.columns)
        state.set(GlobalState.REGION, site.region)
        state.set(GlobalState.POPUP, site.popup)
        state.set(GlobalState.SITES, site.sites)

        self.close()
        self.app_manager.go_to_main()