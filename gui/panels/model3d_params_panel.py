import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict
import requests

from app.utils.model3d_params import Model3DParameterManager
from .base_panel import BaseSettingsPanel


class ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self._show)
        self.widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            relief="solid",
            borderwidth=1,
            font=("맑은 고딕", 9)
        )
        label.pack(ipadx=6, ipady=4)

    def _hide(self, _event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class Model3DParametersPanel(BaseSettingsPanel):
    panel_title = "3D Params"
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
        self.entries: Dict[str, tk.Entry] = {}
        self.help_labels: Dict[str, tk.Label] = {}
        self.tooltips = []
        self.canvas = None
        self.scrollbar = None
        self.content_frame = None
        self._canvas_window_id = None
        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.content_frame = ttk.Frame(self.canvas)
        self._canvas_window_id = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        self.content_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

        parent_widget = self.content_frame
        row = 0

        title = ttk.Label(parent_widget, text="3D 모델 생성 파라미터", font=("맑은 고딕", 11, "bold"))
        title.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))
        row += 1

        sections = [
            ("API", [("api.base_url", "API Base URL")]),
            ("Quality Thresholds", [
                ("quality_thresholds.minimum", "Minimum"),
                ("quality_thresholds.standard", "Standard"),
                ("quality_thresholds.premium", "Premium"),
            ]),
            ("Generation Defaults", [
                ("generation_defaults.seed", "Seed"),
                ("generation_defaults.ss_guidance_strength", "SS Guidance"),
                ("generation_defaults.ss_sampling_steps", "SS Steps"),
                ("generation_defaults.slat_guidance_strength", "SLAT Guidance"),
                ("generation_defaults.slat_sampling_steps", "SLAT Steps"),
                ("generation_defaults.mesh_simplify_ratio", "Mesh Simplify Ratio"),
                ("generation_defaults.texture_size", "Texture Size"),
                ("generation_defaults.output_format", "Output Format"),
            ]),
        ]

        for section_title, fields in sections:
            section = ttk.Label(parent_widget, text=section_title, font=("맑은 고딕", 10, "bold"))
            section.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 4))
            row += 1

            for key, label in fields:
                label_widget = ttk.Label(parent_widget, text=label)
                label_widget.grid(row=row, column=0, sticky="w", padx=10, pady=3)
                entry = ttk.Entry(parent_widget, width=45)
                entry.grid(row=row, column=1, sticky="we", padx=10, pady=3)
                self.entries[key] = entry

                description = self._get_field_description(key)
                if description:
                    help_label = tk.Label(
                        parent_widget,
                        text=description,
                        anchor="w",
                        justify="left",
                        wraplength=620,
                        font=("맑은 고딕", 8)
                    )
                    help_label.grid(row=row + 1, column=1, sticky="w", padx=10, pady=(0, 4))
                    self.help_labels[key] = help_label
                    self.tooltips.append(ToolTip(label_widget, description))
                    self.tooltips.append(ToolTip(entry, description))
                    row += 2
                else:
                    row += 1

        preset_frame = ttk.LabelFrame(parent_widget, text="프리셋")
        preset_frame.grid(row=row, column=0, columnspan=2, sticky="we", padx=10, pady=(8, 6))
        ttk.Button(preset_frame, text="저품질", command=lambda: self._apply_preset("low")).pack(side="left", padx=8, pady=8)
        ttk.Button(preset_frame, text="일반", command=lambda: self._apply_preset("normal")).pack(side="left", padx=8, pady=8)
        ttk.Button(preset_frame, text="고품질", command=lambda: self._apply_preset("high")).pack(side="left", padx=8, pady=8)
        row += 1

        button_frame = ttk.Frame(parent_widget)
        button_frame.grid(row=row, column=0, columnspan=2, sticky="e", padx=10, pady=10)

        ttk.Button(button_frame, text="새로고침", command=self.load_data).pack(side="left", padx=5)
        ttk.Button(button_frame, text="런타임 적용", command=self._on_apply_clicked).pack(side="left", padx=5)

        parent_widget.columnconfigure(1, weight=1)

    def _on_frame_configure(self, _event=None) -> None:
        if self.canvas is not None:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        if self.canvas is not None and self._canvas_window_id is not None:
            self.canvas.itemconfigure(self._canvas_window_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if self.canvas is None:
            return
        delta = event.delta
        if delta == 0:
            return
        self.canvas.yview_scroll(int(-delta / 120), "units")

    def _bind_mousewheel(self, _event=None) -> None:
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None) -> None:
        self.unbind_all("<MouseWheel>")

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
                help_label.config(text=self._get_field_description(key, params))

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

