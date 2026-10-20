"""Responsive startup progress before loading the scientific libraries."""
import json
import os
from pathlib import Path
import sys
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
    loaded, stages, failed = [], [5], []
    diagnostic = None
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        import faulthandler
        diagnostic = open(str(sys.argv[2])+'.startup.log', 'w', encoding='utf-8')
        faulthandler.dump_traceback_later(45, repeat=True, file=diagnostic)

    def step(value, text):
        progress['value'] = value
        stages.append(value)
        status.set(f'{text}…  {value}%')
        root.update_idletasks()
        if diagnostic:
            diagnostic.write(f'{value}: {text}\n')
            diagnostic.flush()

    def load():
        try:
            step(15, 'Loading image support')
            import PIL.Image
            import numpy
            import tifffile
            step(40, 'Loading analysis and plotting libraries')
            import tem_scalebar_distribution
            step(80, 'Preparing the editor')
            import tem_studio
            loaded.append(tem_studio)
            step(100, 'Ready')
            root.after(100, root.destroy)
        except Exception as error:
            import traceback
            failed.append(traceback.format_exc())
            if diagnostic:
                diagnostic.write(failed[-1])
                diagnostic.flush()
            else:
                messagebox.showerror(APP_NAME+' startup', str(error), parent=root)
            root.destroy()

    # macOS font and GUI initialization must stay on the main thread.
    root.after(50, load)
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
        if diagnostic:
            faulthandler.cancel_dump_traceback_later()
            diagnostic.close()
        return result
    module.TEMStudio().mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(launch())
