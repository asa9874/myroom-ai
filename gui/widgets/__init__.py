import os
import subprocess
import sys


def launch_external_glb_viewer(model_path: str) -> None:
	if not model_path:
		raise ValueError("model_path is required")

	project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
	subprocess.Popen(
		[sys.executable, "-m", "gui.widgets.panda3d_external_viewer", model_path],
		cwd=project_root,
	)

__all__ = ["launch_external_glb_viewer"]
