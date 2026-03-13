import os
import tkinter as tk
from typing import Optional

import customtkinter as ctk
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    Filename,
    MouseButton,
    NodePath,
    WindowProperties,
    loadPrcFileData,
)

loadPrcFileData('', 'window-type none')
loadPrcFileData('', 'audio-library-name null')


class _PandaApp(ShowBase):
    def __init__(self):
        super().__init__(windowType='none')
        self.disableMouse()


class GLBOpenGLViewer(ctk.CTkFrame):
    _app: Optional[_PandaApp] = None

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(fg_color="#11141a")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.status_label = ctk.CTkLabel(
            self,
            text="모델 파일을 불러오면 Panda3D로 렌더링됩니다.",
            font=("맑은 고딕", 11),
            text_color="#aab3c2",
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        control_bar = ctk.CTkFrame(self, fg_color="#1a1f27", corner_radius=8)
        control_bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        ctk.CTkButton(control_bar, text="◀", width=36, height=28, command=lambda: self._rotate(yaw_delta=-8)).pack(side="left", padx=(8, 4), pady=6)
        ctk.CTkButton(control_bar, text="▶", width=36, height=28, command=lambda: self._rotate(yaw_delta=8)).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(control_bar, text="▲", width=36, height=28, command=lambda: self._rotate(pitch_delta=-6)).pack(side="left", padx=(10, 4), pady=6)
        ctk.CTkButton(control_bar, text="▼", width=36, height=28, command=lambda: self._rotate(pitch_delta=6)).pack(side="left", padx=4, pady=6)

        ctk.CTkButton(control_bar, text="＋", width=36, height=28, command=lambda: self._zoom(-0.35)).pack(side="right", padx=(4, 8), pady=6)
        ctk.CTkButton(control_bar, text="－", width=36, height=28, command=lambda: self._zoom(0.35)).pack(side="right", padx=4, pady=6)

        ctk.CTkLabel(
            control_bar,
            text="드래그 회전 · 휠 줌",
            font=("맑은 고딕", 10),
            text_color="#aab3c2",
        ).pack(side="right", padx=(0, 10))

        self._embed_container = tk.Frame(self, bg="#11141a", highlightthickness=0, bd=0)
        self._embed_container.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

        self._window = None
        self._interaction_job = None
        self._destroyed = False
        self._camera_np = None
        self._camera_distance = 3.0
        self._orbit_yaw = 20.0
        self._orbit_pitch = -15.0
        self._drag_last = None
        self._last_panda_mouse = None
        self._model_np: Optional[NodePath] = None
        self._lights_attached = False
        self._panda_ready = False

        self._embed_container.bind("<Configure>", self._on_resize)
        self._embed_container.bind("<ButtonPress-1>", self._on_drag_start)
        self._embed_container.bind("<B1-Motion>", self._on_drag_move)
        self._embed_container.bind("<MouseWheel>", self._on_mouse_wheel)
        self._embed_container.bind("<Button-4>", lambda _e: self._zoom(-0.25))
        self._embed_container.bind("<Button-5>", lambda _e: self._zoom(0.25))

        self.bind("<Destroy>", self._on_destroy)
        self.after(50, self._init_panda_embed)

    @classmethod
    def _get_app(cls) -> _PandaApp:
        if cls._app is None:
            cls._app = _PandaApp()
        return cls._app

    def _init_panda_embed(self):
        if self._panda_ready or not self.winfo_exists():
            return

        app = self._get_app()
        width = max(1, self._embed_container.winfo_width())
        height = max(1, self._embed_container.winfo_height())

        wp = WindowProperties()
        wp.setParentWindow(self._embed_container.winfo_id())
        wp.setOrigin(0, 0)
        wp.setSize(width, height)

        self._window = app.openWindow(props=wp, makeCamera=False, requireWindow=True)
        if self._window is None:
            self.status_label.configure(text="Panda3D 렌더 창 생성 실패")
            return

        self._camera_np = app.makeCamera(self._window)
        self._camera_np.reparentTo(app.render)

        self._ensure_lights()
        self._update_camera()
        self._panda_ready = True
        self._render_once()
        self._start_interaction_loop()

    def _ensure_lights(self):
        if self._lights_attached:
            return

        app = self._get_app()
        ambient = AmbientLight("ambient_light")
        ambient.setColor((0.45, 0.45, 0.50, 1.0))
        ambient_np = app.render.attachNewNode(ambient)
        app.render.setLight(ambient_np)

        directional = DirectionalLight("dir_light")
        directional.setColor((0.90, 0.90, 1.0, 1.0))
        directional_np = app.render.attachNewNode(directional)
        directional_np.setHpr(-35, -40, 0)
        app.render.setLight(directional_np)

        self._lights_attached = True

    def _render_once(self):
        if not self.winfo_exists() or not self._panda_ready or self._window is None:
            return
        try:
            app = self._get_app()
            app.graphicsEngine.renderFrame()
        except Exception:
            pass

    def _start_interaction_loop(self):
        if self._interaction_job is not None:
            return
        self._interaction_job = self.after(16, self._interaction_tick)

    def _interaction_tick(self):
        self._interaction_job = None
        if self._destroyed or not self.winfo_exists() or not self._panda_ready or self._window is None:
            return

        self._poll_panda_mouse_interaction()
        self._render_once()

        if not self._destroyed and self.winfo_exists():
            self._interaction_job = self.after(16, self._interaction_tick)

    def _poll_panda_mouse_interaction(self):
        app = self._get_app()
        watcher = app.mouseWatcherNode
        if watcher is None or not watcher.hasMouse():
            self._last_panda_mouse = None
            return

        mouse_pos = watcher.getMouse()
        left_down = watcher.isButtonDown(MouseButton.one())

        if left_down:
            if self._last_panda_mouse is not None:
                dx = float(mouse_pos.getX() - self._last_panda_mouse[0])
                dy = float(mouse_pos.getY() - self._last_panda_mouse[1])
                self._orbit_yaw += dx * 180.0
                self._orbit_pitch = max(-80.0, min(80.0, self._orbit_pitch + dy * 120.0))
                self._update_camera()
            self._last_panda_mouse = (float(mouse_pos.getX()), float(mouse_pos.getY()))
        else:
            self._last_panda_mouse = None

        if watcher.isButtonDown(MouseButton.wheelUp()):
            self._zoom(-0.22)
        elif watcher.isButtonDown(MouseButton.wheelDown()):
            self._zoom(0.22)

    def _on_resize(self, _event=None):
        if not self._window:
            return
        wp = WindowProperties()
        wp.setSize(max(1, self._embed_container.winfo_width()), max(1, self._embed_container.winfo_height()))
        self._window.requestProperties(wp)
        self._render_once()

    def _on_drag_start(self, event):
        self._drag_last = (event.x, event.y)

    def _on_drag_move(self, event):
        if self._drag_last is None:
            self._drag_last = (event.x, event.y)
            return

        dx = event.x - self._drag_last[0]
        dy = event.y - self._drag_last[1]
        self._drag_last = (event.x, event.y)

        self._orbit_yaw += dx * 0.4
        self._orbit_pitch = max(-80.0, min(80.0, self._orbit_pitch + dy * 0.4))
        self._update_camera()

    def _on_mouse_wheel(self, event):
        delta = -1 if event.delta < 0 else 1
        self._zoom(-delta * 0.25)

    def _rotate(self, yaw_delta: float = 0.0, pitch_delta: float = 0.0):
        self._orbit_yaw += yaw_delta
        self._orbit_pitch = max(-80.0, min(80.0, self._orbit_pitch + pitch_delta))
        self._update_camera()
        self._render_once()

    def _zoom(self, zoom_delta: float):
        self._camera_distance = max(1.0, min(12.0, self._camera_distance + zoom_delta))
        self._update_camera()
        self._render_once()

    def _update_camera(self):
        if self._camera_np is None:
            return

        import math

        yaw_rad = math.radians(self._orbit_yaw)
        pitch_rad = math.radians(self._orbit_pitch)

        x = self._camera_distance * math.cos(pitch_rad) * math.sin(yaw_rad)
        y = -self._camera_distance * math.cos(pitch_rad) * math.cos(yaw_rad)
        z = self._camera_distance * math.sin(pitch_rad)

        self._camera_np.setPos(x, y, z)
        self._camera_np.lookAt(0, 0, 0)

    def load_glb(self, file_path: str) -> None:
        if not self._panda_ready:
            self.after(100, lambda: self.load_glb(file_path))
            return

        normalized_path = os.path.abspath(file_path) if file_path else ""

        if not normalized_path or not os.path.exists(normalized_path):
            self.status_label.configure(text="모델 파일 경로가 유효하지 않습니다.")
            self._detach_model()
            return

        try:
            app = self._get_app()
            self._detach_model()

            panda_filename = Filename.fromOsSpecific(normalized_path)
            panda_filename.makeCanonical()
            model = app.loader.loadModel(panda_filename)
            model.reparentTo(app.render)
            model.setPos(0, 0, 0)

            bounds = model.getTightBounds()
            if bounds and bounds[0] is not None and bounds[1] is not None:
                min_b, max_b = bounds
                center = (min_b + max_b) * 0.5
                span = max((max_b - min_b).length(), 0.001)
                model.setPos(-center)
                scale = 1.6 / span
                model.setScale(scale)

            self._model_np = model
            self._update_camera()
            self._render_once()
            self.status_label.configure(text=f"Panda3D 렌더링 중: {os.path.basename(normalized_path)}")
        except Exception as exc:
            self.status_label.configure(text=f"모델 로드 실패: {exc}")
            self._detach_model()

    def _detach_model(self):
        if self._model_np is not None and not self._model_np.isEmpty():
            self._model_np.removeNode()
        self._model_np = None

    def _on_destroy(self, _event=None):
        if self._destroyed:
            return
        self._destroyed = True

        if self._interaction_job is not None:
            try:
                self.after_cancel(self._interaction_job)
            except Exception:
                pass
            self._interaction_job = None

        try:
            self._detach_model()
            if self._window is not None:
                app = self._get_app()
                app.closeWindow(self._window)
                self._window = None
        except Exception:
            pass
