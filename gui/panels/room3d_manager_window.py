import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import requests


class Room3DManagerWindow:
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

    QUEUE_DISPLAY_NAMES = {
        "room3d.request.queue": "Room3D 요청 큐",
        "room3d.response.queue": "Room3D 응답 큐",
        "room3d.request": "Room3D 요청 라우팅키",
        "room3d.response": "Room3D 응답 라우팅키",
    }

    def __init__(self, parent, api_base: str = "http://127.0.0.1:5000/api"):
        self.parent = parent
        self.api_base = api_base.rstrip("/")
        self.room3d_api = f"{self.api_base}/room3d"

        self.window = ctk.CTkToplevel(parent)
        self.window.title("Room3D 관리")
        self.window.geometry("1640x960")
        self.window.configure(fg_color=self.BG_PRIMARY)
        self.window.grab_set()
        self.window.columnconfigure(0, weight=3)
        self.window.columnconfigure(1, weight=2)
        self.window.rowconfigure(0, weight=1)

        self._poll_job = None
        self._last_connection_signature = None
        self._last_event_signature = None
        self._connection_items: List[Dict[str, Any]] = []
        self._event_items: List[Dict[str, Any]] = []

        self.req_room3d_id_var = tk.StringVar(value="1001")
        self.req_member_id_var = tk.StringVar(value="5")
        self.req_image_url_var = tk.StringVar(
            value="https://asa-room.s3.amazonaws.com/room3d/images/sample-drawing.png"
        )
        self.req_room_name_var = tk.StringVar(value="안방")
        self.req_description_var = tk.StringVar(value="붙박이장이 있는 안방")

        self.res_room3d_id_var = tk.StringVar(value="1001")
        self.res_member_id_var = tk.StringVar(value="5")
        self.res_status_var = tk.StringVar(value="SUCCESS")
        self.res_message_var = tk.StringVar(value="completed")

        self.contract_text = None
        self.status_text = None
        self.connection_frame = None
        self.event_frame = None

        self._build_ui()
        self._refresh_contract()
        self._refresh_overview(silent=True)

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_poll()

    def _build_ui(self) -> None:
        left = ctk.CTkFrame(self.window, fg_color=self.BG_CARD, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

        right = ctk.CTkFrame(self.window, fg_color=self.BG_CARD, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        ctk.CTkLabel(
            left,
            text="Room3D MQ 테스트",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 18, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        request_card = ctk.CTkFrame(left, fg_color=self.BG_SUB, corner_radius=10)
        request_card.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        request_card.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            request_card,
            text="요청 메시지 발행",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 13, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6))

        self._build_form_row(request_card, 1, "room3dId", self.req_room3d_id_var)
        self._build_form_row(request_card, 2, "memberId", self.req_member_id_var)
        self._build_form_row(request_card, 3, "drawingImageUrl", self.req_image_url_var)
        self._build_form_row(request_card, 4, "roomName", self.req_room_name_var)
        self._build_form_row(request_card, 5, "description", self.req_description_var)

        req_btn_wrap = ctk.CTkFrame(request_card, fg_color="transparent")
        req_btn_wrap.grid(row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 10))
        req_btn_wrap.columnconfigure(0, weight=1)
        req_btn_wrap.columnconfigure(1, weight=1)

        ctk.CTkButton(
            req_btn_wrap,
            text="요청 MQ 발행",
            command=self._publish_request,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            text_color=self.TEXT_PRIMARY,
            height=34,
            font=("맑은 고딕", 11, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            req_btn_wrap,
            text="계약정보 새로고침",
            command=self._refresh_contract,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            height=34,
            font=("맑은 고딕", 11, "bold"),
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        response_card = ctk.CTkFrame(left, fg_color=self.BG_SUB, corner_radius=10)
        response_card.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        response_card.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            response_card,
            text="응답 메시지 발행",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 13, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6))

        self._build_form_row(response_card, 1, "room3dId", self.res_room3d_id_var)
        self._build_form_row(response_card, 2, "memberId", self.res_member_id_var)

        ctk.CTkLabel(
            response_card,
            text="status",
            text_color=self.TEXT_SECONDARY,
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=3, column=0, sticky="w", padx=10, pady=4)

        status_menu = ctk.CTkOptionMenu(
            response_card,
            values=["SUCCESS", "FAILED"],
            variable=self.res_status_var,
            fg_color=self.ACCENT,
            button_color=self.ACCENT,
            button_hover_color=self.ACCENT_HOVER,
            text_color=self.TEXT_PRIMARY,
            height=30,
        )
        status_menu.grid(row=3, column=1, sticky="ew", padx=(0, 10), pady=4)

        self._build_form_row(response_card, 4, "message", self.res_message_var)

        ctk.CTkLabel(
            response_card,
            text="SUCCESS 시 xmlFileUrl은 자동으로 \"이 텍스트는 임시텍스트입니다.\" 로 발행됩니다.",
            text_color=self.TEXT_MUTED,
            font=("맑은 고딕", 10),
            wraplength=780,
            justify="left",
            anchor="w",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 8))

        ctk.CTkButton(
            response_card,
            text="응답 MQ 발행",
            command=self._publish_response,
            fg_color="#0f766e",
            hover_color="#115e59",
            text_color=self.TEXT_PRIMARY,
            height=34,
            font=("맑은 고딕", 11, "bold"),
        ).grid(row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        contract_card = ctk.CTkFrame(left, fg_color=self.BG_SUB, corner_radius=10)
        contract_card.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        contract_card.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            contract_card,
            text="계약 요약",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 13, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        self.contract_text = ctk.CTkTextbox(
            contract_card,
            height=88,
            fg_color="#11141a",
            text_color=self.TEXT_SECONDARY,
            font=("Consolas", 11),
            corner_radius=8,
        )
        self.contract_text.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            left,
            text="실행 로그",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 13, "bold"),
        ).grid(row=4, column=0, sticky="nw", padx=12, pady=(0, 6))

        self.status_text = ctk.CTkTextbox(
            left,
            fg_color="#11141a",
            text_color=self.TEXT_SECONDARY,
            font=("Consolas", 11),
            corner_radius=8,
        )
        self.status_text.grid(row=4, column=0, sticky="nsew", padx=12, pady=(28, 12))
        self.status_text.insert("1.0", "Room3D 관리창 초기화됨\n")
        self.status_text.configure(state="disabled")

        ctk.CTkLabel(
            right,
            text="Room3D MQ 연결 상태",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 15, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        self.connection_frame = ctk.CTkFrame(right, fg_color="#11141a", corner_radius=10)
        self.connection_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        ctk.CTkLabel(
            right,
            text="Room3D MQ 이벤트",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 15, "bold"),
        ).grid(row=2, column=0, sticky="nw", padx=10, pady=(0, 6))

        self.event_frame = ctk.CTkScrollableFrame(
            right,
            fg_color="#11141a",
            corner_radius=10,
            scrollbar_button_color=self.ACCENT,
            scrollbar_button_hover_color=self.ACCENT_HOVER,
        )
        self.event_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(30, 10))

    def _build_form_row(self, parent, row_index: int, label: str, variable: tk.StringVar) -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=self.TEXT_SECONDARY,
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=row_index, column=0, sticky="w", padx=10, pady=4)

        ctk.CTkEntry(
            parent,
            textvariable=variable,
            fg_color="#11141a",
            border_color=self.ACCENT,
            text_color=self.TEXT_PRIMARY,
            height=30,
            font=("맑은 고딕", 10),
        ).grid(row=row_index, column=1, sticky="ew", padx=(0, 10), pady=4)

    def _on_close(self) -> None:
        if self._poll_job is not None:
            try:
                self.window.after_cancel(self._poll_job)
            except Exception:
                pass
        self.window.destroy()

    def _schedule_poll(self) -> None:
        if not self.window.winfo_exists():
            return
        self._poll_job = self.window.after(3000, self._poll_tick)

    def _poll_tick(self) -> None:
        self._refresh_overview(silent=True)
        self._schedule_poll()

    def _log_status(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}\n"
        self.status_text.configure(state="normal")
        self.status_text.insert("1.0", line)
        self.status_text.configure(state="disabled")

    def _coerce_int(self, value: Any, default_value: int) -> int:
        try:
            return int(str(value).strip())
        except Exception:
            return int(default_value)

    def _refresh_contract(self) -> None:
        try:
            response = requests.get(f"{self.room3d_api}/contract", timeout=3)
            response.raise_for_status()
            payload = response.json()
            lines = [
                f"exchange: {payload.get('exchange', '-')}",
                f"request: {payload.get('requestQueue', '-')} ({payload.get('requestRoutingKey', '-')})",
                f"response: {payload.get('responseQueue', '-')} ({payload.get('responseRoutingKey', '-')})",
                f"placeholder: {payload.get('placeholderXmlText', '-')}",
            ]
            self.contract_text.delete("1.0", "end")
            self.contract_text.insert("1.0", "\n".join(lines))
            self._log_status("Room3D 계약 정보를 갱신했습니다.")
        except Exception as exc:
            self._log_status(f"계약 정보 조회 실패: {exc}")

    def _refresh_overview(self, silent: bool = False) -> None:
        try:
            response = requests.get(f"{self.room3d_api}/overview", params={"limit": 200}, timeout=3)
            response.raise_for_status()
            payload = response.json()
            connections = payload.get("connections", []) if payload.get("success") else []
            events = payload.get("events", []) if payload.get("success") else []

            connection_signature = tuple(
                (str(item.get("queue")), bool(item.get("connected")), str(item.get("updated_at")))
                for item in connections
            )
            event_signature = tuple(
                (str(item.get("id")), str(item.get("queue")), str(item.get("direction")), str(item.get("timestamp")))
                for item in events
            )

            self._connection_items = connections
            self._event_items = events

            if connection_signature != self._last_connection_signature:
                self._last_connection_signature = connection_signature
                self._render_connections()

            if event_signature != self._last_event_signature:
                self._last_event_signature = event_signature
                self._render_events()

            if not silent:
                self._log_status(f"Room3D 이벤트 갱신: {len(events)}건")
        except Exception as exc:
            if not silent:
                self._log_status(f"Room3D overview 조회 실패: {exc}")

    def _render_connections(self) -> None:
        for child in self.connection_frame.winfo_children():
            child.destroy()

        connection_map = {str(item.get("queue", "")): item for item in self._connection_items}
        expected = ["room3d.request.queue", "room3d.response.queue"]

        for row, queue_name in enumerate(expected):
            item = connection_map.get(queue_name, {})
            connected = bool(item.get("connected", False))
            component = item.get("component", "-")
            detail = item.get("detail", "")

            row_frame = ctk.CTkFrame(self.connection_frame, fg_color="transparent")
            row_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=4)
            row_frame.columnconfigure(1, weight=1)

            dot_color = self.SUCCESS if connected else self.DANGER
            dot = ctk.CTkLabel(row_frame, text="", width=12, height=12, fg_color=dot_color, corner_radius=999)
            dot.grid(row=0, column=0, padx=(0, 8), pady=2)

            queue_display = self.QUEUE_DISPLAY_NAMES.get(queue_name, queue_name)
            status_text = "연결됨" if connected else "미연결"
            ctk.CTkLabel(
                row_frame,
                text=f"{queue_display} | {status_text}",
                text_color=self.TEXT_PRIMARY,
                font=("맑은 고딕", 11, "bold"),
                anchor="w",
            ).grid(row=0, column=1, sticky="w")

            ctk.CTkLabel(
                row_frame,
                text=f"component={component}  {detail}",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 9),
                anchor="w",
            ).grid(row=1, column=1, sticky="w")

    def _render_events(self) -> None:
        for child in self.event_frame.winfo_children():
            child.destroy()

        if not self._event_items:
            ctk.CTkLabel(
                self.event_frame,
                text="Room3D 이벤트가 아직 없습니다.",
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 11),
            ).pack(anchor="w", padx=8, pady=8)
            return

        for event in self._event_items:
            card = ctk.CTkFrame(self.event_frame, fg_color=self.BG_SUB, corner_radius=10)
            card.pack(fill="x", padx=6, pady=5)
            card.columnconfigure(1, weight=1)

            direction = str(event.get("direction", "-")).upper()
            queue_name = str(event.get("queue", ""))
            queue_display = self.QUEUE_DISPLAY_NAMES.get(queue_name, queue_name)

            chip_color = "#2563eb" if direction == "OUT" else "#0f766e"
            ctk.CTkLabel(
                card,
                text=direction,
                text_color="#f8fafc",
                fg_color=chip_color,
                corner_radius=6,
                font=("맑은 고딕", 9, "bold"),
                width=38,
            ).grid(row=0, column=0, sticky="nw", padx=(10, 8), pady=(10, 4))

            ctk.CTkLabel(
                card,
                text=queue_display,
                text_color=self.TEXT_PRIMARY,
                font=("맑은 고딕", 11, "bold"),
                anchor="w",
            ).grid(row=0, column=1, sticky="w", pady=(10, 2))

            summary = self._format_event_summary(event)
            ctk.CTkLabel(
                card,
                text=summary,
                text_color=self.TEXT_SECONDARY,
                font=("맑은 고딕", 10),
                anchor="w",
                justify="left",
                wraplength=500,
            ).grid(row=1, column=1, sticky="w", pady=(0, 4))

            ctk.CTkLabel(
                card,
                text=str(event.get("timestamp", "")),
                text_color=self.TEXT_MUTED,
                font=("맑은 고딕", 9),
                anchor="w",
            ).grid(row=2, column=1, sticky="w", pady=(0, 10))

            def on_click(_evt=None, item=event):
                self._show_event_detail(item)

            for widget in card.winfo_children():
                widget.bind("<Button-1>", on_click)
            card.bind("<Button-1>", on_click)

    def _format_event_summary(self, event: Dict[str, Any]) -> str:
        details = event.get("details")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                return details[:180]

        if not isinstance(details, dict):
            return "-"

        queue_name = str(event.get("queue", ""))
        if "request" in queue_name:
            return (
                f"room3dId={details.get('room3dId')}  "
                f"memberId={details.get('memberId')}  "
                f"roomName={details.get('roomName', '-') }"
            )

        return (
            f"room3dId={details.get('room3dId')}  "
            f"status={details.get('status')}  "
            f"xmlFileUrl={details.get('xmlFileUrl')}"
        )

    def _show_event_detail(self, event: Dict[str, Any]) -> None:
        detail = ctk.CTkToplevel(self.window)
        detail.title("Room3D 이벤트 상세")
        detail.geometry("920x700")
        detail.configure(fg_color=self.BG_PRIMARY)
        detail.grab_set()

        ctk.CTkLabel(
            detail,
            text=f"{event.get('timestamp', '')} | {event.get('queue', '')}",
            text_color=self.TEXT_PRIMARY,
            font=("맑은 고딕", 13, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 8))

        textbox = ctk.CTkTextbox(
            detail,
            fg_color="#11141a",
            text_color=self.TEXT_SECONDARY,
            font=("Consolas", 11),
            corner_radius=8,
        )
        textbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        details = event.get("details")
        try:
            rendered = json.dumps(details, ensure_ascii=False, indent=2)
        except Exception:
            rendered = str(details)

        textbox.insert("1.0", rendered)

    def _publish_request(self) -> None:
        payload = {
            "room3dId": self._coerce_int(self.req_room3d_id_var.get(), 1001),
            "memberId": self._coerce_int(self.req_member_id_var.get(), 1),
            "drawingImageUrl": str(self.req_image_url_var.get()).strip(),
            "roomName": str(self.req_room_name_var.get()).strip(),
            "description": str(self.req_description_var.get()).strip() or None,
        }

        if not payload["drawingImageUrl"] or not payload["roomName"]:
            messagebox.showerror("입력 오류", "drawingImageUrl, roomName은 필수입니다.")
            return

        try:
            response = requests.post(f"{self.room3d_api}/test/publish-request", json=payload, timeout=5)
            response.raise_for_status()
            body = response.json()
            self._log_status(
                f"요청 발행 완료 room3dId={payload['room3dId']} memberId={payload['memberId']}"
            )
            self.res_room3d_id_var.set(str(payload["room3dId"]))
            self.res_member_id_var.set(str(payload["memberId"]))
            self._refresh_overview(silent=True)
            messagebox.showinfo("요청 발행 완료", body.get("message", "success"))
        except Exception as exc:
            self._log_status(f"요청 발행 실패: {exc}")
            messagebox.showerror("요청 발행 실패", str(exc))

    def _publish_response(self) -> None:
        payload = {
            "room3dId": self._coerce_int(self.res_room3d_id_var.get(), 1001),
            "memberId": self._coerce_int(self.res_member_id_var.get(), 1),
            "status": str(self.res_status_var.get()).upper(),
            "message": str(self.res_message_var.get()).strip() or "completed",
        }

        try:
            response = requests.post(f"{self.room3d_api}/test/publish-response", json=payload, timeout=5)
            response.raise_for_status()
            body = response.json()
            self._log_status(
                f"응답 발행 완료 room3dId={body.get('room3dId')} status={body.get('status')} xmlFileUrl={body.get('xmlFileUrl')}"
            )
            self._refresh_overview(silent=True)
            messagebox.showinfo("응답 발행 완료", "Room3D 응답 메시지를 발행했습니다.")
        except Exception as exc:
            self._log_status(f"응답 발행 실패: {exc}")
            messagebox.showerror("응답 발행 실패", str(exc))
