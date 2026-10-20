"""TEM graphic tool desktop application. Run directly or use the bundled EXE."""
import copy
import json
import os
import sys
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk
import tifffile
import tem_scalebar_distribution as core
from app_version import __version__, APP_NAME
import updater
import update_ui


class ScrollableTab(ttk.Frame):
    """A tab whose controls remain reachable in short desktop windows."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg='#f3f5f8', width=405)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, padding=12)
        self.window_id = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.content.bind('<Configure>', self.update_region)
        self.canvas.bind('<Configure>', self.resize_content)

    def update_region(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def resize_content(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)
        self.update_region()

    def wheel(self, event):
        if self.content.winfo_reqheight() <= self.canvas.winfo_height():
            return 'break'
        delta = event.delta
        step = -int(delta/120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(step, 'units')
        return 'break'


class TEMStudio(tk.Tk):
    def __init__(self, enable_updates=True):
        super().__init__()
        self.title(f'{APP_NAME} {__version__} · Scale Bar & Size Distribution')
        self.tk.call('tk', 'appname', APP_NAME)
        self.enable_updates = enable_updates
        self.geometry('1400x920')
        self.minsize(900, 500)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.temp = tempfile.TemporaryDirectory(prefix='tem_studio_')
        self.files = []
        self.settings = {}
        self.current = None
        self.loading = False
        self.pending = None
        self.preview_image = None
        self.report = None
        self.view = 'tem'
        self.photo = None
        self.transform = (1, 0, 0)
        self.drag = None
        self.csv_path = None
        self.vars = {}
        self.vars['match_original'] = tk.StringVar(value='true')
        self.app_icon = ImageTk.PhotoImage(Image.open(Path(__file__).with_name('assets')/'graph-tool-icon.png').resize((64, 64), Image.Resampling.LANCZOS))
        try:
            self.iconphoto(True, self.app_icon)
        except tk.TclError:
            pass  # macOS also uses the application's bundled ICNS.
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#f3f5f8')
        style.configure('TLabel', background='#f3f5f8', font=('Segoe UI', 10))
        style.configure('TLabelframe', background='#f3f5f8')
        style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'))
        style.configure('TButton', font=('Segoe UI', 10), padding=5)
        style.configure('Accent.TButton', background='#225e9b', foreground='white')
        self.build()
        self.bind_all('<MouseWheel>', self.scroll_left)
        self.bind_all('<Button-4>', self.scroll_left)
        self.bind_all('<Button-5>', self.scroll_left)
        self.bind('<Control-o>', lambda e: self.add_files())
        self.bind('<Control-s>', lambda e: self.export_current())
        if enable_updates:
            self.after(200, self.restore_update_session)
            self.after(500, self.mark_update_ready)
            import update_cleanup
            update_cleanup.schedule()

    def var(self, key, default=''):
        v = tk.StringVar(value=str(default))
        self.vars[key] = v
        return v

    def field(self, parent, label, key, default='', choices=None):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=3)
        ttk.Label(row, text=label, width=23).pack(side='left')
        v = self.var(key, default)
        if choices:
            widget = ttk.Combobox(row, textvariable=v, values=choices, state='readonly', width=19)
        else:
            widget = ttk.Entry(row, textvariable=v, width=22)
        widget.pack(side='right', fill='x', expand=True)
        v.trace_add('write', lambda *_: self.changed(key))
        return widget

    def build(self):
        header = ttk.Frame(self, padding=(18, 10))
        header.pack(fill='x')
        self.header_icon = ImageTk.PhotoImage(Image.open(Path(__file__).with_name('assets')/'graph-tool-icon.png').resize((42, 42), Image.Resampling.LANCZOS))
        ttk.Label(header, image=self.header_icon).pack(side='left', padx=(0, 8))
        ttk.Label(header, text=APP_NAME, font=('Segoe UI', 20, 'bold')).pack(side='left')
        ttk.Label(header, text='Scale bar editor  /  Size distribution', foreground='#65758b').pack(side='left', padx=20)
        ttk.Button(header, text='Export current…', style='Accent.TButton', command=self.export_current).pack(side='right')
        ttk.Button(header, text='Export all TEM…', command=self.export_all).pack(side='right', padx=8)
        body = ttk.Panedwindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=12)
        left = ttk.Frame(body, width=425)
        body.add(left, weight=0)
        right = ttk.Frame(body)
        body.add(right, weight=1)
        tabs = ttk.Notebook(left)
        tabs.pack(fill='both', expand=True)
        self.scroll_tabs = [ScrollableTab(tabs) for _ in range(3)]
        for tab, label in zip(self.scroll_tabs, ('Data & calibration', 'Scale bar', 'Distribution')):
            tabs.add(tab, text=label)
        data, layout, dist = [tab.content for tab in self.scroll_tabs]
        inset_tab = ScrollableTab(tabs)
        self.scroll_tabs.append(inset_tab)
        tabs.add(inset_tab, text='Inset zoom')
        inset = inset_tab.content
        self.field(inset, 'Show inset', 'inset_enabled', 'No', ['No', 'Yes'])
        ttk.Button(inset, text='Select source region on image', command=lambda: self.tool('inset')).pack(fill='x', pady=8)
        self.field(inset, 'Source box x0,y0,x1,y1', 'inset_roi')
        self.field(inset, 'Inset width (px)', 'inset_width', '500')
        self.field(inset, 'Inset X (px; optional)', 'inset_x')
        self.field(inset, 'Inset Y (px; optional)', 'inset_y')
        self.field(inset, 'Border / scale color', 'inset_color', 'white', ['white', 'black'])
        self.field(inset, 'Border thickness (px)', 'inset_border', '4')
        self.field(inset, 'Connector line', 'inset_connector', 'Yes', ['Yes', 'No'])
        self.field(inset, 'Connector thickness (px)', 'inset_connector_width', '4')
        self.field(inset, 'Connector color', 'inset_connector_color', 'white', ['white', 'black'])
        self.field(inset, 'Inset bar nm (blank=auto)', 'inset_bar_nm')
        self.field(inset, 'Show inset scale bar', 'inset_show_scalebar', 'Yes', ['Yes', 'No'])
        ttk.Label(inset, text='Select a region, then drag the inset to move it. Drag its lower-right corner to resize. Aspect ratio is preserved; its scale bar updates automatically. All dimensions use original image pixels.', wraplength=375).pack(anchor='w', pady=12)
        updates = ScrollableTab(tabs)
        self.scroll_tabs.append(updates)
        tabs.add(updates, text='Updates')
        ttk.Label(updates.content, text=APP_NAME + ' ' + __version__, font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=10)
        ttk.Label(updates.content, text='Check GitHub releases in the background. Signed updates are installed after confirmation. Your current image settings are restored after restart.', wraplength=370).pack(anchor='w', pady=8)
        if self.enable_updates:
            update_ui.attach(self, updates.content, __version__, before_restart=self.save_update_session)
        else:
            ttk.Label(updates.content, text='Update checks disabled during self-test.').pack()
        buttons = ttk.Frame(data)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Add TIFF…', command=self.add_files).pack(side='left')
        ttk.Button(buttons, text='Remove', command=self.remove_file).pack(side='left', padx=5)
        ttk.Button(buttons, text='Load sample', command=self.sample).pack(side='right')
        self.listbox = tk.Listbox(data, height=7, exportselection=False, font=('Segoe UI', 10))
        self.listbox.pack(fill='x', pady=8)
        self.listbox.bind('<<ListboxSelect>>', self.select_file)
        ttk.Label(data, text='Calibration is stored separately for every image.', wraplength=375).pack(anchor='w', pady=(0, 10))
        self.field(data, 'Calibration mode', 'cal_mode', 'Auto measure bar', ['Auto measure bar', 'Manual bar width', 'nm per pixel'])
        self.field(data, 'Original label value', 'original_bar_nm')
        self.field(data, 'Original label unit', 'original_unit', 'nm', ['nm', 'µm'])
        self.field(data, 'Original width (px)', 'original_bar_px')
        self.field(data, 'nm per pixel', 'nm_per_pixel')
        ttk.Label(data, text='Auto mode reads the original nm/µm label and measures its bar. Physical metadata takes priority. Verify the detected values below.', wraplength=375, foreground='#65758b').pack(anchor='w', pady=6)
        ttk.Button(data, text='Re-detect original scale bar', command=self.redetect_scale).pack(fill='x', pady=4)
        ttk.Button(data, text='Measure original bar with two points', command=lambda: self.tool('measure')).pack(fill='x', pady=4)
        self.field(data, 'Erase box (x0,y0,x1,y1)', 'erase_box')
        self.field(data, 'Erase background', 'background', 'Auto', ['Auto', 'Black', 'White'])
        self.field(data, 'Remove black footer', 'remove_footer', 'Yes', ['Yes', 'No'])
        self.field(data, 'Original corner', 'original_corner', 'bottom-right', ['bottom-right', 'bottom-left', 'top-right', 'top-left'])
        ttk.Button(data, text='Draw original annotation erase box', command=lambda: self.tool('erase')).pack(fill='x', pady=4)
        ttk.Label(data, text='Blank erase box: detect a separate footer, otherwise use a 420 × 130 px corner box. Draw a box for other layouts.', wraplength=375, foreground='#65758b').pack(anchor='w', pady=6)
        presets = ttk.Frame(data)
        presets.pack(fill='x', pady=5)
        ttk.Button(presets, text='Save project…', command=self.save_project).pack(side='left')
        ttk.Button(presets, text='Open project…', command=self.open_project).pack(side='right')

        ttk.Label(layout, text='Large, readable scale bar', font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(0, 8))
        self.field(layout, 'Length (nm; blank=original)', 'bar_nm', '')
        self.field(layout, 'Auto target width (px)', 'target_width', '500')
        self.field(layout, 'Color', 'color', 'white', ['white', 'black'])
        self.field(layout, 'Line thickness (px)', 'thickness', '18')
        self.field(layout, 'Font size (px)', 'font_size', '64')
        self.field(layout, 'Corner preset', 'corner', 'bottom-right', ['bottom-right', 'bottom-left', 'top-right', 'top-left'])
        self.field(layout, 'Margin (px)', 'margin', '110')
        self.field(layout, 'Label position', 'label_position', 'above', ['above', 'below'])
        self.field(layout, 'Text / line gap (px)', 'gap', '12')
        self.field(layout, 'Custom X (px; optional)', 'bar_x')
        self.field(layout, 'Custom Y (px; optional)', 'bar_y')
        ttk.Button(layout, text='Use corner preset (clear X / Y)', command=self.reset_position).pack(fill='x', pady=8)
        ttk.Button(layout, text='Refresh TEM preview', command=self.refresh_tem).pack(fill='x')
        ttk.Label(layout, text='Drag the new scale bar in the preview to position it anywhere. Dimensions use original image pixels. Changing length always updates the nm label to preserve calibration.', wraplength=375, foreground='#65758b').pack(anchor='w', pady=10)

        ttk.Button(dist, text='Open diameter CSV…', command=self.open_csv).pack(fill='x')
        self.csv_label = ttk.Label(dist, text='No CSV selected', wraplength=375)
        self.csv_label.pack(anchor='w', pady=8)
        self.column_widget = self.field(dist, 'Diameter column (nm)', 'column', 'diameter_nm', ['diameter_nm'])
        self.field(dist, 'Number of bins', 'bins', '12')
        self.field(dist, 'Bin width (nm; optional)', 'bin_width')
        self.field(dist, 'Y axis', 'y_mode', 'count', ['count', 'frequency'])
        self.field(dist, 'Export DPI (≥300)', 'dpi', '300')
        self.pdf = tk.BooleanVar(value=True)
        ttk.Checkbutton(dist, text='Also export PDF', variable=self.pdf).pack(anchor='w', pady=8)
        ttk.Button(dist, text='Preview distribution', command=self.refresh_distribution).pack(fill='x')
        ttk.Label(dist, text='Gaussian maximum-likelihood fit; std uses ddof=0. No particle segmentation or diameter extraction.', wraplength=375, foreground='#65758b').pack(anchor='w', pady=12)

        toolbar = ttk.Frame(right, padding=(8, 0, 0, 8))
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='TEM preview', command=self.refresh_tem).pack(side='left')
        ttk.Button(toolbar, text='Original', command=self.show_original).pack(side='left', padx=5)
        ttk.Button(toolbar, text='Distribution', command=self.refresh_distribution).pack(side='left')
        self.mode = tk.StringVar(value='move')
        ttk.Label(toolbar, text='Drag bar to move · fit view').pack(side='right')
        self.canvas = tk.Canvas(right, bg='#202833', highlightthickness=0, cursor='hand2')
        self.canvas.pack(fill='both', expand=True, padx=(8, 0))
        self.canvas.bind('<Configure>', lambda e: self.draw_preview())
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.motion)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.info = tk.StringVar(value='Add a TIFF or open a CSV to begin.')
        ttk.Label(right, textvariable=self.info, wraplength=850, padding=8).pack(fill='x')
        self.status = tk.StringVar(value='Ready · Original files are preserved')
        ttk.Label(self, textvariable=self.status, padding=(16, 8), relief='sunken').pack(fill='x')

    def image_state(self):
        return {k: v.get() for k, v in self.vars.items() if k not in {'column', 'bins', 'bin_width', 'y_mode', 'dpi'}}

    def scroll_left(self, event):
        # Route wheel events from descendants only; the image preview is unaffected.
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if isinstance(widget, ScrollableTab):
                if getattr(event, 'num', None) in (4, 5):
                    event.delta = 120 if event.num == 4 else -120
                return widget.wheel(event)
            widget = getattr(widget, 'master', None)

    def store(self):
        if self.current:
            self.settings[str(self.current)] = self.image_state()

    def changed(self, key=None, *_):
        if self.loading:
            return
        if key == 'bar_nm':
            self.vars['match_original'].set('true' if not self.vars['bar_nm'].get().strip() else 'false')
        elif key in ('original_unit', 'original_bar_nm') and self.vars['match_original'].get() == 'true':
            self.loading = True
            self.vars['bar_nm'].set('')
            self.loading = False
        self.store()
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(450, self.auto_refresh)

    def auto_refresh(self):
        self.pending = None
        if self.view == 'distribution':
            self.refresh_distribution(quiet=True)
        elif self.current and self.mode.get() == 'move':
            self.refresh_tem(quiet=True)

    def add_files(self):
        names = filedialog.askopenfilenames(title='Add TEM images', filetypes=[('TIFF images', '*.tif *.tiff')])
        self.load_files(names)

    def load_files(self, names):
        for name in names:
            path = Path(name).resolve()
            if path not in self.files:
                self.files.append(path)
                self.listbox.insert('end', path.name)
        if names:
            self.listbox.selection_clear(0, 'end')
            self.listbox.selection_set(len(self.files)-1)
            self.select_file()

    def select_file(self, _=None):
        indices = self.listbox.curselection()
        if not indices:
            return
        self.store()
        self.current = self.files[indices[0]]
        defaults = dict(cal_mode='Auto measure bar', original_bar_nm='', original_unit='nm', match_original='true', original_bar_px='', nm_per_pixel='',
                        erase_box='', background='Auto', remove_footer='Yes', original_corner='bottom-right', bar_nm='', target_width='500',
                        color='white', thickness='18', font_size='64', corner='bottom-right', margin='110',
                        label_position='above', gap='12', bar_x='', bar_y='',
                        inset_enabled='No', inset_roi='', inset_width='500', inset_x='', inset_y='',
                        inset_color='white', inset_border='4', inset_connector='Yes', inset_bar_nm='',
                        inset_connector_width='4', inset_connector_color='white', inset_show_scalebar='Yes')
        self.loading = True
        for key, value in dict(defaults, **self.settings.get(str(self.current), {})).items():
            if key in self.vars:
                self.vars[key].set(value)
        self.loading = False
        self.mode.set('move')
        self.refresh_tem(quiet=True)

    def remove_file(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        removed = self.files.pop(sel[0])
        self.settings.pop(str(removed), None)
        self.listbox.delete(sel[0])
        self.current = None
        if self.files:
            self.listbox.selection_set(0)
            self.select_file()
        else:
            self.preview_image = None
            self.report = None
            self.canvas.delete('all')

    def sample(self):
        # Synthetic demonstration only; never bundle the user's research data.
        import numpy as np
        folder = Path(self.temp.name)
        image = folder/'synthetic_demo.tif'
        csv_file = folder/'synthetic_diameters.csv'
        rng = np.random.default_rng(21)
        array = np.clip(rng.normal(175, 15, (1091, 1024)), 0, 255).astype(np.uint8)
        array[1024:] = 0
        array[1050:1058, 500:751] = 255
        tifffile.imwrite(image, array)
        values = np.clip(rng.normal(65, 12, 103), 1, None)
        csv_file.write_text('diameter_nm\n'+'\n'.join(f'{v:.4f}' for v in values)+'\n', encoding='utf-8')
        self.load_files([str(image)])
        self.vars['original_bar_nm'].set('200')
        self.vars['erase_box'].set('0,1024,1024,1091')
        self.set_csv(csv_file)
        self.vars['column'].set('diameter_nm')
        self.refresh_tem(quiet=True)
        self.status.set('Synthetic demonstration only · not experimental data · temporary files')

    def get_args(self, state=None, out=None):
        a = core.create_parser().parse_args([])
        s = state or self.image_state()
        for key in ('original_bar_nm', 'original_bar_px', 'nm_per_pixel', 'bar_nm', 'target_width'):
            value = s.get(key, '').strip()
            setattr(a, key, core.positive(value) if value else None)
        a.target_width = a.target_width or 500
        a.match_original_bar = s.get('match_original', 'true') == 'true' or a.bar_nm is None
        if a.match_original_bar:
            a.bar_nm = None
        a.ocr_default_unit = 'um' if s.get('original_unit') == 'µm' else 'nm'
        if a.original_bar_nm is not None and a.ocr_default_unit == 'um':
            a.original_bar_nm *= 1000
        mode = s['cal_mode']
        a.measure_original_bar = mode == 'Auto measure bar'
        if mode == 'nm per pixel':
            a.original_bar_nm = a.original_bar_px = None
        else:
            a.nm_per_pixel = None
        if mode == 'Auto measure bar':
            a.original_bar_px = None
        for key in ('thickness', 'font_size', 'margin', 'gap'):
            v = int(s[key])
            if v < (1 if key in ('thickness', 'font_size') else 0):
                raise ValueError(f'{key} is too small')
            setattr(a, key, v)
        for key in ('bar_x', 'bar_y'):
            setattr(a, key, int(s[key]) if s.get(key, '').strip() else None)
        for key in ('color', 'corner', 'original_corner', 'label_position'):
            setattr(a, key, s[key])
        a.background = {'Auto': None, 'Black': 0, 'White': 255}[s['background']]
        a.keep_original_footer = s.get('remove_footer', 'Yes') == 'No'
        a.erase_box = core.rectangle(s['erase_box']) if s['erase_box'].strip() else None
        a.inset_roi = core.rectangle(s['inset_roi']) if s.get('inset_enabled') == 'Yes' and s.get('inset_roi', '').strip() else None
        a.inset_width = int(s.get('inset_width', '500'))
        a.inset_x = int(s['inset_x']) if s.get('inset_x', '').strip() else None
        a.inset_y = int(s['inset_y']) if s.get('inset_y', '').strip() else None
        a.inset_color = s.get('inset_color', 'white')
        a.inset_border = int(s.get('inset_border', '4'))
        a.inset_no_connector = s.get('inset_connector', 'Yes') == 'No'
        a.inset_connector_width = int(s.get('inset_connector_width', '4'))
        a.inset_connector_color = s.get('inset_connector_color', 'white')
        a.inset_bar_nm = core.positive(s['inset_bar_nm']) if s.get('inset_bar_nm', '').strip() else None
        a.inset_no_scalebar = s.get('inset_show_scalebar', 'Yes') == 'No'
        a.output_dir = Path(out or self.temp.name)
        a.output_dir.mkdir(parents=True, exist_ok=True)
        return a

    def fail(self, e, quiet=False):
        self.status.set(str(e))
        if not quiet:
            messagebox.showerror('Please check settings', str(e))

    def refresh_tem(self, quiet=False):
        if not self.current:
            return
        self.view = 'tem'
        self.mode.set('move')
        try:
            if self.vars['cal_mode'].get() == 'Auto measure bar' and not self.vars['original_bar_nm'].get().strip():
                self.status.set('Reading original scale label and measuring its pixel width…')
                self.update_idletasks()
            self.preview_image, self.report = core.redraw(self.current, self.get_args(), render_only=True)
            r = self.report
            self.loading = True
            try:
                if r.get('original_bar_nm') is not None:
                    factor = 1000 if self.vars['original_unit'].get() == 'µm' else 1
                    self.vars['original_bar_nm'].set(f"{r['original_bar_nm']/factor:g}")
                if r.get('measured_original_bar_pixels') is not None:
                    self.vars['original_bar_px'].set(str(r['measured_original_bar_pixels']))
                self.vars['nm_per_pixel'].set(f"{r['nm_per_pixel']:.12g}")
                if self.vars['match_original'].get() == 'true' or not self.vars['bar_nm'].get().strip():
                    self.vars['bar_nm'].set(f"{r['bar_nm']:g}")
            finally:
                self.loading = False
            self.store()
            self.info.set(f"{self.current.name}  |  {r['bar_nm']:g} nm = {r['bar_pixels']} px  |  {r['nm_per_pixel']:.8g} nm/px\n"
                          f"Original: {str(r.get('original_bar_nm') or 'metadata')} nm / {r['measured_original_bar_pixels'] or 'manual / metadata'} px · Drag the new bar to move it")
            self.status.set('Preview updated · New bar is overlaid on the image · Source file unchanged')
            if 'selected unit' in (r.get('recognized_scale_text') or ''):
                self.status.set('Number recognized; unit text unreadable. Using selected '+self.vars['original_unit'].get()+'. Please verify the unit.')
            self.draw_preview()
        except Exception as e:
            self.report = None
            try:
                self.show_original()
            except Exception:
                pass
            self.fail(e, quiet)

    def redetect_scale(self):
        if not self.current:
            return
        self.loading = True
        try:
            self.vars['cal_mode'].set('Auto measure bar')
            if self.vars['match_original'].get() == 'true':
                self.vars['bar_nm'].set('')
            for key in ('original_bar_nm', 'original_bar_px', 'nm_per_pixel'):
                self.vars[key].set('')
        finally:
            self.loading = False
        self.refresh_tem(quiet=False)

    def show_original(self):
        if not self.current:
            return
        self.view = 'original'
        with Image.open(self.current) as im:
            self.preview_image = im.copy()
        self.info.set('Original image · Use two-point measurement or draw an erase box from Data & calibration.')
        self.draw_preview()

    def draw_preview(self):
        if self.preview_image is None:
            return
        w, h = self.preview_image.size
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale = min(max(cw-24, 1)/w, max(ch-24, 1)/h)
        size = (max(1, round(w*scale)), max(1, round(h*scale)))
        ox, oy = (cw-size[0])/2, (ch-size[1])/2
        self.transform = (scale, ox, oy)
        self.photo = ImageTk.PhotoImage(self.preview_image.resize(size, Image.Resampling.LANCZOS))
        self.canvas.delete('all')
        self.canvas.create_image(ox, oy, anchor='nw', image=self.photo)
        if self.view == 'tem' and self.report and self.report.get('inset'):
            x0, y0, x1, y1 = self.report['inset']['box']
            self.canvas.create_rectangle(ox+x1*scale-9, oy+y1*scale-9,
                                         ox+x1*scale, oy+y1*scale, fill='#ffca3a', outline='#202833')

    def point(self, event):
        scale, ox, oy = self.transform
        w, h = self.preview_image.size
        return (max(0, min(w-1, round((event.x-ox)/scale))), max(0, min(h-1, round((event.y-oy)/scale))))

    def tool(self, mode):
        if not self.current:
            messagebox.showinfo('Add image', 'Please add a TIFF first.')
            return
        if mode == 'inset':
            self.refresh_tem()
        else:
            self.show_original()
        self.mode.set(mode)
        self.status.set('Drag a source rectangle for the inset.' if mode == 'inset' else 'Drag between original bar endpoints (center to center).' if mode == 'measure' else 'Drag a rectangle covering the entire original bar and text.')

    def press(self, event):
        if self.preview_image is None or self.view == 'distribution':
            return
        point = self.point(event)
        if self.mode.get() in ('measure', 'erase', 'inset'):
            self.drag = (point, (event.x, event.y))
        elif self.view == 'tem' and self.report:
            inset = self.report.get('inset')
            if inset:
                x0, y0, x1, y1 = inset['box']
                if x0 <= point[0] < x1 and y0 <= point[1] < y1:
                    tolerance = 16/self.transform[0]
                    self.mode.set('resize_inset' if x1-point[0] < tolerance and y1-point[1] < tolerance else 'move_inset')
                    self.drag = (point, (x0, y0))
                    return
            x0, y0, x1, y1 = self.report['annotation_box']
            if x0-15 <= point[0] <= x1+15 and y0-15 <= point[1] <= y1+15:
                self.drag = (point, (x0, y0))

    def motion(self, event):
        if self.drag is None:
            return
        self.canvas.delete('selection')
        if self.mode.get() in ('measure', 'erase', 'inset'):
            x, y = self.drag[1]
            if self.mode.get() == 'measure':
                self.canvas.create_line(x, y, event.x, event.y, fill='#ffca3a', width=3, tags='selection')
            else:
                self.canvas.create_rectangle(x, y, event.x, event.y, outline='#ffca3a', width=2, tags='selection')
        else:
            point = self.point(event)
            x = self.drag[1][0]+point[0]-self.drag[0][0]
            y = self.drag[1][1]+point[1]-self.drag[0][1]
            scale, ox, oy = self.transform
            box = self.report['inset']['box'] if self.mode.get() in ('move_inset', 'resize_inset') else self.report['annotation_box']
            if self.mode.get() == 'resize_inset':
                x, y = box[:2]
                width = max(80, point[0]-x)
                box = [x, y, x+width, y+round(width*(box[3]-box[1])/(box[2]-box[0]))]
            self.canvas.create_rectangle(ox+x*scale, oy+y*scale, ox+(x+box[2]-box[0])*scale,
                                         oy+(y+box[3]-box[1])*scale, outline='#ffca3a', width=2, tags='selection')

    def release(self, event):
        if self.drag is None:
            return
        point = self.point(event)
        start, other = self.drag
        self.drag = None
        self.canvas.delete('selection')
        self.loading = True
        try:
            if self.mode.get() == 'measure':
                distance = ((point[0]-start[0])**2+(point[1]-start[1])**2)**.5
                if distance < 2:
                    raise ValueError('Measurement too short; drag across the original bar')
                self.vars['original_bar_px'].set(f'{distance:.4f}')
                self.vars['cal_mode'].set('Manual bar width')
            elif self.mode.get() in ('erase', 'inset'):
                x0, x1 = sorted([start[0], point[0]])
                y0, y1 = sorted([start[1], point[1]])
                if x1 == x0 or y1 == y0:
                    raise ValueError('Draw a non-empty rectangle')
                key = 'inset_roi' if self.mode.get() == 'inset' else 'erase_box'
                self.vars[key].set(f'{x0},{y0},{x1+1},{y1+1}')
                if key == 'inset_roi':
                    self.vars['inset_enabled'].set('Yes')
                    w, h = self.preview_image.size
                    ratio = (y1-y0+1)/(x1-x0+1)
                    width = min(500, w-40, int((h-40)/ratio))
                    self.vars['inset_width'].set(str(width))
                    self.vars['inset_x'].set(str(max(0, w-width-20)))
                    self.vars['inset_y'].set('20')
            elif self.mode.get() in ('move_inset', 'resize_inset'):
                box = self.report['inset']['box']
                w, h = self.preview_image.size
                width, height = box[2]-box[0], box[3]-box[1]
                x, y = other
                if self.mode.get() == 'resize_inset':
                    ratio = height/width
                    width = max(80, min(point[0]-x, w-x, int((h-y)/ratio)))
                    self.vars['inset_width'].set(str(width))
                else:
                    x = max(0, min(w-width, x+point[0]-start[0]))
                    y = max(0, min(h-height, y+point[1]-start[1]))
                self.vars['inset_x'].set(str(x))
                self.vars['inset_y'].set(str(y))
            else:
                x = other[0]+point[0]-start[0]
                y = other[1]+point[1]-start[1]
                box = self.report['annotation_box']
                w, h = self.preview_image.size
                x = max(0, min(w-(box[2]-box[0]), x))
                y = max(0, min(h-(box[3]-box[1]), y))
                self.vars['bar_x'].set(str(x))
                self.vars['bar_y'].set(str(y))
        except Exception as e:
            self.fail(e)
        finally:
            self.loading = False
        self.mode.set('move')
        self.store()
        self.refresh_tem(quiet=True)

    def reset_position(self):
        self.vars['bar_x'].set('')
        self.vars['bar_y'].set('')
        self.refresh_tem(quiet=True)

    def open_csv(self):
        name = filedialog.askopenfilename(filetypes=[('CSV', '*.csv')])
        if name:
            try:
                self.set_csv(Path(name))
            except Exception as e:
                self.fail(e)

    def set_csv(self, path):
        import csv
        with path.open(encoding='utf-8-sig', newline='') as f:
            fields = csv.DictReader(f).fieldnames or []
        columns = [c for c in fields if c.strip()]
        if not columns:
            raise ValueError('CSV has no named columns')
        self.csv_path = path
        self.csv_label.config(text=path.name)
        self.column_widget.configure(values=columns)
        if self.vars['column'].get() not in columns:
            self.vars['column'].set('diameter_nm' if 'diameter_nm' in columns else columns[0])

    def dist_args(self, out):
        if not self.csv_path:
            raise ValueError('Please open a diameter CSV')
        a = core.create_parser().parse_args([])
        a.csv = self.csv_path
        a.column = self.vars['column'].get()
        a.bins = int(self.vars['bins'].get())
        a.bin_width = core.positive(self.vars['bin_width'].get()) if self.vars['bin_width'].get().strip() else None
        a.y_mode = self.vars['y_mode'].get()
        a.dpi = int(self.vars['dpi'].get())
        a.pdf = self.pdf.get()
        a.output_dir = Path(out)
        if a.bins < 1 or a.dpi < 300:
            raise ValueError('Bins must be positive; DPI must be at least 300')
        return a

    def refresh_distribution(self, quiet=False):
        try:
            args = self.dist_args(self.temp.name)
            # Preview only needs PNG. PDF is written on explicit export.
            args.pdf = False
            r = core.distribution(args)
            with Image.open(Path(self.temp.name)/'size_distribution.png') as im:
                self.preview_image = im.copy()
            self.view = 'distribution'
            self.info.set(f"Mean ± std = {r['mean_nm']:.4f} ± {r['std_nm']:.4f} nm  |  N = {r['N']}  |  Gaussian MLE (ddof=0)")
            self.status.set('Distribution preview updated')
            self.draw_preview()
        except Exception as e:
            self.fail(e, quiet)

    def export_current(self):
        if self.view == 'distribution':
            self.export_distribution()
            return
        if not self.current:
            messagebox.showinfo('Add image', 'Please add a TIFF first.')
            return
        out = filedialog.askdirectory(title='Export TIFF + PNG to folder')
        if not out:
            return
        try:
            r = core.redraw(self.current, self.get_args(out=out))
            (Path(out)/(self.current.stem+'_scalebar_report.json')).write_text(json.dumps(r, indent=2), encoding='utf-8')
            self.status.set(f'Exported TIFF + PNG to {out}')
            messagebox.showinfo('Export complete', f'TIFF + PNG saved to:\n{out}')
        except Exception as e:
            self.fail(e)

    def export_distribution(self):
        out = filedialog.askdirectory(title='Export distribution PNG / PDF')
        if not out:
            return
        try:
            r = core.distribution(self.dist_args(out))
            (Path(out)/'size_distribution_report.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
            messagebox.showinfo('Export complete', f'Distribution saved to:\n{out}')
        except Exception as e:
            self.fail(e)

    def export_all(self):
        self.store()
        if not self.files:
            return
        if len({p.stem.lower() for p in self.files}) != len(self.files):
            self.fail(ValueError('Duplicate image stems: export these images separately to different folders.'))
            return
        out = filedialog.askdirectory(title='Export all TEM images')
        if not out:
            return
        try:
            # Validate every image before writing any output.
            jobs = [(p, self.get_args(self.settings[str(p)], out)) for p in self.files]
            for path, args in jobs:
                core.redraw(path, copy.copy(args), render_only=True)
            reports = [core.redraw(path, args) for path, args in jobs]
            (Path(out)/'tem_export_report.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
            messagebox.showinfo('Export complete', f'{len(reports)} images exported to:\n{out}')
        except Exception as e:
            self.fail(e)

    def save_project(self):
        self.store()
        name = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('TEM project', '*.json')])
        if name:
            try:
                obj = {'version': 1, 'images': self.settings, 'csv': str(self.csv_path) if self.csv_path else None,
                       'distribution': {k: self.vars[k].get() for k in ('column', 'bins', 'bin_width', 'y_mode', 'dpi')}}
                Path(name).write_text(json.dumps(obj, indent=2), encoding='utf-8')
                self.status.set('Project saved')
            except Exception as e:
                self.fail(e)

    def session_data(self):
        self.store()
        return {'version': 1, 'images': {str(p): self.settings[str(p)] for p in self.files},
                'csv': str(self.csv_path) if self.csv_path else None,
                'distribution': {k: self.vars[k].get() for k in ('column', 'bins', 'bin_width', 'y_mode', 'dpi')},
                'current': str(self.current) if self.current else None, 'view': self.view, 'pdf': self.pdf.get()}

    def save_update_session(self):
        folder = updater.data_directory()
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'resume.json').write_text(json.dumps(self.session_data(), indent=2), encoding='utf-8')
        if self.pending:
            self.after_cancel(self.pending)
            self.pending = None
        self.temp.cleanup()

    def restore_update_session(self):
        path = updater.data_directory()/'resume.json'
        if not path.exists():
            return
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
            self.settings = {p: s for p, s in obj['images'].items() if Path(p).is_file()}
            self.load_files(list(self.settings))
            current = obj.get('current')
            if current and Path(current) in self.files:
                self.listbox.selection_clear(0, 'end')
                self.listbox.selection_set(self.files.index(Path(current)))
                self.select_file()
            if obj.get('csv') and Path(obj['csv']).is_file():
                self.set_csv(Path(obj['csv']))
            self.loading = True
            for key, value in obj.get('distribution', {}).items():
                if key in self.vars:
                    self.vars[key].set(value)
            self.loading = False
            self.pdf.set(obj.get('pdf', True))
            if obj.get('view') == 'distribution' and self.csv_path:
                self.refresh_distribution(quiet=True)
            path.unlink()
            self.status.set('Session restored after update')
        except Exception as e:
            self.loading = False
            self.fail(e, quiet=True)

    def mark_update_ready(self):
        value = os.environ.pop('TEM_UPDATE_HEALTH_FILE', None)
        if value:
            path = Path(value).resolve()
            base = (updater.data_directory()/'updates').resolve()
            if path.name == 'new-app-ready' and path.parent.parent == base:
                path.write_text('ready')

    def open_project(self):
        name = filedialog.askopenfilename(filetypes=[('TEM project', '*.json')])
        if not name:
            return
        try:
            obj = json.loads(Path(name).read_text(encoding='utf-8-sig'))
            missing = [p for p in obj['images'] if not Path(p).exists()]
            if missing:
                raise ValueError('Project image not found: '+missing[0])
            self.current = None
            self.files = []
            self.listbox.delete(0, 'end')
            self.settings = obj['images']
            self.load_files(list(self.settings))
            if obj.get('csv'):
                self.set_csv(Path(obj['csv']))
            for k, v in obj.get('distribution', {}).items():
                if k in self.vars:
                    self.vars[k].set(v)
        except Exception as e:
            self.fail(e)

    def close(self):
        if self.pending:
            self.after_cancel(self.pending)
        self.temp.cleanup()
        self.destroy()


def packaged_self_test(report_path):
    """Exercise preview and both export modes inside the frozen executable."""
    result = {'success': False}
    app = None
    try:
        app = TEMStudio(enable_updates=False)
        app.withdraw()
        app.update()
        if not app.title().startswith(APP_NAME) or app.app_icon.width() != 64 or app.header_icon.width() != 42:
            raise RuntimeError('Application name or icon not applied')
        app.geometry('1000x550')
        app.deiconify()
        app.update()
        scroll = app.scroll_tabs[0]
        scroll.canvas.yview_moveto(1)
        app.update()
        if scroll.canvas.yview()[0] <= 0:
            raise RuntimeError('Left settings pane did not scroll in a small window')
        app.withdraw()
        folder = Path(app.temp.name)
        csv_path = folder / 'diameters.csv'
        csv_path.write_text('diameter_nm\n40\n45\n50\n55\n60\n65\n70\n', encoding='utf-8')
        app.set_csv(csv_path)
        app.pdf.set(True)
        app.refresh_distribution(quiet=True)
        if app.view != 'distribution':
            raise RuntimeError(app.status.get())
        if (folder / 'size_distribution.pdf').exists():
            raise RuntimeError('Preview unexpectedly wrote PDF')
        checks = []
        import numpy as np
        inset_source = folder/'inset-check.tif'
        tifffile.imwrite(inset_source, np.full((800, 1024), 145, dtype=np.uint8))
        inset_args = core.create_parser().parse_args(['--nm-per-pixel', '0.5',
            '--erase-box', '0,750,100,800', '--inset-roi', '50,50,150,150',
            '--inset-width', '300', '--inset-x', '600', '--inset-y', '30',
            '--inset-bar-nm', '10', '--output-dir', str(folder)])
        inset_result = core.redraw(inset_source, inset_args)
        if inset_result['inset']['bar_pixels'] != 60:
            raise RuntimeError('Inset scale calibration failed in packaged app')
        checks.append('inset: PNG + TIFF, 3x zoom and 10 nm / 60 px passed')
        inset_args.inset_no_scalebar = True
        hidden_image, hidden_report = core.redraw(inset_source, inset_args, render_only=True)
        if hidden_report['inset']['show_scalebar'] or not np.all(np.asarray(hidden_image)[35:325, 605:895] == 145):
            raise RuntimeError('Inset scale bar visibility switch failed')
        checks.append('inset scale bar: hidden without changing inset pixels')
        # Exercise the same cryptography dependency and bundled trust config
        # used by update discovery inside the frozen executable.
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        test_key = Ed25519PrivateKey.generate()
        public = base64.b64encode(test_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        payload = {'schema': 1, 'version': '99.0.0', 'assets': {updater.platform_key(): {
            'url': 'https://example.invalid/update', 'size': 1, 'sha256': '0'*64,
            'format': 'app-zip' if sys.platform == 'darwin' else 'exe'}}}
        envelope = {'payload': payload, 'signature': base64.b64encode(test_key.sign(updater.canonical(payload))).decode()}
        updater.verify_manifest(envelope, public, __version__)
        if not updater.bundled_config().get('public_key'):
            raise RuntimeError('Bundled updater public key missing')
        mac_ocr = 'not run on this platform'
        if sys.platform == 'darwin':
            import numpy as np
            from PIL import ImageDraw, ImageFont
            array = np.full((800, 1024), 145, dtype=np.uint8)
            array[700:] = 0
            array[745:753, 420:571] = 255
            image = Image.fromarray(array)
            ImageDraw.Draw(image).text((595, 714), '50 nm', font=ImageFont.load_default(size=44), fill=255)
            source = folder/'native_50nm_scale.tif'
            tifffile.imwrite(source, np.asarray(image))
            app.load_files([str(source)])
            if app.report is None:
                raise RuntimeError('Native scale OCR failed: '+app.status.get())
            if app.vars['original_bar_nm'].get() != '50' or app.vars['original_bar_px'].get() != '151' or app.vars['bar_nm'].get() != '50':
                raise RuntimeError('Native 50 nm auto-import did not populate calibration')
            if app.report['bar_pixels'] != 151:
                raise RuntimeError('Default new bar does not match the original 50 nm / 151 px')
            if app.preview_image.size != (1024, 700) or not app.report.get('removed_black_footer'):
                raise RuntimeError('Original black scale-bar footer was not removed')
            mac_ocr = 'passed: original and default new bar 50 nm / 151 px, fields populated'
        for mode in ('count', 'frequency'):
            app.vars['y_mode'].set(mode)
            r = core.distribution(app.dist_args(folder))
            png = folder / 'size_distribution.png'
            pdf = folder / 'size_distribution.pdf'
            with Image.open(png) as image:
                if image.info.get('dpi', (0, 0))[0] < 299.9:
                    raise RuntimeError('PNG resolution is below 300 dpi')
                image.verify()
            if not pdf.read_bytes().startswith(b'%PDF-'):
                raise RuntimeError('Invalid PDF export')
            if r['N'] != 7 or abs(r['mean_nm']-55) > 1e-9:
                raise RuntimeError('Incorrect distribution statistics')
            checks.append(mode + ': PNG + PDF + statistics passed')
        result = {'success': True, 'version': __version__, 'application_name': APP_NAME,
                  'application_icon': 'loaded', 'frozen': bool(getattr(sys, 'frozen', False)),
                  'small_window_scroll': 'passed at 1000x550',
                  'signed_update_verification': 'passed',
                  'mac_scale_ocr': mac_ocr,
                  'preview': 'passed with PDF option selected', 'checks': checks}
    except Exception as e:
        import traceback
        result['error'] = str(e)
        result['traceback'] = traceback.format_exc()
    finally:
        if app:
            app.close()
        Path(report_path).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['success'] else 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--apply-update':
        import update_installer
        sys.exit(update_installer.run(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        sys.exit(packaged_self_test(sys.argv[2]))
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    TEMStudio().mainloop()
