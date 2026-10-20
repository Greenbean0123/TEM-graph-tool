"""Responsive startup progress before loading the scientific libraries."""
import json
import os
from pathlib import Path
from queue import Queue, Empty
import sys
from threading import Thread
import tkinter as tk
from tkinter import ttk, messagebox

from app_version import APP_NAME, __version__


def launch():
    if len(sys.argv) == 3 and sys.argv[1] == '--apply-update':
        import update_installer
        return update_installer.run(sys.argv[2])
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    root.title(APP_NAME)
    root.resizable(False, False)
    width, height = 480, 190
    root.geometry(f'{width}x{height}+{max(0, (root.winfo_screenwidth()-width)//2)}+{max(0, (root.winfo_screenheight()-height)//2)}')
    frame = ttk.Frame(root, padding=25)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text=APP_NAME, font=('Helvetica', 20, 'bold')).pack(anchor='w')
    ttk.Label(frame, text=f'Version {__version__}', foreground='#64748b').pack(anchor='w', pady=(2, 15))
    progress = ttk.Progressbar(frame, maximum=100, length=420)
    progress.pack(fill='x')
    status = tk.StringVar(value='Starting…  5%')
    ttk.Label(frame, textvariable=status).pack(anchor='w', pady=(10, 0))
    progress['value'] = 5
    events = Queue()
    loaded, stages, failed = [], [5], []

    def load():
        try:
            events.put((15, 'Loading image support'))
            import PIL.Image
            import numpy
            import tifffile
            events.put((40, 'Loading analysis and plotting libraries'))
            import tem_scalebar_distribution
            events.put((80, 'Preparing the editor'))
            import tem_studio
            events.put((100, tem_studio))
        except Exception as error:
            import traceback
            events.put(('error', (str(error), traceback.format_exc())))

    def poll():
        try:
            while True:
                value, text = events.get_nowait()
                if value == 'error':
                    failed.append(text[1])
                    messagebox.showerror(APP_NAME+' startup', text[0], parent=root)
                    root.destroy()
                    return
                progress['value'] = value
                stages.append(value)
                if value == 100:
                    loaded.append(text)
                    status.set('Ready  100%')
                    root.after(100, root.destroy)
                    return
                status.set(f'{text}…  {value}%')
        except Empty:
            pass
        root.after(40, poll)

    Thread(target=load, daemon=True, name='tem-startup-loader').start()
    root.after(40, poll)
    root.mainloop()
    if not loaded:
        return 1 if failed else 0
    module = loaded[0]
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        result = module.packaged_self_test(sys.argv[2])
        report_path = Path(sys.argv[2])
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report['startup_progress'] = {'steps': stages, 'completed': stages[-1] == 100}
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        return result
    module.TEMStudio().mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(launch())
