"""Local UI preferences; these never change scientific images or export settings."""
import json
import tkinter as tk
from tkinter import ttk


class Appearance:
    def __init__(self, app, path=None):
        self.app, self.path = app, path
        saved = {}
        if path:
            try:
                saved = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
        self.theme = tk.StringVar(app, value=saved.get('theme', 'Light') if saved.get('theme') in ('Light', 'Dark') else 'Light')
        size = str(saved.get('scale', '100%'))
        self.scale = tk.StringVar(app, value=size if size in self.sizes else '100%')
        self.style = ttk.Style(app)
        self.style.theme_use('clam')
        self.fonts = {}

    sizes = ('80%', '90%', '100%', '110%', '125%', '150%', '175%', '200%')

    def apply(self, *_):
        dark = self.theme.get() == 'Dark'
        self.colors = dict(bg='#171d27' if dark else '#f2f5fa',
                           fg='#e6edf7' if dark else '#1c2b42',
                           muted='#a6b5c9' if dark else '#56677f',
                           input='#242f40' if dark else '#ffffff',
                           border='#39495e' if dark else '#ccd6e3',
                           accent='#387dd4' if dark else '#2465ae')
        c = self.colors
        factor = int(self.scale.get().rstrip('%')) / 100
        font = ('Segoe UI', max(8, round(10 * factor)))
        s = self.style
        s.configure('.', background=c['bg'], foreground=c['fg'], font=font)
        for name in ('TFrame', 'TLabel', 'TLabelframe', 'TLabelframe.Label', 'TNotebook', 'TPanedwindow'):
            s.configure(name, background=c['bg'], foreground=c['fg'])
        s.configure('Muted.TLabel', foreground=c['muted'])
        s.configure('Title.TLabel', font=('Segoe UI', round(20 * factor), 'bold'))
        s.configure('TButton', padding=(round(10 * factor), round(7 * factor)), background=c['input'], bordercolor=c['border'])
        s.map('TButton', background=[('active', c['border'])], foreground=[('disabled', c['muted'])])
        s.configure('Accent.TButton', background=c['accent'], foreground='white')
        s.map('Accent.TButton', background=[('active', '#347ed2')], foreground=[('active', 'white')])
        for name in ('TEntry', 'TCombobox'):
            s.configure(name, fieldbackground=c['input'], foreground=c['fg'], insertcolor=c['fg'], bordercolor=c['border'], padding=round(4 * factor))
            s.map(name, fieldbackground=[('readonly', c['input'])], foreground=[('readonly', c['fg'])], selectbackground=[('!disabled', c['accent'])])
        s.configure('TNotebook.Tab', padding=(round(7 * factor), round(8 * factor)), background=c['bg'])
        s.map('TNotebook.Tab', background=[('selected', c['input'])], foreground=[('selected', c['accent'])])
        s.configure('TCheckbutton', background=c['bg'], foreground=c['fg'])
        s.map('TCheckbutton', background=[('active', c['bg'])])
        s.configure('TScrollbar', background=c['border'], troughcolor=c['bg'], arrowcolor=c['fg'])
        self.app.option_add('*TCombobox*Listbox.background', c['input'])
        self.app.option_add('*TCombobox*Listbox.foreground', c['fg'])
        self.app.option_add('*TCombobox*Listbox.font', font)
        self.paint(self.app, factor)
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(dict(theme=self.theme.get(), scale=self.scale.get())), encoding='utf-8')
            except OSError:
                pass

    def paint(self, widget, factor=None):
        c = self.colors
        if factor is None:
            factor = int(self.scale.get().rstrip('%')) / 100
        if isinstance(widget, (tk.Tk, tk.Toplevel, tk.Frame)):
            widget.configure(background=c['bg'])
        if isinstance(widget, tk.Canvas) and widget is not getattr(self.app, 'canvas', None):
            widget.configure(background=c['bg'])
        if isinstance(widget, tk.Listbox):
            widget.configure(background=c['input'], foreground=c['fg'], selectbackground=c['accent'], selectforeground='white', highlightthickness=0, borderwidth=0)
        if isinstance(widget, (tk.Label, tk.Button)):
            widget.configure(background=c['bg'], foreground=c['fg'])
        if isinstance(widget, ttk.Label) and widget.cget('foreground') in ('#65758b', '#64748b'):
            widget.configure(foreground='', style='Muted.TLabel')
        if 'font' in widget.keys() and widget.cget('font'):
            key = str(widget)
            if key not in self.fonts:
                from tkinter.font import Font
                f = Font(root=self.app, font=widget.cget('font')).actual()
                self.fonts[key] = (f['family'], f['size'], f['weight'])
            family, size, weight = self.fonts[key]
            widget.configure(font=(family, max(8, round(size * factor)), weight))
        for child in widget.winfo_children():
            self.paint(child, factor)
