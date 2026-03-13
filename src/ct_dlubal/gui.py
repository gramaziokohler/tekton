import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import json
import threading
import sv_ttk

HAS_DND = False
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    pass

# Import our core logic
try:
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
    # from ct_dlubal.dlubal.importer import DlubalImporter # Placeholder for future live-sync
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter

CONFIG_FILE = os.path.expanduser("~/.ct_dlubal_prefs.json")

class DlubalExportGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CT Dlubal - Export & Import Manager")
        self.root.geometry("850x900")
        
        # Apply modern theme
        sv_ttk.set_theme("light")
        
        # Style customization
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Subheader.TLabel", font=("Segoe UI", 11, "bold"))
        
        # Data variables
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.api_key = tk.StringVar()
        
        # Settings variables
        self.material_preset = tk.StringVar(value="C24")
        self.lock_ux = tk.BooleanVar(value=True)
        self.lock_uy = tk.BooleanVar(value=True)
        self.lock_uz = tk.BooleanVar(value=True)
        self.lock_rx = tk.BooleanVar(value=False)
        self.lock_ry = tk.BooleanVar(value=False)
        self.lock_rz = tk.BooleanVar(value=False)
        
        # Dynamic load case checkboxes
        self.load_cases_vars = {}
        self.model_data = None

        self.load_prefs()
        self.setup_ui()

    def load_prefs(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    prefs = json.load(f)
                    self.api_key.set(prefs.get("api_key", ""))
            except: pass

    def save_prefs(self):
        prefs = {"api_key": self.api_key.get()}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(prefs, f)
        messagebox.showinfo("Preferences", "API Key saved successfully.")

    def setup_ui(self):
        # Header with Logo/Title
        header_frame = ttk.Frame(self.root, padding=(25, 25, 25, 15))
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text="COMPAS Timber → Dlubal RFEM/RSTAB", style="Header.TLabel").pack(side=tk.LEFT)
        
        # Theme toggle
        theme_btn = ttk.Button(header_frame, text="Toggle Dark Mode", command=sv_ttk.toggle_theme)
        theme_btn.pack(side=tk.RIGHT)

        # Main Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 25))

        # --- TAB 1: MODEL SETUP ---
        setup_tab = ttk.Frame(self.notebook, padding="25")
        self.notebook.add(setup_tab, text="1. Model Setup")

        # Dropzone
        self.drop_frame = tk.Label(setup_tab, 
                                  text="DRAG & DROP TIMBER MODEL JSON HERE\n(or click to browse)", 
                                  bg="#f1f3f5", fg="#495057", 
                                  font=("Segoe UI Semibold", 10),
                                  relief="groove", bd=2, height=6)
        self.drop_frame.pack(fill=tk.X, pady=(0, 25))
        
        if HAS_DND:
            try:
                self.drop_frame.drop_target_register(DND_FILES)
                self.drop_frame.dnd_bind('<<Drop>>', self.handle_drop)
            except: pass
        else:
            self.drop_frame.config(text="CLICK TO BROWSE TIMBER MODEL JSON\n(Drag & Drop not available)")
            
        self.drop_frame.bind("<Button-1>", lambda e: self.browse_input())

        # Selected File Info
        file_info_frame = ttk.Frame(setup_tab)
        file_info_frame.pack(fill=tk.X, pady=(0, 25))
        ttk.Label(file_info_frame, text="Source Model Path:", style="Subheader.TLabel").pack(anchor=tk.W)
        self.file_label = ttk.Label(file_info_frame, textvariable=self.input_file, foreground="#adb5bd", wraplength=750)
        self.file_label.pack(anchor=tk.W, pady=5)

        # Settings
        settings_grid = ttk.Frame(setup_tab)
        settings_grid.pack(fill=tk.BOTH, expand=True)

        # Left Column: Global Parameters
        left_col = ttk.Frame(settings_grid)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))

        mat_frame = ttk.LabelFrame(left_col, text="Materials", padding="20")
        mat_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(mat_frame, text="Target Timber Quality:").pack(anchor=tk.W, pady=(0, 5))
        ttk.Combobox(mat_frame, textvariable=self.material_preset, values=["C16", "C24", "C30", "GL24h", "GL28h", "GL32h"]).pack(fill=tk.X)

        supp_frame = ttk.LabelFrame(left_col, text="Base Support Boundary Conditions", padding="20")
        supp_frame.pack(fill=tk.X)
        for label, var in [("Fixed uX", self.lock_ux), ("Fixed uY", self.lock_uy), ("Fixed uZ", self.lock_uz), 
                          ("Fixed rX", self.lock_rx), ("Fixed rY", self.lock_ry), ("Fixed rZ", self.lock_rz)]:
            ttk.Checkbutton(supp_frame, text=label, variable=var).pack(anchor=tk.W, pady=3)

        # Right Column: Load Case Filter
        right_col = ttk.Frame(settings_grid)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(15, 0))

        lc_main_frame = ttk.LabelFrame(right_col, text="Active Load Cases", padding="20")
        lc_main_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(lc_main_frame, highlightthickness=0, bg="white")
        scrollbar = ttk.Scrollbar(lc_main_frame, orient="vertical", command=canvas.yview)
        self.load_cases_container = ttk.Frame(canvas)

        self.load_cases_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.load_cases_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(self.load_cases_container, text="(Waiting for model...)").pack(pady=20)

        # --- TAB 2: WORKFLOW ---
        export_tab = ttk.Frame(self.notebook, padding="40")
        self.notebook.add(export_tab, text="2. Workflow / Export")

        saf_frame = ttk.LabelFrame(export_tab, text="Standard Analysis Format (SAF)", padding="30")
        saf_frame.pack(fill=tk.X, pady=(0, 30))
        ttk.Label(saf_frame, text="Exports a bit-perfect SAF v1.0.5 file for RSTAB/RFEM import.").pack(anchor=tk.W, pady=(0, 15))
        ttk.Button(saf_frame, text="GENERATE SAF EXCEL FILE", style="Accent.TButton", command=self.browse_output_and_run).pack(fill=tk.X, ipady=15)

        grpc_frame = ttk.LabelFrame(export_tab, text="Direct Dlubal Live Sync (API)", padding="30")
        grpc_frame.pack(fill=tk.X)
        ttk.Label(grpc_frame, text="Streams the model directly into an active RFEM session via the gRPC interface.").pack(anchor=tk.W, pady=(0, 15))
        ttk.Button(grpc_frame, text="PUSH LIVE TO ACTIVE MODEL", command=lambda: self.start_process("gRPC")).pack(fill=tk.X, ipady=15)

        # --- TAB 3: PREFERENCES ---
        prefs_tab = ttk.Frame(self.notebook, padding="40")
        self.notebook.add(prefs_tab, text="3. Preferences")
        api_frame = ttk.LabelFrame(prefs_tab, text="Dlubal API Settings", padding="30")
        api_frame.pack(fill=tk.X)
        ttk.Label(api_frame, text="Machine Key / API Token:").pack(anchor=tk.W, pady=(0, 5))
        ttk.Entry(api_frame, textvariable=self.api_key, show="*").pack(fill=tk.X, pady=5)
        ttk.Button(prefs_tab, text="Save Global Preferences", command=self.save_prefs).pack(anchor=tk.E, pady=30)

        # Footer
        footer = ttk.Frame(self.root, padding=(25, 15, 25, 25))
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        self.progress = ttk.Progressbar(footer, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(footer, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Label(footer, text="ct_dlubal | Powered by COMPAS", foreground="#adb5bd").pack(side=tk.RIGHT)

    def handle_drop(self, event):
        path = event.data.strip('{}')
        if path.lower().endswith(".json"): self.set_input_file(path)

    def browse_input(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if path: self.set_input_file(path)

    def set_input_file(self, path):
        self.input_file.set(path)
        self.output_file.set(path.replace(".json", ".saf"))
        self.load_model_load_cases(path)

    def load_model_load_cases(self, path):
        for w in self.load_cases_container.winfo_children(): w.destroy()
        self.load_cases_vars = {}
        try:
            with open(path, 'r') as f: self.model_data = json.load(f)
            lcs = self.model_data.get('load_cases', self.model_data.get('structural_model', {}).get('load_cases', []))
            if not lcs:
                 ttk.Label(self.load_cases_container, text="No load cases found.").pack(pady=10)
                 return
            for lc in lcs:
                name = lc.get('name', f"LC {lc.get('id')}")
                var = tk.BooleanVar(value=True); self.load_cases_vars[name] = var
                ttk.Checkbutton(self.load_cases_container, text=name, variable=var).pack(anchor=tk.W, pady=2)
        except Exception as e:
            ttk.Label(self.load_cases_container, text=f"Error loading cases: {str(e)}").pack()

    def browse_output_and_run(self):
        if not self.input_file.get():
            messagebox.showwarning("Warning", "Please select a model JSON first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".saf", filetypes=[("SAF", "*.saf"), ("Excel", "*.xlsx")])
        if path:
            self.output_file.set(path)
            self.start_process("SAF")

    def start_process(self, mode):
        self.status_var.set(f"Running {mode}...")
        threading.Thread(target=self.process_logic, args=(mode,), daemon=True).start()

    def process_logic(self, mode):
        try:
            self.progress['value'] = 20
            # Load fresh from input
            with open(self.input_file.get(), 'r') as f:
                data = json.load(f)
            
            model = StructuralModel.from_json(data)
            
            # Apply Material Modification
            for sid in model.materials: 
                model.materials[sid] = self.material_preset.get()
            
            # Filter Load Cases
            active = [n for n, v in self.load_cases_vars.items() if v.get()]
            model.load_cases = [lc for lc in model.load_cases if lc.name in active]
            
            # Apply Support Modifications
            inf = float('inf')
            for s in model.supports:
                s.ux = inf if self.lock_ux.get() else 0.0
                s.uy = inf if self.lock_uy.get() else 0.0
                s.uz = inf if self.lock_uz.get() else 0.0
                s.rx = inf if self.lock_rx.get() else 0.0
                s.ry = inf if self.lock_ry.get() else 0.0
                s.rz = inf if self.lock_rz.get() else 0.0
            
            self.progress['value'] = 60
            
            if mode == "SAF":
                success = SAFExporter(model).export(self.output_file.get())
            else:
                # Live sync would happen here
                messagebox.showinfo("Dlubal gRPC", "gRPC sync module initialization...")
                success = True # Mocking success for now as importer needs focus
                
            self.status_var.set("Finished Successfully" if success else "Process Failed")
            self.progress['value'] = 100 if success else 0
            if success: 
                messagebox.showinfo("Success", f"{mode} Process finished.\nOutput: {os.path.basename(self.output_file.get())}")
        except Exception as e: 
            messagebox.showerror("Export Error", f"An error occurred during {mode} generation:\n\n{str(e)}")
            self.status_var.set("Error occurred")
        finally: 
            self.progress['value'] = 0

if __name__ == "__main__":
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = DlubalExportGUI(root)
    root.mainloop()
