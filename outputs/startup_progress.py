"""A loading panel that shares the editor's single Tk interpreter."""
import tkinter as tk
from tkinter import ttk
from app_version import APP_NAME, __version__


class StartupPanel:
    def __init__(self, root, on_step=None):
        self.root, self.on_step = root, on_step
        self.steps = []
        root.title(APP_NAME)
        root.resizable(False, False)
        width, height = 480, 190
        root.geometry(f'{width}x{height}+{max(0, (root.winfo_screenwidth()-width)//2)}+{max(0, (root.winfo_screenheight()-height)//2)}')
        self.frame = ttk.Frame(root, padding=25)
        self.frame.pack(fill='both', expand=True)
        ttk.Label(self.frame, text=APP_NAME, font=('Helvetica', 20, 'bold')).pack(anchor='w')
        ttk.Label(self.frame, text=f'Version {__version__}', foreground='#64748b').pack(anchor='w', pady=(2, 15))
        self.bar = ttk.Progressbar(self.frame, maximum=100, length=420)
        self.bar.pack(fill='x')
        self.status = tk.StringVar(root)
        ttk.Label(self.frame, textvariable=self.status).pack(anchor='w', pady=(10, 0))
        self.step(5, 'Starting')

    def step(self, value, text):
        self.steps.append(value)
        self.bar['value'] = value
        self.status.set(f'{text}…  {value}%')
        self.root.update_idletasks()
        if self.on_step:
            self.on_step(value, text)

    def close(self):
        self.frame.destroy()
        self.root.resizable(True, True)
