import json
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List

import requests
import customtkinter as ctk

from app.utils.model3d_params import Model3DParameterManager
from .base_panel import BaseSettingsPanel


class Model3DParametersPanel(BaseSettingsPanel):
    panel_title = "3D Params"
    BG_PRIMARY = "#0f1013"
    BG_CARD = "#151820"
    BG_INPUT = "#1a1f27"
    TEXT_PRIMARY = "#f5f7fa"
    TEXT_SECONDARY = "#b8bec9"
    TEXT_MUTED = "#8e97a7"
    ACCENT = "#2e3440"
    ACCENT_HOVER = "#3a4150"
    SUCCESS = "#22c55e"
    DANGER = "#ef4444"

    EXPECTED_QUEUES = [
        "model3d.upload.queue",
        "recommand.request.queue",
        "model3d.metadata.update.queue",
        "model3d.delete.queue",
    ]

    QUEUE_DISPLAY_NAMES = {
        "model3d.upload.queue": "3D 모델 생성 요청",
        "recommand.request.queue": "가구 추천 요청",
        "model3d.metadata.update.queue": "메타데이터 업데이트",
        "model3d.delete.queue": "3D 모델 삭제 요청",
        "model3d.response": "3D 모델 생성 응답",
        "recommand.response": "가구 추천 응답",
    }

    PRESET_FIELDS = [
        "generation_defaults.ss_guidance_strength",
        "generation_defaults.ss_sampling_steps",
        "generation_defaults.slat_guidance_strength",
        "generation_defaults.slat_sampling_steps",
        "generation_defaults.mesh_simplify_ratio",
        "generation_defaults.texture_size",
    ]

    PRESETS = {
        "low": {
            "generation_defaults.ss_guidance_strength": 7.5,
            "generation_defaults.ss_sampling_steps": 12,
            "generation_defaults.slat_guidance_strength": 3.0,
            "generation_defaults.slat_sampling_steps": 12,
            "generation_defaults.mesh_simplify_ratio": 0.85,
            "generation_defaults.texture_size": 512,
        },
        "normal": {
            "generation_defaults.ss_guidance_strength": 8.0,
            "generation_defaults.ss_sampling_steps": 16,
            "generation_defaults.slat_guidance_strength": 3.0,
            "generation_defaults.slat_sampling_steps": 16,
            "generation_defaults.mesh_simplify_ratio": 0.95,
            "generation_defaults.texture_size": 1024,
        },
        "high": {
            "generation_defaults.ss_guidance_strength": 8.8,
            "generation_defaults.ss_sampling_steps": 24,
            "generation_defaults.slat_guidance_strength": 4.2,
            "generation_defaults.slat_sampling_steps": 24,
            "generation_defaults.mesh_simplify_ratio": 0.98,
            "generation_defaults.texture_size": 2048,
        },
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.manager = Model3DParameterManager()
        self.runtime_api_base = "http://127.0.0.1:5000/api/model3d-params"
        self.mq_api_base = "http://127.0.0.1:5000/api/mq-monitor"

        self.entries: Dict[str, ctk.CTkEntry] = {}
        self.help_labels: Dict[str, ctk.CTkLabel] = {}
        self.content_frame = None

        self.connection_list_frame = None
        self.event_list_frame = None
        self._mq_polling_job = None
        self._last_connection_signature = None
        self._last_event_signature = None

        self.configure(fg_color=self.BG_PRIMARY)
        self._build_ui()
        self.load_data()
        self._refresh_mq_panel()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(self, fg_color=self.BG_CARD, corner_radius=12, width=360)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left_panel.grid_propagate(False)
        left_panel.rowconfigure(3, weight=1)
        left_panel.columnconfigure(0, weight=1)

        mq_title = ctk.CTkLabel(
            left_panel,
            text="RabbitMQ Monitor",
            font=("맑은 고딕", 18, "bold"),
            text_color=self.TEXT_PRIMARY,
        )
        mq_title.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        status_title = ctk.CTkLabel(
            left_panel,
            text="MQ 연결 상태",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_SECONDARY,
        )
        status_title.grid(row=1, column=0, sticky="w", padx=12, pady=(4, 6))

        self.connection_list_frame = ctk.CTkFrame(left_panel, fg_color="#12151b", corner_radius=10)
        self.connection_list_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        event_title = ctk.CTkLabel(
            left_panel,
            text="RabbitMQ 로그",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_SECONDARY,
        )
        event_title.grid(row=3, column=0, sticky="nw", padx=12, pady=(0, 6))

        self.event_list_frame = ctk.CTkScrollableFrame(
            left_panel,
            fg_color="#12151b",
            corner_radius=10,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        self.event_list_frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=(30, 12))

        right_panel = ctk.CTkFrame(self, fg_color=self.BG_PRIMARY, corner_radius=12)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        self.content_frame = ctk.CTkScrollableFrame(
            right_panel,
            corner_radius=10,
            fg_color=self.BG_PRIMARY,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        self.content_frame.grid(row=0, column=0, sticky="nsew")

        self._build_parameter_editor(self.content_frame)

    def _build_parameter_editor(self, parent_widget) -> None:
        row = 0

        title = ctk.CTkLabel(
            parent_widget,
            text="3D 모델 생성 파라미터",
            font=("맑은 고딕", 20, "bold"),
            text_color=self.TEXT_PRIMARY,
        )
        title.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))
        row += 1

        sections = [
            ("API", [("api.base_url", "API Base URL")]),
            (
                "Quality Thresholds",
                [
                    ("quality_thresholds.minimum", "Minimum"),
                    ("quality_thresholds.standard", "Standard"),
                    ("quality_thresholds.premium", "Premium"),
                ],
            ),
            (
                "Generation Defaults",
                [
                    ("generation_defaults.seed", "Seed"),
                    ("generation_defaults.ss_guidance_strength", "SS Guidance"),
                    ("generation_defaults.ss_sampling_steps", "SS Steps"),
                    ("generation_defaults.slat_guidance_strength", "SLAT Guidance"),
                    ("generation_defaults.slat_sampling_steps", "SLAT Steps"),
                    ("generation_defaults.mesh_simplify_ratio", "Mesh Simplify Ratio"),
                    ("generation_defaults.texture_size", "Texture Size"),
                    ("generation_defaults.output_format", "Output Format"),
                ],
            ),
        ]

        for section_title, fields in sections:
            section = ctk.CTkLabel(
                parent_widget,
                text=section_title,
                font=("맑은 고딕", 15, "bold"),
                text_color=self.TEXT_PRIMARY,
            )
            section.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 4))
            row += 1

            for key, label in fields:
                label_widget = ctk.CTkLabel(
                    parent_widget,
                    text=label,
                    text_color=self.TEXT_SECONDARY,
                    font=("맑은 고딕", 13, "bold"),
                )
                label_widget.grid(row=row, column=0, sticky="w", padx=10, pady=3)
                entry = ctk.CTkEntry(
                    parent_widget,
                    width=380,
                    height=34,
                    fg_color=self.BG_INPUT,
                    border_color=self.ACCENT,
                    text_color=self.TEXT_PRIMARY,
                    font=("맑은 고딕", 12),
                )
                entry.grid(row=row, column=1, sticky="we", padx=10, pady=3)
                self.entries[key] = entry

                description = self._get_field_description(key)
                if description:
                    help_label = ctk.CTkLabel(
                        parent_widget,
                        text=description,
                        anchor="w",
                        justify="left",
                        text_color=self.TEXT_MUTED,
                        wraplength=620,
                        font=("맑은 고딕", 11),
                    )
                    help_label.grid(row=row + 1, column=1, sticky="w", padx=10, pady=(0, 4))
                    self.help_labels[key] = help_label
                    row += 2
                else:
                    row += 1

        preset_section_title = ctk.CTkLabel(
            parent_widget,
            text="프리셋",
            font=("맑은 고딕", 15, "bold"),
            text_color=self.TEXT_PRIMARY,
        )
        preset_section_title.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))
        row += 1

        preset_frame = ctk.CTkFrame(parent_widget, fg_color=self.BG_CARD, corner_radius=10)
        preset_frame.grid(row=row, column=0, columnspan=2, sticky="we", padx=10, pady=(8, 6))
        ctk.CTkButton(
            preset_frame,
            text="저품질",
            command=lambda: self._apply_preset("low"),
            width=110,
            height=34,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 12, "bold"),
        ).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(
            preset_frame,
            text="일반",
            command=lambda: self._apply_preset("normal"),
            width=110,
            height=34,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 12, "bold"),
        ).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(
            preset_frame,
            text="고품질",
            command=lambda: self._apply_preset("high"),
            width=110,
            height=34,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 12, "bold"),
        ).pack(side="left", padx=8, pady=8)
        row += 1

        button_frame = ctk.CTkFrame(parent_widget, fg_color="transparent")
        button_frame.grid(row=row, column=0, columnspan=2, sticky="e", padx=10, pady=10)

        ctk.CTkButton(
            button_frame,
            text="새로고침",
            command=self.load_data,
            width=110,
            height=36,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 12, "bold"),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            button_frame,
            text="런타임 적용",
            command=self._on_apply_clicked,
            width=130,
            height=36,
            fg_color="#374151",
            hover_color="#4b5563",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 12, "bold"),
        ).pack(side="left", padx=5)

        parent_widget.columnconfigure(1, weight=1)

    def load_data(self) -> None:
        params = self._load_from_runtime_api()
        if params is None:
            params = self.manager.load()

        for key, entry in self.entries.items():
            value = self._read_nested(params, key)
            entry.delete(0, tk.END)
            if value is not None:
                entry.insert(0, str(value))

            help_label = self.help_labels.get(key)
            if help_label is not None:
                help_label.configure(text=self._get_field_description(key, params))

    def save_data(self) -> None:
        updated = self.manager.load()
        for key, entry in self.entries.items():
            self._write_nested(updated, key, self._convert_value(entry.get().strip()))
        self._apply_to_runtime_api(updated)

    def _on_apply_clicked(self) -> None:
        try:
            self.save_data()
            messagebox.showinfo("적용 완료", "런타임 파라미터를 서버에 반영했습니다.")
            self.load_data()
        except Exception as exc:
            messagebox.showerror("적용 실패", f"런타임 반영 중 오류가 발생했습니다.\n{exc}")

    def _apply_preset(self, preset_name: str) -> None:
        preset = self.PRESETS.get(preset_name, {})
        if not preset:
            return

        for key in self.PRESET_FIELDS:
            entry = self.entries.get(key)
            if entry is None:
                continue
            value = preset.get(key)
            if value is None:
                continue
            entry.delete(0, tk.END)
            entry.insert(0, str(value))

    def _refresh_mq_panel(self) -> None:
        overview = self._load_mq_overview()
        if overview:
            connections = overview.get("connections", [])
            events = overview.get("events", [])

            connection_signature = self._make_connection_signature(connections)
            event_signature = self._make_event_signature(events)

            if connection_signature != self._last_connection_signature:
                self._render_connection_status(connections)
                self._last_connection_signature = connection_signature

            if event_signature != self._last_event_signature:
                self._render_event_cards(events)
                self._last_event_signature = event_signature
        else:
            empty_connection_signature = tuple()
            empty_event_signature = tuple()

            if self._last_connection_signature != empty_connection_signature:
                self._render_connection_status([])
                self._last_connection_signature = empty_connection_signature

            if self._last_event_signature != empty_event_signature:
                self._render_event_cards([])
                self._last_event_signature = empty_event_signature

        if self.winfo_exists():
            self._mq_polling_job = self.after(2000, self._refresh_mq_panel)

    @staticmethod
    def _make_connection_signature(connections: List[dict]):
        normalized = []
        for item in connections:
            normalized.append(
                (
                    item.get("queue"),
                    bool(item.get("connected")),
                    item.get("component"),
                    item.get("detail", ""),
                    item.get("updated_at", ""),
                )
            )
        return tuple(sorted(normalized))

    @staticmethod
    def _make_event_signature(events: List[dict]):
        normalized = []
        for event in events:
            normalized.append(
                (
                    event.get("id"),
                    event.get("timestamp"),
                    event.get("queue"),
                    event.get("direction"),
                )
            )
        return tuple(normalized)

    def _load_mq_overview(self):
        try:
            response = requests.get(f"{self.mq_api_base}/overview", params={"limit": 40}, timeout=2)
            response.raise_for_status()
            payload = response.json()
            return payload if payload.get("success") else None
        except Exception:
            return None

    def _render_connection_status(self, connections: List[dict]) -> None:
        for child in self.connection_list_frame.winfo_children():
            child.destroy()

        connection_map = {item.get("queue"): item for item in connections}
        all_queue_names = list(self.EXPECTED_QUEUES)
        for queue in connection_map.keys():
            if queue not in all_queue_names:
                all_queue_names.append(queue)

        for idx, queue_name in enumerate(all_queue_names):
            info = connection_map.get(queue_name, {})
            connected = bool(info.get("connected", False))
            status_text = "연결됨" if connected else "미연결"
            status_color = self.SUCCESS if connected else self.DANGER
            display_name = self._get_queue_display_name(queue_name)

            row_frame = ctk.CTkFrame(self.connection_list_frame, fg_color="#1a1f27", corner_radius=8)
            row_frame.grid(row=idx, column=0, sticky="ew", padx=8, pady=4)
            row_frame.columnconfigure(0, weight=1)

            ctk.CTkLabel(
                row_frame,
                text=display_name,
                text_color=self.TEXT_SECONDARY,
                font=("맑은 고딕", 11, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=(6, 0))

            ctk.CTkLabel(
                row_frame,
                text=queue_name,
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 9),
                anchor="w",
            ).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 2))

            ctk.CTkLabel(
                row_frame,
                text=status_text,
                text_color=status_color,
                font=("맑은 고딕", 11, "bold"),
                anchor="w",
            ).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 6))

        self.connection_list_frame.columnconfigure(0, weight=1)

    def _render_event_cards(self, events: List[dict]) -> None:
        for child in self.event_list_frame.winfo_children():
            child.destroy()

        if not events:
            ctk.CTkLabel(
                self.event_list_frame,
                text="아직 메시지 이벤트가 없습니다.",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 11),
                anchor="w",
            ).pack(fill="x", padx=8, pady=8)
            return

        for event in events:
            queue_name = event.get("queue", "unknown")
            direction = str(event.get("direction", "IN")).upper()
            action_text = "들어옴" if direction == "IN" else "나감"
            display_name = self._get_queue_display_name(queue_name)
            preview_status = self._extract_event_status(event)
            status_suffix = f" ({preview_status})" if preview_status else ""
            line_text = f"{display_name}: 메시지가 {action_text}{status_suffix}"

            card = ctk.CTkFrame(self.event_list_frame, fg_color="#1a1f27", corner_radius=8)
            card.pack(fill="x", padx=8, pady=4)

            ctk.CTkLabel(
                card,
                text=queue_name,
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 9),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(6, 0))

            btn = ctk.CTkButton(
                card,
                text=line_text,
                command=lambda e=event: self._show_event_detail(e),
                anchor="w",
                fg_color="#1f2530",
                hover_color="#2a3140",
                text_color=self.TEXT_PRIMARY,
                font=("맑은 고딕", 11),
                height=34,
            )
            btn.pack(fill="x", padx=6, pady=(2, 6))

    def _show_event_detail(self, event: dict) -> None:
        detail_window = ctk.CTkToplevel(self)
        detail_window.title("RabbitMQ 이벤트 상세")
        detail_window.geometry("620x520")
        detail_window.configure(fg_color=self.BG_PRIMARY)
        detail_window.grab_set()

        queue_name = event.get("queue", "unknown")
        direction = str(event.get("direction", "IN")).upper()
        action_text = "들어옴" if direction == "IN" else "나감"
        display_name = self._get_queue_display_name(queue_name)
        preview_status = self._extract_event_status(event)
        status_suffix = f" ({preview_status})" if preview_status else ""

        ctk.CTkLabel(
            detail_window,
            text=f"{display_name}: 메시지가 {action_text}{status_suffix}",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 15, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            detail_window,
            text=f"큐: {queue_name}",
            text_color=self.TEXT_MUTED,
            font=("맑은 고딕", 10),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 2))

        ctk.CTkLabel(
            detail_window,
            text=f"시간: {event.get('timestamp', '-')}",
            text_color=self.TEXT_MUTED,
            font=("맑은 고딕", 11),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 8))

        detail_box = ctk.CTkTextbox(
            detail_window,
            fg_color="#12151b",
            text_color=self.TEXT_SECONDARY,
            corner_radius=8,
            font=("Consolas", 11),
        )
        detail_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        detail_payload = event.get("details")
        try:
            pretty = json.dumps(detail_payload, ensure_ascii=False, indent=2)
        except Exception:
            pretty = str(detail_payload)

        detail_box.insert("1.0", pretty)
        detail_box.configure(state="disabled")

    def _get_queue_display_name(self, queue_name: str) -> str:
        return self.QUEUE_DISPLAY_NAMES.get(queue_name, queue_name)

    @staticmethod
    def _extract_event_status(event: dict) -> str:
        direction = str(event.get("direction", "")).upper()
        if direction != "OUT":
            return ""

        details = event.get("details")
        if not isinstance(details, dict):
            return ""

        raw_status = details.get("status")
        if raw_status is None:
            return ""

        status_text = str(raw_status).strip().upper()
        if status_text in ("SUCCESS", "SUCCEEDED", "OK"):
            return "성공"
        if status_text in ("FAILED", "FAIL", "ERROR"):
            return "실패"
        return str(raw_status)

    @staticmethod
    def _read_nested(data: dict, key_path: str):
        current = data
        for part in key_path.split('.'):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @staticmethod
    def _write_nested(data: dict, key_path: str, value):
        keys = key_path.split('.')
        current = data
        for part in keys[:-1]:
            current = current.setdefault(part, {})
        current[keys[-1]] = value

    @staticmethod
    def _convert_value(value: str):
        if value == "":
            return value
        try:
            if value.lower() in ("true", "false"):
                return value.lower() == "true"
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _get_field_description(self, key_path: str, params: dict = None) -> str:
        if params is None:
            params = self.manager.load()

        parts = key_path.split('.')
        if len(parts) < 2:
            return ""

        section = params.get(parts[0], {})
        descriptions = section.get('_field_descriptions', {}) if isinstance(section, dict) else {}
        field_name = parts[-1]
        return descriptions.get(field_name, "")

    def _load_from_runtime_api(self):
        try:
            response = requests.get(f"{self.runtime_api_base}/runtime", timeout=2)
            response.raise_for_status()
            payload = response.json()
            return payload.get('params')
        except Exception:
            return None

    def _apply_to_runtime_api(self, params: dict) -> None:
        response = requests.put(f"{self.runtime_api_base}/runtime", json=params, timeout=3)
        response.raise_for_status()
