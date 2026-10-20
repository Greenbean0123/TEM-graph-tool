"""Start the editor with stage-based loading progress on its own root window."""
import os
from pathlib import Path
import sys


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
    import tem_studio
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        import faulthandler
        with open(str(sys.argv[2])+'.startup.log', 'w', encoding='utf-8') as diagnostic:
            faulthandler.dump_traceback_later(45, repeat=True, file=diagnostic)
            def step(value, text):
                diagnostic.write(f'{value}: {text}\n')
                diagnostic.flush()
            try:
                return tem_studio.packaged_self_test(sys.argv[2], startup_callback=step)
            finally:
                faulthandler.cancel_dump_traceback_later()
    tem_studio.TEMStudio(show_startup=True).mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(launch())
