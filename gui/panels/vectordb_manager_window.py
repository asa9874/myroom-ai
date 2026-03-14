import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import tkinter as tk
from tkinter import messagebox, filedialog
import threading

import customtkinter as ctk
import requests
from PIL import Image


class VectorDBManagerWindow:
    BG_PRIMARY = "#0f1013"
    BG_CARD = "#151820"
    BG_SUB = "#1a1f27"
    TEXT_PRIMARY = "#f5f7fa"
    TEXT_SECONDARY = "#b8bec9"
    TEXT_MUTED = "#8e97a7"
    ACCENT = "#2e3440"
    ACCENT_HOVER = "#3a4150"
    SUCCESS = "#22c55e"
    DANGER = "#ef4444"

    def __init__(self, parent, api_base: str = "http://127.0.0.1:5000/api"):
        self.parent = parent
        self.api_base = api_base.rstrip("/")
        self.recommendation_api = f"{self.api_base}/recommendation"
        self.mq_api = f"{self.api_base}/mq-monitor"

        self.window = ctk.CTkToplevel(parent)
        self.window.title("VectorDB 관리")
        self.window.geometry("1680x960")
        self.window.configure(fg_color=self.BG_PRIMARY)
        self.window.grab_set()
        self.window.columnconfigure(0, weight=3)
        self.window.columnconfigure(1, weight=2)
        self.window.rowconfigure(0, weight=3)
        self.window.rowconfigure(1, weight=2)

        self._poll_job = None
        self._image_cache: Dict[str, ctk.CTkImage] = {}
        self._last_meta_signature = None
        self._last_reco_signature = None

        self._metadata_items: List[Dict[str, Any]] = []
        self._recommendation_items: List[Dict[str, Any]] = []
        self._local_test_recommendations: List[Dict[str, Any]] = []
        self._local_test_reco_seq = 0
        self._status_refresh_tick = 0

        self._build_ui()
        self._refresh_all()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.left_container = ctk.CTkFrame(self.window, fg_color=self.BG_CARD, corner_radius=12)
        self.left_container.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=(10, 6))
        self.left_container.columnconfigure(0, weight=1)
        self.left_container.rowconfigure(1, weight=1)

        left_header = ctk.CTkFrame(self.left_container, fg_color="transparent")
        left_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        left_header.columnconfigure(7, weight=1)

        ctk.CTkLabel(
            left_header,
            text="VectorDB 카드 목록",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 15, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        ctk.CTkLabel(left_header, text="카테고리", text_color=self.TEXT_SECONDARY, font=("맑은 고딕", 10)).grid(
            row=0, column=1, padx=(0, 4)
        )
        self.category_var = tk.StringVar(value="전체")
        self.category_menu = ctk.CTkOptionMenu(
            left_header,
            values=["전체"],
            variable=self.category_var,
            command=lambda _v: self._render_metadata_cards(),
            width=120,
            fg_color=self.ACCENT,
            button_color=self.ACCENT,
            button_hover_color=self.ACCENT_HOVER,
        )
        self.category_menu.grid(row=0, column=2, padx=(0, 8))

        ctk.CTkLabel(left_header, text="삭제여부", text_color=self.TEXT_SECONDARY, font=("맑은 고딕", 10)).grid(
            row=0, column=3, padx=(0, 4)
        )
        self.deleted_var = tk.StringVar(value="전체")
        self.deleted_menu = ctk.CTkOptionMenu(
            left_header,
            values=["전체", "활성", "삭제"],
            variable=self.deleted_var,
            command=lambda _v: self._render_metadata_cards(),
            width=90,
            fg_color=self.ACCENT,
            button_color=self.ACCENT,
            button_hover_color=self.ACCENT_HOVER,
        )
        self.deleted_menu.grid(row=0, column=4, padx=(0, 8))

        ctk.CTkLabel(left_header, text="정렬", text_color=self.TEXT_SECONDARY, font=("맑은 고딕", 10)).grid(
            row=0, column=5, padx=(0, 4)
        )
        self.sort_var = tk.StringVar(value="최신순")
        self.sort_menu = ctk.CTkOptionMenu(
            left_header,
            values=["최신순", "오래된순", "ID순"],
            variable=self.sort_var,
            command=lambda _v: self._render_metadata_cards(),
            width=100,
            fg_color=self.ACCENT,
            button_color=self.ACCENT,
            button_hover_color=self.ACCENT_HOVER,
        )
        self.sort_menu.grid(row=0, column=6, padx=(0, 8))

        self.meta_count_label = ctk.CTkLabel(
            left_header,
            text="0건",
            text_color=self.TEXT_MUTED,
            font=("맑은 고딕", 10),
        )
        self.meta_count_label.grid(row=0, column=7, sticky="e")

        self.meta_cards_frame = ctk.CTkScrollableFrame(
            self.left_container,
            fg_color="#11141a",
            corner_radius=10,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        self.meta_cards_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        for col in range(3):
            self.meta_cards_frame.columnconfigure(col, weight=1)

        self.right_container = ctk.CTkFrame(self.window, fg_color=self.BG_CARD, corner_radius=12)
        self.right_container.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=(10, 6))
        self.right_container.columnconfigure(0, weight=1)
        self.right_container.rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.right_container,
            text="VectorDB 관리",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 15, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        button_wrap = ctk.CTkFrame(self.right_container, fg_color="transparent")
        button_wrap.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        for i in range(2):
            button_wrap.columnconfigure(i, weight=1)

        ctk.CTkButton(
            button_wrap,
            text="메타데이터 새로고침",
            command=self._refresh_metadata,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            height=34,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=4)

        ctk.CTkButton(
            button_wrap,
            text="VectorDB 상태 조회",
            command=self._refresh_status,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            height=34,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=4)

        ctk.CTkButton(
            button_wrap,
            text="VectorDB 초기화",
            command=self._reset_vectordb,
            fg_color="#b91c1c",
            hover_color="#991b1b",
            height=34,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=4)

        ctk.CTkButton(
            button_wrap,
            text="init.json 템플릿 생성",
            command=self._create_init_json_template,
            fg_color="#0f766e",
            hover_color="#115e59",
            height=34,
        ).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=4)

        self.status_text = ctk.CTkTextbox(
            self.right_container,
            fg_color="#11141a",
            text_color=self.TEXT_SECONDARY,
            font=("Consolas", 11),
            corner_radius=8,
        )
        self.status_text.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.status_text.insert("1.0", "VectorDB 관리창 초기화됨\n")
        self.status_text.configure(state="disabled")

        self.bottom_container = ctk.CTkFrame(self.window, fg_color=self.BG_CARD, corner_radius=12)
        self.bottom_container.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(6, 10))
        self.bottom_container.columnconfigure(0, weight=1)
        self.bottom_container.rowconfigure(1, weight=1)

        bottom_header = ctk.CTkFrame(self.bottom_container, fg_color="transparent")
        bottom_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        bottom_header.columnconfigure(1, weight=1)
        ctk.CTkLabel(
            bottom_header,
            text="AI 추천 기록 (MQ)",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.reco_category_var = tk.StringVar(value="미지정")
        self.reco_category_menu = ctk.CTkOptionMenu(
            bottom_header,
            values=["미지정", "chair", "table", "sofa", "bed", "cabinet", "desk", "other"],
            variable=self.reco_category_var,
            width=100,
            fg_color=self.ACCENT,
            button_color=self.ACCENT,
            button_hover_color=self.ACCENT_HOVER,
        )
        self.reco_category_menu.grid(row=0, column=1, padx=(8, 6), sticky="e")

        self.reco_topk_var = tk.StringVar(value="5")
        self.reco_topk_entry = ctk.CTkEntry(
            bottom_header,
            width=46,
            height=28,
            textvariable=self.reco_topk_var,
            fg_color="#1a1f27",
            border_color=self.ACCENT,
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 10),
        )
        self.reco_topk_entry.grid(row=0, column=2, padx=(0, 6), sticky="e")

        ctk.CTkButton(
            bottom_header,
            text="추천 테스트",
            command=self._on_run_recommendation_test,
            width=100,
            height=28,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=0, column=3, padx=(0, 8), sticky="e")

        self.reco_count_label = ctk.CTkLabel(
            bottom_header,
            text="0건",
            text_color=self.TEXT_MUTED,
            font=("맑은 고딕", 10),
        )
        self.reco_count_label.grid(row=0, column=4, sticky="e")

        self.reco_cards_frame = ctk.CTkScrollableFrame(
            self.bottom_container,
            fg_color="#11141a",
            corner_radius=10,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        self.reco_cards_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        for col in range(4):
            self.reco_cards_frame.columnconfigure(col, weight=1)

    def _on_close(self):
        if self._poll_job is not None:
            try:
                self.window.after_cancel(self._poll_job)
            except Exception:
                pass
        self.window.destroy()

    def _log_status(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}\n"
        self.status_text.configure(state="normal")
        self.status_text.insert("1.0", line)
        self.status_text.configure(state="disabled")

    def _refresh_all(self) -> None:
        self._refresh_metadata(silent=True)
        self._refresh_recommendations(silent=True)
        self._status_refresh_tick = (self._status_refresh_tick + 1) % 6
        if self._status_refresh_tick == 0:
            self._refresh_status(silent=True)
        if self.window.winfo_exists():
            self._poll_job = self.window.after(5000, self._refresh_all)

    def _refresh_metadata(self, silent: bool = False) -> None:
        try:
            response = requests.get(f"{self.recommendation_api}/metadata", params={"skip": 0, "limit": 1000}, timeout=3)
            response.raise_for_status()
            payload = response.json()
            items = payload.get("metadata_list", []) if payload.get("status") == "success" else []
            self._metadata_items = items
            self._update_category_filter_values(items)

            signature = tuple(
                (
                    item.get("index"),
                    item.get("furniture_type"),
                    item.get("filename"),
                    str((item.get("metadata") or {}).get("model3d_id")),
                    bool((item.get("metadata") or {}).get("_deleted", False)),
                )
                for item in items
            )
            if signature != self._last_meta_signature:
                self._last_meta_signature = signature
                self._render_metadata_cards()

            if not silent:
                self._log_status(f"메타데이터 새로고침 완료 ({len(items)}건)")
        except Exception as exc:
            if not silent:
                self._log_status(f"메타데이터 조회 실패: {exc}")

    def _update_category_filter_values(self, items: List[Dict[str, Any]]) -> None:
        categories = sorted({str(item.get("furniture_type") or "unknown") for item in items})
        values = ["전체"] + categories
        self.category_menu.configure(values=values)
        if self.category_var.get() not in values:
            self.category_var.set("전체")

    def _get_filtered_metadata_items(self) -> List[Dict[str, Any]]:
        items = list(self._metadata_items)

        selected_category = self.category_var.get()
        if selected_category != "전체":
            items = [item for item in items if str(item.get("furniture_type")) == selected_category]

        deleted_filter = self.deleted_var.get()
        if deleted_filter != "전체":
            should_deleted = deleted_filter == "삭제"
            items = [item for item in items if bool((item.get("metadata") or {}).get("_deleted", False)) == should_deleted]

        sort_key = self.sort_var.get()
        if sort_key == "오래된순":
            items.sort(key=lambda x: x.get("index", 0))
        elif sort_key == "ID순":
            items.sort(key=lambda x: str((x.get("metadata") or {}).get("model3d_id", "")))
        else:
            items.sort(key=lambda x: x.get("index", 0), reverse=True)

        return items

    def _render_metadata_cards(self) -> None:
        for child in self.meta_cards_frame.winfo_children():
            child.destroy()

        items = self._get_filtered_metadata_items()
        self.meta_count_label.configure(text=f"{len(items)}건")

        if not items:
            ctk.CTkLabel(
                self.meta_cards_frame,
                text="표시할 VectorDB 데이터가 없습니다.",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 11),
            ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=8)
            return

        for idx, item in enumerate(items):
            row = idx // 3
            col = idx % 3
            self._create_metadata_card(self.meta_cards_frame, item, row, col)

    def _create_metadata_card(self, parent, item: Dict[str, Any], row: int, col: int) -> None:
        card = ctk.CTkFrame(parent, fg_color=self.BG_SUB, corner_radius=10)
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        card.columnconfigure(0, weight=1)

        image_path = item.get("image_path")
        image_obj = self._get_preview_image(image_path, cache_prefix="meta")
        ctk.CTkLabel(card, text="", image=image_obj).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        metadata = item.get("metadata") or {}
        model3d_id = metadata.get("model3d_id", "-")
        name = metadata.get("name") or item.get("filename") or "(이름 없음)"
        deleted = bool(metadata.get("_deleted", False))

        ctk.CTkLabel(
            card,
            text=str(name),
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 10, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=8)

        ctk.CTkLabel(
            card,
            text=f"ID: {model3d_id}  |  idx: {item.get('index', '-')}",
            text_color=self.TEXT_SECONDARY,
            font=("맑은 고딕", 9),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=8)

        status_text = "삭제" if deleted else "활성"
        status_color = self.DANGER if deleted else self.SUCCESS
        ctk.CTkLabel(
            card,
            text=f"상태: {status_text}",
            text_color=status_color,
            font=("맑은 고딕", 9, "bold"),
            anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

        def on_click(_evt=None):
            self._show_metadata_detail(item)

        for widget in card.winfo_children():
            widget.bind("<Button-1>", on_click)
        card.bind("<Button-1>", on_click)

    def _show_metadata_detail(self, item: Dict[str, Any]) -> None:
        detail = ctk.CTkToplevel(self.window)
        detail.title(f"VectorDB 상세 - idx {item.get('index', '-')}")
        detail.geometry("760x720")
        detail.configure(fg_color=self.BG_PRIMARY)
        detail.grab_set()

        wrapper = ctk.CTkScrollableFrame(detail, fg_color=self.BG_PRIMARY)
        wrapper.pack(fill="both", expand=True, padx=10, pady=10)

        image_obj = self._get_preview_image(item.get("image_path"), cache_prefix="meta-detail", size=(280, 280))
        ctk.CTkLabel(wrapper, text="", image=image_obj).pack(anchor="w", padx=4, pady=(0, 8))

        summary = [
            ("Index", item.get("index")),
            ("Furniture Type", item.get("furniture_type")),
            ("Image Path", item.get("image_path")),
            ("Filename", item.get("filename")),
        ]

        metadata = item.get("metadata") or {}
        for key, value in summary:
            self._add_detail_pill_row(wrapper, str(key), value)

        ctk.CTkLabel(
            wrapper,
            text="메타데이터",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 13, "bold"),
        ).pack(anchor="w", padx=4, pady=(8, 6))

        for key, value in metadata.items():
            self._add_detail_pill_row(wrapper, str(key), value)

    def _refresh_status(self, silent: bool = False) -> None:
        try:
            response = requests.get(f"{self.recommendation_api}/vectordb/status", timeout=3)
            response.raise_for_status()
            payload = response.json()
            if not silent:
                vectordb = payload.get("vectordb", {})
                total_items = vectordb.get("total_items", 0)
                total_size = vectordb.get("total_size_mb", 0)
                self._log_status(f"VectorDB 상태: {total_items}건 / {total_size}MB")
        except Exception as exc:
            if not silent:
                self._log_status(f"VectorDB 상태 조회 실패: {exc}")

    def _reset_vectordb(self) -> None:
        ok = messagebox.askyesno("VectorDB 초기화", "정말 VectorDB를 초기화할까요?\n(기존 인덱스/메타데이터가 삭제됩니다)")
        if not ok:
            return

        try:
            response = requests.post(f"{self.recommendation_api}/vectordb/reset", timeout=5)
            response.raise_for_status()
            payload = response.json()
            self._log_status(f"초기화 완료: {payload.get('message', 'success')}")
            self._refresh_metadata(silent=True)
            self._refresh_status(silent=True)
        except Exception as exc:
            self._log_status(f"초기화 실패: {exc}")
            messagebox.showerror("초기화 실패", str(exc))

    def _create_init_json_template(self) -> None:
        template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "init.json"))
        payload = {
            "description": "VectorDB 초기 학습용 템플릿 - 값을 채운 뒤 배치 학습 스크립트에서 사용",
            "version": 1,
            "items": [
                {
                    "model3d_id": 1001,
                    "member_id": 1,
                    "name": "샘플 소파",
                    "description": "사용자가 작성할 설명",
                    "furniture_type": "sofa",
                    "is_shared": True,
                    "image_url": "https://example.com/images/sofa_001.jpg",
                    "extra": {
                        "category": "livingroom",
                        "tags": ["modern", "fabric"],
                        "deleted": False
                    }
                },
                {
                    "model3d_id": 1002,
                    "member_id": 2,
                    "name": "샘플 의자",
                    "description": "사용자가 작성할 설명",
                    "furniture_type": "chair",
                    "is_shared": True,
                    "image_url": "https://example.com/images/chair_001.jpg",
                    "extra": {
                        "category": "dining",
                        "tags": ["wood", "minimal"],
                        "deleted": False
                    }
                }
            ]
        }

        try:
            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._log_status(f"init.json 템플릿 생성: {template_path}")
            messagebox.showinfo("완료", f"init.json 템플릿 생성 완료\n{template_path}")
        except Exception as exc:
            self._log_status(f"init.json 생성 실패: {exc}")
            messagebox.showerror("생성 실패", str(exc))

    def _refresh_recommendations(self, silent: bool = False) -> None:
        try:
            response = requests.get(f"{self.mq_api}/overview", params={"limit": 250}, timeout=3)
            response.raise_for_status()
            payload = response.json()
            events = payload.get("events", []) if payload.get("success") else []
            mq_records = self._build_recommendation_records(events)
            records = self._merge_recommendation_records(mq_records, list(self._local_test_recommendations))
            self._recommendation_items = records

            signature = tuple(
                (
                    rec.get("id"),
                    rec.get("member_id"),
                    rec.get("status"),
                    rec.get("result_count", 0),
                    rec.get("timestamp"),
                )
                for rec in records
            )
            if signature != self._last_reco_signature:
                self._last_reco_signature = signature
                self._render_recommendation_cards()

            if not silent:
                self._log_status(f"추천 기록 갱신: {len(records)}건")
        except Exception as exc:
            if not silent:
                self._log_status(f"추천 기록 조회 실패: {exc}")

    @staticmethod
    def _merge_recommendation_records(mq_records: List[Dict[str, Any]], local_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = list(local_records) + list(mq_records)
        merged.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
        return merged[:120]

    def _on_run_recommendation_test(self) -> None:
        image_path = filedialog.askopenfilename(
            title="추천 테스트 이미지 선택",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.avif"),
                ("All Files", "*.*"),
            ],
        )
        if not image_path:
            return

        try:
            top_k = int(str(self.reco_topk_var.get()).strip() or "5")
            top_k = max(1, min(top_k, 20))
        except Exception:
            messagebox.showerror("입력 오류", "top_k는 1~20 숫자여야 합니다.")
            return

        selected_category = str(self.reco_category_var.get() or "미지정").strip() or "미지정"
        category = None if selected_category == "미지정" else selected_category

        self._local_test_reco_seq += 1
        record_id = f"test-reco-{self._local_test_reco_seq}"
        created_at = datetime.now().isoformat()
        placeholder = {
            "id": record_id,
            "member_id": "GUI_TEST",
            "status": "processing",
            "timestamp": created_at,
            "room_image_url": image_path,
            "category": selected_category,
            "top_k": top_k,
            "result_count": 0,
            "room_analysis": {},
            "recommendation": {},
            "raw": {},
            "source": "gui-local-test",
        }
        self._local_test_recommendations.insert(0, placeholder)
        self._render_recommendation_cards()

        worker = threading.Thread(
            target=self._run_recommendation_test_worker,
            args=(record_id, image_path, category, top_k),
            daemon=True,
            name="VectorDBRecoTestWorker",
        )
        worker.start()

    def _run_recommendation_test_worker(self, record_id: str, image_path: str, category: Optional[str], top_k: int) -> None:
        try:
            with open(image_path, "rb") as fp:
                files = {"file": (os.path.basename(image_path), fp, "application/octet-stream")}
                params = {
                    "top_k": top_k,
                    "member_id": 99999,
                }
                if category:
                    params["category"] = category
                response = requests.post(f"{self.recommendation_api}/analyze", files=files, params=params, timeout=120)
                response.raise_for_status()
                payload = response.json()

            status = str(payload.get("status", "unknown"))
            recommendation = payload.get("recommendation", {}) or {}
            room_analysis = payload.get("room_analysis", {}) or {}

            normalized_recommendation = {
                "targetCategory": recommendation.get("target_category", category),
                "reasoning": recommendation.get("reasoning", ""),
                "searchQuery": recommendation.get("search_query", ""),
                "results": recommendation.get("results", []) or [],
                "resultCount": recommendation.get("result_count", 0),
            }

            self._update_local_test_record(
                record_id,
                status=status,
                category=normalized_recommendation.get("targetCategory") or (category or "미지정"),
                result_count=normalized_recommendation.get("resultCount", 0),
                room_analysis=room_analysis,
                recommendation=normalized_recommendation,
                raw=payload,
                timestamp=datetime.now().isoformat(),
            )

            if self.window.winfo_exists():
                self.window.after(0, self._render_recommendation_cards)
                self.window.after(0, lambda: self._log_status(f"추천 테스트 완료: {record_id}"))

        except Exception as exc:
            self._update_local_test_record(
                record_id,
                status="failed",
                recommendation={"targetCategory": category or "미지정", "reasoning": "", "searchQuery": "", "results": [], "resultCount": 0},
                raw={"error": str(exc)},
                result_count=0,
                timestamp=datetime.now().isoformat(),
            )
            if self.window.winfo_exists():
                self.window.after(0, self._render_recommendation_cards)
                self.window.after(0, lambda: messagebox.showerror("추천 테스트 실패", str(exc)))

    def _update_local_test_record(self, record_id: str, **patch: Any) -> None:
        for item in self._local_test_recommendations:
            if item.get("id") == record_id:
                item.update(patch)
                return

    def _build_recommendation_records(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        request_by_member: Dict[str, List[Dict[str, Any]]] = {}
        records: List[Dict[str, Any]] = []
        seq = 0

        for event in reversed(events):
            queue_name = str(event.get("queue", ""))
            direction = str(event.get("direction", "")).upper()
            details = event.get("details")
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except Exception:
                    details = {}
            if not isinstance(details, dict):
                continue

            if "recommand.request" in queue_name and direction == "IN":
                member_id = str(details.get("memberId", ""))
                if not member_id:
                    continue
                request_by_member.setdefault(member_id, []).append(
                    {
                        "image_url": details.get("imageUrl"),
                        "category": details.get("category"),
                        "top_k": details.get("topK"),
                        "timestamp": event.get("timestamp"),
                    }
                )
                continue

            if "recommand.response" in queue_name and direction == "OUT":
                member_id = str(details.get("memberId", ""))
                if not member_id:
                    continue

                req_info = None
                pending = request_by_member.get(member_id, [])
                if pending:
                    req_info = pending.pop(0)

                recommendation = details.get("recommendation", {}) or {}
                results = recommendation.get("results", []) if isinstance(recommendation, dict) else []
                seq += 1
                records.append(
                    {
                        "id": f"reco-{seq}",
                        "member_id": member_id,
                        "status": details.get("status", "unknown"),
                        "timestamp": event.get("timestamp"),
                        "room_image_url": (req_info or {}).get("image_url"),
                        "category": recommendation.get("targetCategory") or (req_info or {}).get("category"),
                        "top_k": (req_info or {}).get("top_k"),
                        "result_count": recommendation.get("resultCount", len(results)),
                        "room_analysis": details.get("roomAnalysis", {}),
                        "recommendation": recommendation,
                        "raw": details,
                        "source": "mq",
                    }
                )

        records.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
        return records[:80]

    def _render_recommendation_cards(self) -> None:
        for child in self.reco_cards_frame.winfo_children():
            child.destroy()

        records = self._recommendation_items
        self.reco_count_label.configure(text=f"{len(records)}건")

        if not records:
            ctk.CTkLabel(
                self.reco_cards_frame,
                text="아직 추천 기록이 없습니다.",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 11),
            ).grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=8)
            return

        for idx, rec in enumerate(records):
            row = idx // 4
            col = idx % 4
            self._create_recommendation_card(self.reco_cards_frame, rec, row, col)

    def _create_recommendation_card(self, parent, rec: Dict[str, Any], row: int, col: int) -> None:
        card = ctk.CTkFrame(parent, fg_color=self.BG_SUB, corner_radius=10)
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        card.columnconfigure(0, weight=1)

        image_obj = self._get_preview_image(rec.get("room_image_url"), cache_prefix="reco")
        ctk.CTkLabel(card, text="", image=image_obj).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            card,
            text=f"member: {rec.get('member_id', '-')}",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 10, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=8)

        ctk.CTkLabel(
            card,
            text=f"cat: {rec.get('category', '-')}",
            text_color=self.TEXT_SECONDARY,
            font=("맑은 고딕", 9),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=8)

        ctk.CTkLabel(
            card,
            text=f"추천개수: {rec.get('result_count', 0)}",
            text_color=self.TEXT_SECONDARY,
            font=("맑은 고딕", 9),
            anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

        if rec.get("source") == "gui-local-test":
            ctk.CTkLabel(
                card,
                text="TEST",
                text_color="#f8fafc",
                fg_color="#2563eb",
                corner_radius=6,
                font=("맑은 고딕", 9, "bold"),
            ).place(relx=0.93, rely=0.08, anchor="ne")

        def on_click(_evt=None):
            self._show_recommendation_detail(rec)

        for widget in card.winfo_children():
            widget.bind("<Button-1>", on_click)
        card.bind("<Button-1>", on_click)

    def _show_recommendation_detail(self, rec: Dict[str, Any]) -> None:
        detail = ctk.CTkToplevel(self.window)
        detail.title(f"추천 상세 - member {rec.get('member_id', '-')}")
        detail.geometry("1180x820")
        detail.configure(fg_color=self.BG_PRIMARY)
        detail.grab_set()
        detail.columnconfigure(0, weight=0)
        detail.columnconfigure(1, weight=1)
        detail.rowconfigure(0, weight=1)

        left = ctk.CTkFrame(detail, fg_color=self.BG_CARD, corner_radius=10, width=360)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        left.grid_propagate(False)

        right = ctk.CTkFrame(detail, fg_color=self.BG_CARD, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        room_img = self._get_preview_image(rec.get("room_image_url"), cache_prefix="reco-detail", size=(300, 300))
        ctk.CTkLabel(left, text="방 사진", text_color=self.TEXT_PRIMARY, font=("맑은 고딕", 13, "bold")).pack(
            anchor="w", padx=10, pady=(10, 6)
        )
        ctk.CTkLabel(left, text="", image=room_img).pack(anchor="w", padx=10, pady=(0, 8))

        self._add_detail_pill_row(left, "memberId", rec.get("member_id"))
        self._add_detail_pill_row(left, "category", rec.get("category"))
        self._add_detail_pill_row(left, "추천개수", rec.get("result_count"))
        self._add_detail_pill_row(left, "timestamp", rec.get("timestamp"))

        room_analysis = rec.get("room_analysis", {}) or {}
        recommendation = rec.get("recommendation", {}) or {}
        ctk.CTkLabel(
            right,
            text="Room Analysis & Query",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 14, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))

        analysis_frame = ctk.CTkScrollableFrame(
            right,
            fg_color="#11141a",
            corner_radius=10,
            height=190,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        analysis_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        self._add_detail_pill_row(analysis_frame, "style", room_analysis.get("style"))
        self._add_detail_pill_row(analysis_frame, "color", room_analysis.get("color"))
        self._add_detail_pill_row(analysis_frame, "material", room_analysis.get("material"))
        self._add_detail_pill_row(analysis_frame, "detectedCount", room_analysis.get("detectedCount"))
        self._add_detail_pill_row(analysis_frame, "detectedFurniture", room_analysis.get("detectedFurniture"))
        self._add_detail_pill_row(analysis_frame, "reasoning", recommendation.get("reasoning"))
        self._add_detail_pill_row(analysis_frame, "searchQuery", recommendation.get("searchQuery"))

        ctk.CTkLabel(
            right,
            text="추천에 사용된 가구 (VectorDB)",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 14, "bold"),
        ).grid(row=2, column=0, sticky="nw", padx=10, pady=(0, 6))

        reco_cards = ctk.CTkScrollableFrame(
            right,
            fg_color="#11141a",
            corner_radius=10,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        reco_cards.grid(row=2, column=0, sticky="nsew", padx=10, pady=(30, 10))
        for col in range(3):
            reco_cards.columnconfigure(col, weight=1)

        results = recommendation.get("results", [])
        if not results:
            ctk.CTkLabel(
                reco_cards,
                text="추천 결과가 없습니다.",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 11),
            ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=8)
            return

        for idx, result in enumerate(results):
            row = idx // 3
            col = idx % 3
            self._create_result_furniture_card(reco_cards, result, row, col)

    def _create_result_furniture_card(self, parent, result: Dict[str, Any], row: int, col: int) -> None:
        card = ctk.CTkFrame(parent, fg_color=self.BG_SUB, corner_radius=10)
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        card.columnconfigure(0, weight=1)

        image_path = result.get("image_path")
        image_obj = self._get_preview_image(image_path, cache_prefix="reco-item")
        ctk.CTkLabel(card, text="", image=image_obj).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        model3d_id = result.get("model3d_id", "-")
        ctk.CTkLabel(
            card,
            text=str(result.get("filename") or f"model {model3d_id}"),
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 10, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=8)

        ctk.CTkLabel(
            card,
            text=f"ID: {model3d_id}",
            text_color=self.TEXT_SECONDARY,
            font=("맑은 고딕", 9),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=8)

        ctk.CTkLabel(
            card,
            text=f"score: {result.get('score', 0):.3f}",
            text_color=self.TEXT_SECONDARY,
            font=("맑은 고딕", 9),
            anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

        def on_click(_evt=None):
            matched = self._find_metadata_by_model3d_id(model3d_id)
            if matched:
                self._show_metadata_detail(matched)
            else:
                messagebox.showinfo("정보", f"model3d_id={model3d_id} 메타데이터를 찾지 못했습니다.")

        for widget in card.winfo_children():
            widget.bind("<Button-1>", on_click)
        card.bind("<Button-1>", on_click)

    def _find_metadata_by_model3d_id(self, model3d_id: Any) -> Optional[Dict[str, Any]]:
        target = str(model3d_id)
        for item in self._metadata_items:
            metadata = item.get("metadata") or {}
            if str(metadata.get("model3d_id")) == target:
                return item
        return None

    def _add_detail_pill_row(self, parent, key: str, value: Any) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=3)
        row.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row,
            text=str(key),
            text_color="#dbe4ff",
            fg_color="#2c3445",
            corner_radius=999,
            font=("맑은 고딕", 9, "bold"),
            height=24,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))

        ctk.CTkLabel(
            row,
            text=str(value),
            text_color=self.TEXT_PRIMARY,
            fg_color="#1b2130",
            corner_radius=999,
            font=("맑은 고딕", 9),
            height=24,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew")

    def _get_preview_image(self, image_path: Optional[str], cache_prefix: str, size=(96, 96)) -> ctk.CTkImage:
        key = f"{cache_prefix}:{image_path}:{size[0]}x{size[1]}"
        if key in self._image_cache:
            return self._image_cache[key]

        image_obj = None
        try:
            if image_path and str(image_path).startswith("http"):
                response = requests.get(str(image_path), timeout=3)
                response.raise_for_status()
                from io import BytesIO
                image_obj = Image.open(BytesIO(response.content))
            elif image_path and os.path.exists(str(image_path)):
                image_obj = Image.open(str(image_path))
        except Exception:
            image_obj = None

        if image_obj is None:
            image_obj = Image.new("RGB", size, color="#2a2f39")

        image_obj = image_obj.convert("RGB")
        width, height = image_obj.size
        crop = min(width, height)
        left = (width - crop) // 2
        top = (height - crop) // 2
        image_obj = image_obj.crop((left, top, left + crop, top + crop))
        resampling = getattr(Image, "Resampling", Image)
        image_obj = image_obj.resize(size, resampling.LANCZOS)

        ctk_img = ctk.CTkImage(light_image=image_obj, dark_image=image_obj, size=size)
        self._image_cache[key] = ctk_img
        return ctk_img
