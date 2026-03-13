from tkinter import ttk
from typing import Any


class BaseSettingsPanel(ttk.Frame):
    """확장 가능한 설정 패널 기본 클래스"""

    panel_title = "Settings"

    def __init__(self, parent: Any):
        super().__init__(parent)

    def load_data(self) -> None:
        """외부 설정을 UI에 로드"""

    def save_data(self) -> None:
        """UI 값을 외부 설정으로 저장"""
