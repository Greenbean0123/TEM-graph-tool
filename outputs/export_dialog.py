"""Choose export filenames, image formats and optional batch inputs."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog


class ExportDialog(simpledialog.Dialog):
    def __init__(self, parent, kind, directory, formats, default_name, files=None):
        self.kind, self.directory, self.formats = kind, directory, formats
        self.default_name, self.files = default_name, files
        super().__init__(parent, title='Export '+('TEM images' if kind == 'tem' else 'size distribution'))

    def body(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Output folder').pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=(3, 10))
        self.folder = tk.StringVar(self, value=str(self.directory))
        ttk.Entry(row, textvariable=self.folder, width=53).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Browse…', command=self.browse).pack(side='left', padx=(6, 0))
        ttk.Label(frame, text='Filename prefix (blank = original names)' if self.files else 'Filename (blank = default)').pack(anchor='w')
        self.name = tk.StringVar(self)
        entry = ttk.Entry(frame, textvariable=self.name, width=64)
        entry.pack(fill='x', pady=3)
        description = 'A prefix produces prefix_001, prefix_002, …' if self.files else 'Default: '+self.default_name+' · extension is optional'
        ttk.Label(frame, text=description, wraplength=490, foreground='#64748b').pack(anchor='w', pady=(0, 10))
        ttk.Label(frame, text='Select output formats').pack(anchor='w')
        formats = [('png', 'PNG (.png)'), ('tif', 'TIFF (.tif)')] if self.kind == 'tem' else [('png', 'PNG (.png)'), ('pdf', 'PDF (.pdf)')]
        self.format_vars = {}
        for value, label in formats:
            variable = tk.BooleanVar(self, value=value in self.formats)
            self.format_vars[value] = variable
            ttk.Checkbutton(frame, text=label, variable=variable).pack(anchor='w', pady=2)
        self.report = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(frame, text='Also save settings / statistics report (JSON)', variable=self.report).pack(anchor='w', pady=(8, 4))
        if self.files:
            ttk.Label(frame, text='Select images (Ctrl / Command / Shift to select several)').pack(anchor='w', pady=(10, 3))
            row = ttk.Frame(frame)
            row.pack(fill='both', expand=True)
            self.selection = tk.Listbox(row, selectmode='extended', exportselection=False, height=min(7, len(self.files)), width=64)
            scrollbar = ttk.Scrollbar(row, orient='vertical', command=self.selection.yview)
            self.selection.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            self.selection.pack(side='left', fill='both', expand=True)
            for file in self.files:
                self.selection.insert('end', str(file))
            self.selection.selection_set(0, 'end')
        return entry

    def browse(self):
        result = filedialog.askdirectory(parent=self, initialdir=self.folder.get() or None)
        if result:
            self.folder.set(result)

    def validate(self):
        import tem_scalebar_distribution as core
        try:
            core.export_stem('.', self.name.get(), self.default_name, {'.png', '.tif', '.tiff'} if self.kind == 'tem' else {'.png', '.pdf'})
        except ValueError as error:
            messagebox.showerror('Filename', str(error), parent=self)
            return False
        if not self.folder.get().strip():
            messagebox.showerror('Output folder', 'Choose an output folder.', parent=self)
            return False
        if not any(variable.get() for variable in self.format_vars.values()):
            messagebox.showerror('Output format', 'Select at least one output format.', parent=self)
            return False
        if self.files and not self.selection.curselection():
            messagebox.showerror('Select images', 'Select at least one TEM image.', parent=self)
            return False
        return True

    def apply(self):
        self.result = dict(directory=Path(self.folder.get().strip()).expanduser(), name=self.name.get().strip(),
            formats=[value for value, variable in self.format_vars.items() if variable.get()],
            report=self.report.get(), files=[self.files[i] for i in self.selection.curselection()] if self.files else None)
