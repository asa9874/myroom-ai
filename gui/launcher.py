import tkinter as tk
from tkinter import ttk

from gui.panels import Model3DParametersPanel


class ParameterManagementApp:
    """확장 가능한 파라미터 관리 GUI 애플리케이션"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MyRoom AI - Parameter Manager")
        self.root.geometry("860x760")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self._panel_classes = [
            Model3DParametersPanel,
        ]
        self._panels = []
        self._register_panels()

    def _register_panels(self):
        for panel_class in self._panel_classes:
            panel = panel_class(self.notebook)
            self.notebook.add(panel, text=panel_class.panel_title)
            self._panels.append(panel)

    def run(self):
        self.root.mainloop()


def launch_parameter_gui() -> None:
    app = ParameterManagementApp()
    app.run()
