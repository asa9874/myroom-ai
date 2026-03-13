import math
import os
import sys
from typing import Optional

from direct.showbase.ShowBase import ShowBase
from panda3d.core import AmbientLight, DirectionalLight, Filename, loadPrcFileData

loadPrcFileData('', 'window-title MyRoom AI - 3D Viewer')
loadPrcFileData('', 'win-size 1200 780')
loadPrcFileData('', 'audio-library-name null')


class ExternalGLBViewer(ShowBase):
    def __init__(self, model_path: str):
        super().__init__()
        self.disableMouse()

        self.model_path = os.path.abspath(model_path)
        self.model = None

        self.camera_distance = 3.0
        self.orbit_yaw = 20.0
        self.orbit_pitch = -15.0
        self._last_mouse = None

        self._setup_lights()
        self._load_model()
        self._update_camera()

        self.taskMgr.add(self._interaction_task, "interaction_task")

    def _setup_lights(self):
        ambient = AmbientLight("ambient_light")
        ambient.setColor((0.48, 0.48, 0.55, 1.0))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        directional = DirectionalLight("dir_light")
        directional.setColor((0.95, 0.95, 1.0, 1.0))
        directional_np = self.render.attachNewNode(directional)
        directional_np.setHpr(-35, -40, 0)
        self.render.setLight(directional_np)

    def _load_model(self):
        if not os.path.exists(self.model_path):
            print(f"[ERROR] 모델 파일 없음: {self.model_path}")
            return

        panda_filename = Filename.fromOsSpecific(self.model_path)
        panda_filename.makeCanonical()

        try:
            model = self.loader.loadModel(panda_filename)
            model.reparentTo(self.render)
            model.setPos(0, 0, 0)

            bounds = model.getTightBounds()
            if bounds and bounds[0] is not None and bounds[1] is not None:
                min_b, max_b = bounds
                center = (min_b + max_b) * 0.5
                span = max((max_b - min_b).length(), 0.001)
                model.setPos(-center)
                model.setScale(1.8 / span)

            self.model = model
            print(f"[OK] 모델 로드 완료: {self.model_path}")
        except Exception as exc:
            print(f"[ERROR] 모델 로드 실패: {exc}")

    def _update_camera(self):
        yaw_rad = math.radians(self.orbit_yaw)
        pitch_rad = math.radians(self.orbit_pitch)

        x = self.camera_distance * math.cos(pitch_rad) * math.sin(yaw_rad)
        y = -self.camera_distance * math.cos(pitch_rad) * math.cos(yaw_rad)
        z = self.camera_distance * math.sin(pitch_rad)

        self.camera.setPos(x, y, z)
        self.camera.lookAt(0, 0, 0)

    def _interaction_task(self, task):
        mw = self.mouseWatcherNode
        if mw and mw.hasMouse():
            mouse = mw.getMouse()
            left_down = mw.isButtonDown("mouse1")

            if left_down:
                if self._last_mouse is not None:
                    dx = float(mouse.getX() - self._last_mouse[0])
                    dy = float(mouse.getY() - self._last_mouse[1])
                    self.orbit_yaw += dx * 180.0
                    self.orbit_pitch = max(-80.0, min(80.0, self.orbit_pitch + dy * 120.0))
                    self._update_camera()
                self._last_mouse = (float(mouse.getX()), float(mouse.getY()))
            else:
                self._last_mouse = None

            if mw.isButtonDown("wheel_up"):
                self.camera_distance = max(1.0, self.camera_distance - 0.22)
                self._update_camera()
            elif mw.isButtonDown("wheel_down"):
                self.camera_distance = min(12.0, self.camera_distance + 0.22)
                self._update_camera()

        return task.cont


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m gui.widgets.panda3d_external_viewer <path_to_glb>")
        return

    model_path = sys.argv[1]
    app = ExternalGLBViewer(model_path)
    app.run()


if __name__ == "__main__":
    main()
