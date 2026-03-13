import customtkinter as ctk

from gui.panels import Model3DParametersPanel


class ParameterManagementApp:
    """확장 가능한 파라미터 관리 GUI 애플리케이션"""

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("MyRoom AI - Parameter Manager")
        self.root.geometry("860x760")
        self.root.configure(fg_color="#0b0b0d")

        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.tabview.configure(
            fg_color="#0f1013",
            segmented_button_fg_color="#16181d",
            segmented_button_unselected_color="#1b1e24",
            segmented_button_selected_color="#2a2f39",
            segmented_button_unselected_hover_color="#262b33",
            segmented_button_selected_hover_color="#343a46",
            text_color="#f3f4f6"
        )

        self._panel_classes = [
            Model3DParametersPanel,
        ]
        self._panels = []
        self._register_panels()

    def _register_panels(self):
        for panel_class in self._panel_classes:
            self.tabview.add(panel_class.panel_title)
            tab = self.tabview.tab(panel_class.panel_title)
            panel = panel_class(tab)
            panel.pack(fill="both", expand=True)
            self._panels.append(panel)

    def run(self):
        self.root.mainloop()


def launch_parameter_gui() -> None:
    app = ParameterManagementApp()
    app.run()
