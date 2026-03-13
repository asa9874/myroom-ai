import json
import os
import subprocess
import threading
import time
from queue import Queue, Empty
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Dict, List, Any

import requests
import customtkinter as ctk
from PIL import Image

from app.utils.model3d_params import Model3DParameterManager
from app.utils.model3d_generator import Model3DGenerator
from .base_panel import BaseSettingsPanel
from gui.widgets import launch_external_glb_viewer


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

    BOOL_FIELDS = {
        "runtime_options.model3d_use_detected_object",
        "runtime_options.quality_check_enabled",
        "runtime_options.quality_check_strict_mode",
    }

    FIELD_LABELS = {
        "api.base_url": "3D 서버 URL",
        "runtime_options.model3d_use_detected_object": "감지 객체 우선 사용",
        "runtime_options.quality_check_enabled": "품질 검사 사용",
        "runtime_options.quality_check_strict_mode": "엄격 품질 모드",
        "generation_defaults.seed": "Seed",
        "generation_defaults.ss_guidance_strength": "SS Guidance",
        "generation_defaults.ss_sampling_steps": "SS Steps",
        "generation_defaults.slat_guidance_strength": "SLAT Guidance",
        "generation_defaults.slat_sampling_steps": "SLAT Steps",
        "generation_defaults.mesh_simplify_ratio": "Mesh Ratio",
        "generation_defaults.texture_size": "Texture Size",
        "generation_defaults.output_format": "Output",
    }

    GENERATION_DETAIL_ORDER = [
        "seed",
        "ss_guidance_strength",
        "ss_sampling_steps",
        "slat_guidance_strength",
        "slat_sampling_steps",
        "mesh_simplify_ratio",
        "texture_size",
        "output_format",
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.manager = Model3DParameterManager()
        self.runtime_api_base = "http://127.0.0.1:5000/api/model3d-params"
        self.mq_api_base = "http://127.0.0.1:5000/api/mq-monitor"
        self.local_generator = Model3DGenerator(parameter_manager=self.manager)
        self._local_generation_lock = threading.Lock()
        self._local_generations: Dict[str, Dict[str, Any]] = {}
        self._local_generation_seq = 0

        self.entries: Dict[str, Any] = {}
        self.bool_vars: Dict[str, tk.BooleanVar] = {}
        self.content_frame = None

        self.connection_list_frame = None
        self.event_list_frame = None
        self.generation_grid_frame = None
        self._generation_image_cache: Dict[str, ctk.CTkImage] = {}
        self.model_server_status_title = None
        self.model_server_status_detail = None
        self._last_model_server_status_signature = None
        self._model_server_check_inflight = False
        self._model_server_check_results: Queue = Queue()
        self._model_server_next_check_at = 0.0
        self._model_server_backoff_ms = 2000
        self._mq_polling_job = None
        self._last_connection_signature = None
        self._last_event_signature = None
        self._last_generation_signature = None
        self._generation_field_descriptions = self._load_generation_field_descriptions()

        self.configure(fg_color=self.BG_PRIMARY)
        self._build_ui()
        self.load_data()
        self._refresh_mq_panel()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=3)
        self.columnconfigure(2, weight=2)
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

        middle_panel = ctk.CTkFrame(self, fg_color=self.BG_PRIMARY, corner_radius=12)
        middle_panel.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        middle_panel.columnconfigure(0, weight=1)
        middle_panel.rowconfigure(0, weight=1)

        self.content_frame = ctk.CTkScrollableFrame(
            middle_panel,
            corner_radius=10,
            fg_color=self.BG_PRIMARY,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        self.content_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 0))

        self._build_parameter_editor(self.content_frame)

        right_panel = ctk.CTkFrame(self, fg_color=self.BG_CARD, corner_radius=12, width=460)
        right_panel.grid(row=0, column=2, sticky="nsew", padx=(4, 8), pady=8)
        right_panel.grid_propagate(False)
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(2, weight=1)

        header_title = ctk.CTkLabel(
            right_panel,
            text="3D 생성 서버 연결상태",
            font=("맑은 고딕", 15, "bold"),
            text_color=self.TEXT_PRIMARY,
            anchor="w",
        )
        header_title.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

        model_server_card = ctk.CTkFrame(right_panel, fg_color="#10141a", corner_radius=10)
        model_server_card.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.model_server_status_title = ctk.CTkLabel(
            model_server_card,
            text="확인 중...",
            text_color="#f59e0b",
            font=("맑은 고딕", 12, "bold"),
            anchor="w",
        )
        self.model_server_status_title.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 0))

        self.model_server_status_detail = ctk.CTkLabel(
            model_server_card,
            text="-",
            text_color=self.TEXT_MUTED,
            font=("맑은 고딕", 10),
            anchor="w",
        )
        self.model_server_status_detail.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        generation_title = ctk.CTkLabel(
            right_panel,
            text="3D 모델 생성 현황",
            font=("맑은 고딕", 15, "bold"),
            text_color=self.TEXT_PRIMARY,
            anchor="w",
        )
        generation_title.grid(row=2, column=0, sticky="nw", padx=10, pady=(0, 6))

        self.generation_grid_frame = ctk.CTkScrollableFrame(
            right_panel,
            corner_radius=10,
            fg_color="#11141a",
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
            height=360,
        )
        self.generation_grid_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(30, 10))

        for col in range(4):
            self.generation_grid_frame.columnconfigure(col, weight=1)

    def _build_parameter_editor(self, parent_widget) -> None:
        row = 0

        title = ctk.CTkLabel(
            parent_widget,
            text="3D 생성 세팅",
            font=("맑은 고딕", 18, "bold"),
            text_color=self.TEXT_PRIMARY,
        )
        title.grid(row=row, column=0, sticky="w", padx=10, pady=(8, 6))
        row += 1

        api_card = ctk.CTkFrame(parent_widget, fg_color=self.BG_CARD, corner_radius=12)
        api_card.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 8))
        api_card.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            api_card,
            text="서버 연결",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        api_entry = ctk.CTkEntry(
            api_card,
            height=32,
            fg_color=self.BG_INPUT,
            border_color=self.ACCENT,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11),
        )
        api_entry.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        self.entries["api.base_url"] = api_entry
        row += 1

        runtime_card = ctk.CTkFrame(parent_widget, fg_color=self.BG_CARD, corner_radius=12)
        runtime_card.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 8))
        runtime_card.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            runtime_card,
            text="런타임 옵션",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        runtime_fields = [
            "runtime_options.model3d_use_detected_object",
            "runtime_options.quality_check_enabled",
            "runtime_options.quality_check_strict_mode",
        ]
        for idx, key in enumerate(runtime_fields, start=1):
            row_frame = ctk.CTkFrame(runtime_card, fg_color="#1a1f27", corner_radius=8)
            row_frame.grid(row=idx, column=0, sticky="ew", padx=10, pady=3)
            row_frame.columnconfigure(0, weight=1)

            ctk.CTkLabel(
                row_frame,
                text=self.FIELD_LABELS.get(key, key),
                text_color=self.TEXT_SECONDARY,
                font=("맑은 고딕", 11, "bold"),
            ).grid(row=0, column=0, sticky="w", padx=9, pady=6)

            bool_var = tk.BooleanVar(value=False)
            switch = ctk.CTkSwitch(
                row_frame,
                text="ON",
                variable=bool_var,
                onvalue=True,
                offvalue=False,
                progress_color="#22c55e",
                button_color="#f5f7fa",
                button_hover_color="#e5e7eb",
                text_color=self.TEXT_PRIMARY,
                font=("맑은 고딕", 10, "bold"),
            )
            switch.grid(row=0, column=1, sticky="e", padx=9, pady=6)
            self.entries[key] = switch
            self.bool_vars[key] = bool_var
        row += 1

        generation_card = ctk.CTkFrame(parent_widget, fg_color=self.BG_CARD, corner_radius=12)
        generation_card.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 8))
        generation_card.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            generation_card,
            text="생성 파라미터",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        fields_grid = ctk.CTkFrame(generation_card, fg_color="transparent")
        fields_grid.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        fields_grid.columnconfigure(0, weight=1)
        fields_grid.columnconfigure(1, weight=1)

        generation_fields = [
            "generation_defaults.seed",
            "generation_defaults.ss_guidance_strength",
            "generation_defaults.ss_sampling_steps",
            "generation_defaults.slat_guidance_strength",
            "generation_defaults.slat_sampling_steps",
            "generation_defaults.mesh_simplify_ratio",
            "generation_defaults.texture_size",
            "generation_defaults.output_format",
        ]

        for idx, key in enumerate(generation_fields):
            grid_row = idx // 2
            grid_col = idx % 2

            field_card = ctk.CTkFrame(fields_grid, fg_color="#1a1f27", corner_radius=8)
            field_card.grid(row=grid_row, column=grid_col, sticky="ew", padx=3, pady=3)
            field_card.columnconfigure(0, weight=1)

            ctk.CTkLabel(
                field_card,
                text=self.FIELD_LABELS.get(key, key),
                text_color=self.TEXT_SECONDARY,
                font=("맑은 고딕", 10, "bold"),
            ).grid(row=0, column=0, sticky="w", padx=9, pady=(6, 3))

            description_text = self._generation_field_descriptions.get(key.split(".")[-1], "")
            if description_text:
                ctk.CTkLabel(
                    field_card,
                    text=description_text,
                    text_color=self.TEXT_MUTED,
                    font=("맑은 고딕", 9),
                    justify="left",
                    anchor="w",
                    wraplength=300,
                ).grid(row=1, column=0, sticky="w", padx=9, pady=(0, 4))

            entry = ctk.CTkEntry(
                field_card,
                height=30,
                fg_color=self.BG_INPUT,
                border_color=self.ACCENT,
                text_color=self.TEXT_PRIMARY,
                font=("맑은 고딕", 11),
            )
            entry.grid(row=2, column=0, sticky="ew", padx=9, pady=(0, 8))
            self.entries[key] = entry
        row += 1

        preset_frame = ctk.CTkFrame(parent_widget, fg_color=self.BG_CARD, corner_radius=12)
        preset_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctk.CTkLabel(
            preset_frame,
            text="프리셋",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_PRIMARY,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        btn_wrap = ctk.CTkFrame(preset_frame, fg_color="transparent")
        btn_wrap.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(
            btn_wrap,
            text="저품질",
            command=lambda: self._apply_preset("low"),
            width=110,
            height=32,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11, "bold"),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_wrap,
            text="일반",
            command=lambda: self._apply_preset("normal"),
            width=110,
            height=32,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11, "bold"),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_wrap,
            text="고품질",
            command=lambda: self._apply_preset("high"),
            width=110,
            height=32,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11, "bold"),
        ).pack(side="left", padx=5)
        row += 1

        button_frame = ctk.CTkFrame(parent_widget, fg_color="transparent")
        button_frame.grid(row=row, column=0, sticky="e", padx=10, pady=8)

        ctk.CTkButton(
            button_frame,
            text="새로고침",
            command=self.load_data,
            width=110,
            height=34,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11, "bold"),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            button_frame,
            text="런타임 적용",
            command=self._on_apply_clicked,
            width=130,
            height=34,
            fg_color="#374151",
            hover_color="#4b5563",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11, "bold"),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            button_frame,
            text="테스트 생성",
            command=self._on_test_generate_clicked,
            width=120,
            height=34,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11, "bold"),
        ).pack(side="left", padx=5)

        parent_widget.columnconfigure(0, weight=1)

    def load_data(self) -> None:
        params = self._load_from_runtime_api()
        if params is None:
            params = self.manager.load()

        for key, entry in self.entries.items():
            value = self._read_nested(params, key)

            if key in self.bool_vars:
                self.bool_vars[key].set(bool(value))
            else:
                entry.delete(0, tk.END)
                if value is not None:
                    entry.insert(0, str(value))

    def save_data(self) -> None:
        updated = self.manager.load()
        for key, entry in self.entries.items():
            if key in self.bool_vars:
                self._write_nested(updated, key, bool(self.bool_vars[key].get()))
            else:
                self._write_nested(updated, key, self._convert_value(entry.get().strip()))
        self._apply_to_runtime_api(updated)

    def _on_apply_clicked(self) -> None:
        try:
            self.save_data()
            messagebox.showinfo("적용 완료", "런타임 파라미터를 서버에 반영했습니다.")
            self.load_data()
        except Exception as exc:
            messagebox.showerror("적용 실패", f"런타임 반영 중 오류가 발생했습니다.\n{exc}")

    def _on_test_generate_clicked(self) -> None:
        image_path = filedialog.askopenfilename(
            title="테스트용 이미지 선택",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.avif"),
                ("All Files", "*.*"),
            ],
        )
        if not image_path:
            return

        try:
            settings = self._collect_generation_settings_from_form()
        except Exception as exc:
            messagebox.showerror("설정 오류", f"생성 파라미터 파싱에 실패했습니다.\n{exc}")
            return

        model3d_id = f"test-{int(time.time())}"
        job_id = self._start_local_generation(
            model3d_id=model3d_id,
            image_path=image_path,
            settings=settings,
        )

        worker = threading.Thread(
            target=self._run_local_test_generation,
            args=(job_id, image_path, settings),
            daemon=True,
            name="GuiLocal3DGeneration",
        )
        worker.start()

    def _collect_generation_settings_from_form(self) -> Dict[str, Any]:
        settings: Dict[str, Any] = {}
        for key in self.GENERATION_DETAIL_ORDER:
            full_key = f"generation_defaults.{key}"
            entry = self.entries.get(full_key)
            if entry is None:
                continue
            value = self._convert_value(str(entry.get()).strip())
            settings[key] = value
        return settings

    def _run_local_test_generation(self, job_id: str, image_path: str, settings: Dict[str, Any]) -> None:
        try:
            output_dir = os.path.join("uploads", "models")
            os.makedirs(output_dir, exist_ok=True)

            model_path = self.local_generator.generate_3d_model(
                image_path=image_path,
                output_dir=output_dir,
                member_id=99999,
                seed=settings.get("seed"),
                ss_guidance_strength=settings.get("ss_guidance_strength"),
                ss_sampling_steps=settings.get("ss_sampling_steps"),
                slat_guidance_strength=settings.get("slat_guidance_strength"),
                slat_sampling_steps=settings.get("slat_sampling_steps"),
                mesh_simplify_ratio=settings.get("mesh_simplify_ratio"),
                texture_size=settings.get("texture_size"),
            )

            self._update_local_generation(
                job_id,
                status="completed",
                model3d_path=model_path,
                model3d_url=f"file://{os.path.abspath(model_path)}",
                message="GUI 테스트 생성 완료",
            )

            if self.winfo_exists():
                self.after(0, lambda: messagebox.showinfo("테스트 생성 완료", f"3D 모델 생성 성공\n{model_path}"))
        except Exception as exc:
            self._update_local_generation(
                job_id,
                status="failed",
                message=f"GUI 테스트 생성 실패: {exc}",
            )
            if self.winfo_exists():
                self.after(0, lambda: messagebox.showerror("테스트 생성 실패", str(exc)))

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
        local_generations = self._get_local_generations()
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

            api_generations = overview.get("generations", [])
            generations = self._merge_generation_sources(api_generations, local_generations)
            generation_signature = self._make_generation_signature(generations)
            if generation_signature != self._last_generation_signature:
                self._render_generation_grid(generations)
                self._last_generation_signature = generation_signature

            self._poll_model_server_status_async()
        else:
            empty_connection_signature = tuple()
            empty_event_signature = tuple()
            generations = self._merge_generation_sources([], local_generations)
            generation_signature = self._make_generation_signature(generations)

            if self._last_connection_signature != empty_connection_signature:
                self._render_connection_status([])
                self._last_connection_signature = empty_connection_signature

            if self._last_event_signature != empty_event_signature:
                self._render_event_cards([])
                self._last_event_signature = empty_event_signature

            if self._last_generation_signature != generation_signature:
                self._render_generation_grid(generations)
                self._last_generation_signature = generation_signature

            self._set_model_server_status(False, "서버 상태 조회 실패")
            self._poll_model_server_status_async(force=True)

        if self.winfo_exists():
            self._mq_polling_job = self.after(2000, self._refresh_mq_panel)

    def _start_local_generation(self, model3d_id: str, image_path: str, settings: Dict[str, Any]) -> str:
        with self._local_generation_lock:
            self._local_generation_seq += 1
            job_id = f"local-gen-{self._local_generation_seq}"
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._local_generations[job_id] = {
                "job_id": job_id,
                "status": "processing",
                "member_id": "GUI_TEST",
                "model3d_id": model3d_id,
                "input_image_url": image_path,
                "input_image_urls": [image_path],
                "input_image_path": image_path,
                "model3d_path": None,
                "model3d_url": None,
                "settings": settings or {},
                "message": "GUI 테스트 생성 시작",
                "created_at": now,
                "updated_at": now,
                "source": "gui-local-test",
            }
            return job_id

    def _update_local_generation(self, job_id: str, **patch: Any) -> None:
        with self._local_generation_lock:
            item = self._local_generations.get(job_id)
            if not item:
                return
            item.update(patch)
            item["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    def _get_local_generations(self) -> List[Dict[str, Any]]:
        with self._local_generation_lock:
            items = list(self._local_generations.values())
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items[:30]

    @staticmethod
    def _merge_generation_sources(api_items: List[dict], local_items: List[dict]) -> List[dict]:
        merged: Dict[str, dict] = {}
        for item in api_items:
            job_id = str(item.get("job_id") or "")
            if job_id:
                merged[job_id] = item
        for item in local_items:
            job_id = str(item.get("job_id") or "")
            if job_id:
                merged[job_id] = item

        values = list(merged.values())
        values.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return values[:30]

    def _poll_model_server_status_async(self, force: bool = False) -> None:
        self._drain_model_server_check_results()

        if self._model_server_check_inflight:
            return

        now = time.time()
        if not force and now < self._model_server_next_check_at:
            return

        base_url = self._get_current_model_server_base_url()
        if not base_url:
            self._set_model_server_status(False, "API Base URL 미설정")
            self._model_server_next_check_at = now + (self._model_server_backoff_ms / 1000.0)
            return

        self._model_server_check_inflight = True
        threading.Thread(
            target=self._run_model_server_check,
            args=(base_url,),
            daemon=True,
            name="ModelServerHealthCheck",
        ).start()

    def _drain_model_server_check_results(self) -> None:
        while True:
            try:
                result = self._model_server_check_results.get_nowait()
            except Empty:
                break

            self._model_server_check_inflight = False
            reachable = bool(result.get("reachable", False))
            detail = str(result.get("detail", ""))
            self._set_model_server_status(reachable, detail)

            if reachable:
                self._model_server_backoff_ms = 2000
            else:
                self._model_server_backoff_ms = min(15000, self._model_server_backoff_ms + 2000)

            self._model_server_next_check_at = time.time() + (self._model_server_backoff_ms / 1000.0)

    def _run_model_server_check(self, base_url: str) -> None:
        reachable = False
        detail = base_url
        probe_urls = (base_url.rstrip("/"), f"{base_url.rstrip('/')}/health")

        for probe_url in probe_urls:
            try:
                response = requests.get(probe_url, timeout=0.6)
                reachable = True
                detail = f"{base_url} (HTTP {response.status_code})"
                break
            except Exception:
                continue

        if not reachable:
            detail = f"{base_url} (응답 없음)"

        self._model_server_check_results.put({
            "reachable": reachable,
            "detail": detail,
        })

    def _get_current_model_server_base_url(self) -> str:
        api_entry = self.entries.get("api.base_url")
        if api_entry is not None:
            try:
                value = str(api_entry.get()).strip()
                if value:
                    return value
            except Exception:
                pass

        try:
            runtime_params = self._load_from_runtime_api() or {}
            base_url = str(self._read_nested(runtime_params, "api.base_url") or "").strip()
            if base_url:
                return base_url
        except Exception:
            pass

        return str(self.manager.get_api_base_url() or "").strip()

    def _set_model_server_status(self, connected: bool, detail: str) -> None:
        status_text = "연결됨" if connected else "미연결"
        status_color = self.SUCCESS if connected else self.DANGER
        signature = (status_text, detail)
        if signature == self._last_model_server_status_signature:
            return

        self._last_model_server_status_signature = signature
        if self.model_server_status_title is not None:
            self.model_server_status_title.configure(text=status_text, text_color=status_color)
        if self.model_server_status_detail is not None:
            self.model_server_status_detail.configure(text=detail)

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

    @staticmethod
    def _make_generation_signature(generations: List[dict]):
        normalized = []
        for item in generations:
            normalized.append(
                (
                    item.get("job_id"),
                    item.get("status"),
                    item.get("updated_at"),
                    item.get("input_image_path"),
                    item.get("input_image_url"),
                    item.get("model3d_path"),
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

    def _render_generation_grid(self, generations: List[dict]) -> None:
        for child in self.generation_grid_frame.winfo_children():
            child.destroy()

        if not generations:
            ctk.CTkLabel(
                self.generation_grid_frame,
                text="아직 3D 생성 작업이 없습니다.",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 12),
                anchor="w",
            ).grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=8)
            return

        for idx, item in enumerate(generations):
            row = idx // 4
            col = idx % 4
            self._create_generation_card(self.generation_grid_frame, item, row, col)

    def _create_generation_card(self, parent, item: dict, row: int, col: int) -> None:
        status = str(item.get("status", "processing"))
        card = ctk.CTkFrame(parent, fg_color="#1a1f27", corner_radius=10)
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        card.columnconfigure(0, weight=1)

        preview_img = self._get_generation_preview_image(item)
        image_label = ctk.CTkLabel(card, text="", image=preview_img)
        image_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        if status == "processing":
            loading_label = ctk.CTkLabel(
                card,
                text="⏳ 로딩 중",
                text_color="#f8fafc",
                fg_color="#000000",
                corner_radius=6,
                font=("맑은 고딕", 10, "bold"),
            )
            loading_label.place(relx=0.5, rely=0.42, anchor="center")

        status_text = {"processing": "제작중", "completed": "완료", "failed": "실패"}.get(status, status)
        status_color = {"processing": "#f59e0b", "completed": "#22c55e", "failed": "#ef4444"}.get(status, self.TEXT_SECONDARY)

        ctk.CTkLabel(
            card,
            text=f"#{item.get('model3d_id', '-')}",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 10, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 1))

        ctk.CTkLabel(
            card,
            text=f"상태: {status_text}",
            text_color=status_color,
            font=("맑은 고딕", 10, "bold"),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 7))

        def open_detail(_event=None):
            self._show_generation_detail(item)

        for widget in card.winfo_children():
            widget.bind("<Button-1>", open_detail)
        card.bind("<Button-1>", open_detail)

    def _get_generation_preview_image(self, item: dict) -> ctk.CTkImage:
        image_path = item.get("input_image_path")
        if not image_path:
            urls = item.get("input_image_urls") or []
            if urls:
                image_path = urls[0]

        cache_key = f"{item.get('job_id')}::{image_path}"
        cached = self._generation_image_cache.get(cache_key)
        if cached is not None:
            return cached

        image_obj = None
        try:
            if image_path and os.path.exists(image_path):
                image_obj = Image.open(image_path)
            elif image_path and str(image_path).startswith("http"):
                response = requests.get(image_path, timeout=3)
                response.raise_for_status()
                from io import BytesIO
                image_obj = Image.open(BytesIO(response.content))
        except Exception:
            image_obj = None

        target_size = 96

        if image_obj is None:
            image_obj = Image.new("RGB", (target_size, target_size), color="#2a2f39")

        image_obj = image_obj.convert("RGB")
        width, height = image_obj.size
        crop_size = min(width, height)
        left = (width - crop_size) // 2
        top = (height - crop_size) // 2
        image_obj = image_obj.crop((left, top, left + crop_size, top + crop_size))
        resampling = getattr(Image, "Resampling", Image)
        image_obj = image_obj.resize((target_size, target_size), resampling.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=image_obj, dark_image=image_obj, size=(target_size, target_size))
        self._generation_image_cache[cache_key] = ctk_img
        return ctk_img

    def _show_generation_detail(self, item: dict) -> None:
        detail_window = ctk.CTkToplevel(self)
        detail_window.title(f"3D 생성 상세 - {item.get('model3d_id', '-')}")
        detail_window.geometry("860x760")
        detail_window.configure(fg_color=self.BG_PRIMARY)
        detail_window.grab_set()
        detail_window.columnconfigure(0, weight=1)
        detail_window.rowconfigure(0, weight=1)

        content = ctk.CTkScrollableFrame(
            detail_window,
            fg_color=self.BG_PRIMARY,
            corner_radius=0,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        content.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        content.columnconfigure(0, weight=1)

        preview_img = self._get_generation_preview_image(item)
        ctk.CTkLabel(content, text="원본 이미지", text_color=self.TEXT_PRIMARY, font=("맑은 고딕", 13, "bold")).pack(
            anchor="w", padx=2, pady=(0, 6)
        )
        ctk.CTkLabel(content, text="", image=preview_img).pack(anchor="w", padx=2, pady=(0, 10))

        settings = item.get("settings") or {}

        model_path = item.get("model3d_path")

        def open_external_viewer():
            if not model_path or not os.path.exists(model_path):
                messagebox.showwarning("모델 없음", "아직 3D 모델 파일이 없거나 생성 중입니다.")
                return
            try:
                launch_external_glb_viewer(model_path)
            except Exception as exc:
                messagebox.showerror("뷰어 실행 실패", f"외부 뷰어 실행 중 오류가 발생했습니다.\n{exc}")

        button_state = "normal" if model_path and os.path.exists(model_path) else "disabled"
        ctk.CTkButton(
            content,
            text="인터랙티브 3D 뷰어 열기",
            command=open_external_viewer,
            state=button_state,
            width=240,
            height=36,
            fg_color="#374151",
            hover_color="#4b5563",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 11, "bold"),
        ).pack(anchor="w", padx=2, pady=(0, 12))

        ctk.CTkLabel(content, text="생성 세팅", text_color=self.TEXT_PRIMARY, font=("맑은 고딕", 13, "bold")).pack(
            anchor="w", padx=2, pady=(0, 6)
        )

        settings_wrap = ctk.CTkFrame(content, fg_color="transparent")
        settings_wrap.pack(fill="both", expand=True)
        self._render_generation_settings_pills(settings_wrap, settings)

    def _render_generation_settings_pills(self, parent, settings: dict) -> None:
        if not settings:
            ctk.CTkLabel(
                parent,
                text="세팅 정보가 없습니다.",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 10),
                anchor="w",
            ).pack(fill="x", padx=2, pady=6)
            return

        if not isinstance(settings, dict):
            self._render_setting_row(parent, "settings", settings, 0)
            return

        ordered_top_keys = [key for key in self.GENERATION_DETAIL_ORDER if key in settings]
        for key in settings.keys():
            if key not in ordered_top_keys:
                ordered_top_keys.append(key)

        for key in ordered_top_keys:
            self._render_setting_tree(parent, key, settings.get(key), depth=0)

    def _render_setting_tree(self, parent, key: str, value, depth: int) -> None:
        if self._is_hidden_settings_key(key):
            return

        if isinstance(value, dict):
            self._render_setting_row(parent, key, f"object ({len(value)})", depth, is_group=True)
            for child_key, child_value in value.items():
                self._render_setting_tree(parent, child_key, child_value, depth + 1)
            return

        if isinstance(value, list):
            self._render_setting_row(parent, key, f"array ({len(value)})", depth, is_group=True)
            for idx, item in enumerate(value):
                self._render_setting_tree(parent, f"[{idx}]", item, depth + 1)
            return

        self._render_setting_row(parent, key, value, depth)

    @staticmethod
    def _is_hidden_settings_key(key: str) -> bool:
        normalized = str(key).lower().replace("-", "_")
        if normalized in {
            "_field_descriptions",
            "_filed_descriptions",
            "_field_descripts",
            "_filed_descripts",
            "field_descriptions",
            "filed_descriptions",
            "field_descripts",
            "filed_descripts",
        }:
            return True
        return ("field_descript" in normalized) or ("filed_descript" in normalized)

    def _load_generation_field_descriptions(self) -> dict:
        try:
            params = self.manager.load() or {}
            generation_defaults = params.get("generation_defaults", {})
            descriptions = generation_defaults.get("_field_descriptions", {})
            if isinstance(descriptions, dict):
                summarized = {}
                for key, text in descriptions.items():
                    summarized[key] = self._summarize_description_text(text)
                return summarized
        except Exception:
            pass
        return {}

    @staticmethod
    def _summarize_description_text(text: Any, max_len: int = 64) -> str:
        if text is None:
            return ""

        normalized = str(text).replace("\n", " ").strip()
        if not normalized:
            return ""

        for token in ["의미:", "높아질수록:", "낮아질수록:", "주의:", "권장"]:
            normalized = normalized.replace(token, " ")

        normalized = " ".join(normalized.split())

        for delimiter in [".", "다만", "하지만", "주의", "권장"]:
            if delimiter in normalized:
                head = normalized.split(delimiter, 1)[0].strip()
                if len(head) >= 8:
                    normalized = head
                    break

        if len(normalized) > max_len:
            normalized = normalized[: max_len - 1].rstrip() + "…"

        return normalized

    def _render_setting_row(self, parent, key: str, value, depth: int, is_group: bool = False) -> None:
        indent = 2 + (depth * 14)

        row_wrap = ctk.CTkFrame(parent, fg_color="transparent")
        row_wrap.pack(fill="x", padx=(indent, 2), pady=2)
        row_wrap.columnconfigure(0, weight=1)

        frame_color = "#171b23" if not is_group else "#1b2330"
        row_frame = ctk.CTkFrame(row_wrap, fg_color=frame_color, corner_radius=10)
        row_frame.grid(row=0, column=0, sticky="ew")
        row_frame.columnconfigure(1, weight=1)

        key_text = self.FIELD_LABELS.get(f"generation_defaults.{key}", key)
        ctk.CTkLabel(
            row_frame,
            text=key_text,
            text_color="#dbe4ff",
            font=("맑은 고딕", 9, "bold"),
            fg_color="#2c3445",
            corner_radius=999,
            height=22,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(6, 6), pady=5)

        value_color = "#243042" if is_group else "#1b2130"
        value_text_color = "#c8d4f4" if is_group else self.TEXT_PRIMARY
        ctk.CTkLabel(
            row_frame,
            text=str(value),
            text_color=value_text_color,
            font=("맑은 고딕", 9),
            fg_color=value_color,
            corner_radius=999,
            height=22,
            anchor="w",
            justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=5)

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
