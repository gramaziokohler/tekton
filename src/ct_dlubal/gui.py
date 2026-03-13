import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import json
import threading

# Import our core logic
try:
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
    from ct_dlubal.dlubal.importer import DlubalImporter
except ImportError:
    # Fallback for local development if not installed as package
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
    from ct_dlubal.dlubal.importer import DlubalImporter

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import json
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

# Import our core logic
try:
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
    from ct_dlubal.dlubal.importer import DlubalImporter
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
    from ct_dlubal.dlubal.importer import DlubalImporter

CONFIG_FILE = os.path.expanduser("~/.ct_dlubal_prefs.json")

class DlubalExportGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CT Dlubal - Export & Import Manager")
        self.root.geometry("700x750")
        
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
        # Main Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- TAB 1: MODEL SETUP ---
        setup_tab = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(setup_tab, text="1. Model Setup")

        # Drag & Drop Area
        self.drop_frame = tk.Label(setup_tab, text="DRAG & DROP TIMBER MODEL JSON HERE\n(or click to browse)", 
                                  bg="#f0f0f0", fg="#666666", relief="dashed", bd=2, height=4)
        self.drop_frame.pack(fill=tk.X, pady=(0, 15))
        
        if HAS_DND:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind('<<Drop>>', self.handle_drop)
        
        self.drop_frame.bind("<Button-1>", lambda e: self.browse_input())

        # Selected File Label
        file_info_frame = ttk.Frame(setup_tab)
        file_info_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(file_info_frame, text="Selected File:").pack(side=tk.LEFT)
        ttk.Label(file_info_frame, textvariable=self.input_file, foreground="blue", wraplength=500).pack(side=tk.LEFT, padx=10)

        # Settings
        settings_container = ttk.Frame(setup_tab)
        settings_container.pack(fill=tk.BOTH, expand=True)

        # Materials
        mat_frame = ttk.LabelFrame(settings_container, text="Material Preset", padding="10")
        mat_frame.pack(fill=tk.X, pady=5)
        ttk.Combobox(mat_frame, textvariable=self.material_preset, values=["C16", "C24", "C30", "GL24h", "GL28h", "GL32h"]).pack(fill=tk.X)

        # Supports
        supp_frame = ttk.LabelFrame(settings_container, text="Support Degrees of Freedom (Locked)", padding="10")
        supp_frame.pack(fill=tk.X, pady=5)
        check_f = ttk.Frame(supp_frame)
        check_f.pack(fill=tk.X)
        for label, var in [("uX", self.lock_ux), ("uY", self.lock_uy), ("uZ", self.lock_uz), ("rX", self.lock_rx), ("rY", self.lock_ry), ("rZ", self.lock_rz)]:
            ttk.Checkbutton(check_f, text=label, variable=var).pack(side=tk.LEFT, padx=5)

        # Load Cases
        self.lc_group = ttk.LabelFrame(settings_container, text="Load Cases to Export", padding="10")
        self.lc_group.pack(fill=tk.BOTH, expand=True, pady=5)
        self.load_cases_container = ttk.Frame(self.lc_group)
        self.load_cases_container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.load_cases_container, text="No model loaded.").pack()

        # --- TAB 2: EXPORT ---
        export_tab = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(export_tab, text="2. Export")

        # SAF Option
        saf_frame = ttk.LabelFrame(export_tab, text="Option A: Save to SAF File", padding="15")
        saf_frame.pack(fill=tk.X, pady=10)
        ttk.Label(saf_frame, text="Output Path:").pack(anchor=tk.W)
        path_f = ttk.Frame(saf_frame)
        path_f.pack(fill=tk.X, pady=5)
        ttk.Entry(path_f, textvariable=self.output_file).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(path_f, text="...", width=3, command=self.browse_output).pack(side=tk.RIGHT)
        ttk.Button(saf_frame, text="GENERATE SAF", command=lambda: self.start_process("SAF")).pack(fill=tk.X, pady=(10,0))

        # gRPC Option
        grpc_frame = ttk.LabelFrame(export_tab, text="Option B: Direct Push to Dlubal", padding="15")
        grpc_frame.pack(fill=tk.X, pady=10)
        ttk.Label(grpc_frame, text="Live transfer via gRPC interface.", font=("", 9, "italic")).pack(pady=5)
        ttk.Button(grpc_frame, text="PUSH LIVE", command=lambda: self.start_process("gRPC")).pack(fill=tk.X)

        # --- TAB 3: PREFERENCES ---
        prefs_tab = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(prefs_tab, text="3. Preferences")

        api_frame = ttk.LabelFrame(prefs_tab, text="Dlubal API Connection", padding="15")
        api_frame.pack(fill=tk.X)
        ttk.Label(api_frame, text="Server License / API Key (if required):").pack(anchor=tk.W)
        ttk.Entry(api_frame, textvariable=self.api_key, show="*").pack(fill=tk.X, pady=5)
        ttk.Button(api_frame, text="Save Preferences", command=self.save_prefs).pack(anchor=tk.E, pady=10)

        # Footer
        status_frame = ttk.Frame(self.root, padding="10")
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.progress = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)

    def handle_drop(self, event):
        file_path = event.data.strip('{}')
        if file_path.lower().endswith(".json"):
            self.set_input_file(file_path)
        else:
            messagebox.showwarning("Invalid File", "Please drop a .json file.")

    def browse_input(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if path: self.set_input_file(path)

    def set_input_file(self, path):
        self.input_file.set(path)
        self.output_file.set(path.replace(".json", ".saf"))
        self.load_model_load_cases(path)
        self.drop_frame.config(text=f"LOADED: {os.path.basename(path)}", fg="green")

    def load_model_load_cases(self, path):
        for widget in self.load_cases_container.winfo_children(): widget.destroy()
        self.load_cases_vars = {}
        try:
            with open(path, 'r') as f: self.model_data = json.load(f)
            lcs = self.model_data.get('load_cases', self.model_data.get('structural_model', {}).get('load_cases', []))
            if not lcs: ttk.Label(self.load_cases_container, text="No load cases found.").pack(); return
            for lc in lcs:
                name = lc.get('name', f"LC {lc.get('id')}")
                var = tk.BooleanVar(value=True); self.load_cases_vars[name] = var
                ttk.Checkbutton(self.load_cases_container, text=name, variable=var).pack(anchor=tk.W)
        except Exception as e: ttk.Label(self.load_cases_container, text=f"Read error: {str(e)}").pack()

    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".saf", filetypes=[("SAF", "*.saf"), ("Excel", "*.xlsx")])
        if path: self.output_file.set(path)

    def start_process(self, mode):
        if not self.input_file.get(): messagebox.showerror("Error", "No input file."); return
        self.status_var.set(f"Processing {mode}...")
        threading.Thread(target=self.process_logic, args=(mode,), daemon=True).start()

    def process_logic(self, mode):
        # (Rest of logic remains same as before)
        try:
            self.progress['value'] = 20
            model = StructuralModel.from_json(self.model_data)
            for sid in list(model.materials.keys()): model.materials[sid] = self.material_preset.get()
            active_lcs = [n for n, v in self.load_cases_vars.items() if v.get()]
            model.load_cases = [lc for lc in model.load_cases if lc.name in active_lcs]
            inf = float('inf')
            for s in model.supports:
                s.ux = inf if self.lock_ux.get() else 0.0; s.uy = inf if self.lock_uy.get() else 0.0; s.uz = inf if self.lock_uz.get() else 0.0
                s.rx = inf if self.lock_rx.get() else 0.0; s.ry = inf if self.lock_ry.get() else 0.0; s.rz = inf if self.lock_rz.get() else 0.0
            
            self.progress['value'] = 60
            success = SAFExporter(model).export(self.output_file.get()) if mode == "SAF" else DlubalImporter(model).push()
            
            self.status_var.set("Success" if success else "Failed")
            self.progress['value'] = 100 if success else 0
            if success: messagebox.showinfo("Success", f"{mode} completed.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally: self.progress['value'] = 0

if __name__ == "__main__":
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
    app = DlubalExportGUI(root)
    root.mainloop()

    def browse_input(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if filename:
            self.input_file.set(filename)
            self.load_model_load_cases(filename)
            if not self.output_file.get():
                self.output_file.set(filename.replace(".json", ".saf"))

    def load_model_load_cases(self, path):
        # Clear existing checkboxes
        for widget in self.load_cases_container.winfo_children():
            widget.destroy()
        self.load_cases_vars = {}

        try:
            with open(path, 'r') as f:
                self.model_data = json.load(f)
            
            # Look for load cases in either timber_model or directly
            lcs = []
            if 'load_cases' in self.model_data:
                lcs = self.model_data['load_cases']
            elif 'structural_model' in self.model_data and 'load_cases' in self.model_data['structural_model']:
                lcs = self.model_data['structural_model']['load_cases']

            if not lcs:
                ttk.Label(self.load_cases_container, text="No load cases found in file.").pack()
                return

            for lc in lcs:
                name = lc.get('name', f"LC {lc.get('id', '?')}")
                var = tk.BooleanVar(value=True)
                self.load_cases_vars[name] = var
                ttk.Checkbutton(self.load_cases_container, text=name, variable=var).pack(anchor=tk.W)

        except Exception as e:
            ttk.Label(self.load_cases_container, text=f"Error reading cases: {str(e)}").pack()

    def browse_output(self):
        filename = filedialog.asksaveasfilename(defaultextension=".saf", filetypes=[("SAF Files", "*.saf"), ("Excel", "*.xlsx")])
        if filename:
            self.output_file.set(filename)

    def start_process(self, mode):
        if not self.input_file.get():
            messagebox.showerror("Error", "Please select an input path.")
            return
        if mode == "SAF" and not self.output_file.get():
            messagebox.showerror("Error", "Please select an output path.")
            return

        self.status_var.set(f"Running {mode} export...")
        threading.Thread(target=self.process_logic, args=(mode,), daemon=True).start()

    def process_logic(self, mode):
        try:
            self.progress['value'] = 10
            # 1. Adapt model based on UI settings
            # We recreate the structural model with settings applied
            model = StructuralModel.from_json(self.model_data)
            
            # Apply Material Preset
            for i in range(len(model.sections)):
                # Simplified: overwrite all timber materials with preset for now 
                # or match mat_id 1
                model.materials[model.sections[i].material_id] = self.material_preset.get()
            
            # Filter Load Cases
            active_lc_names = [name for name, var in self.load_cases_vars.items() if var.get()]
            model.load_cases = [lc for lc in model.load_cases if lc.name in active_lc_names]

            # Apply Support Locks
            inf = float('inf')
            for supp in model.supports:
                supp.ux = inf if self.lock_ux.get() else 0.0
                supp.uy = inf if self.lock_uy.get() else 0.0
                supp.uz = inf if self.lock_uz.get() else 0.0
                supp.rx = inf if self.lock_rx.get() else 0.0
                supp.ry = inf if self.lock_ry.get() else 0.0
                supp.rz = inf if self.lock_rz.get() else 0.0

            self.progress['value'] = 50
            
            if mode == "SAF":
                exporter = SAFExporter(model)
                success = exporter.export(self.output_file.get())
            else:
                importer = DlubalImporter(model)
                success = importer.push()

            if success:
                self.status_var.set("Process finished successfully.")
                self.progress['value'] = 100
                messagebox.showinfo("Success", f"{mode} process completed.")
            else:
                self.status_var.set("Process failed.")
                messagebox.showerror("Error", "Export/Import failed.")

        except Exception as e:
            self.status_var.set("Critical Error.")
            messagebox.showerror("Error", f"Technical error:\n{str(e)}")
        finally:
            self.progress['value'] = 0

if __name__ == "__main__":
    root = tk.Tk()
    gui = DlubalExportGUI(root)
    root.mainloop()
