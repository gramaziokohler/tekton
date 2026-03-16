import sys
import os
import json
import threading
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QPushButton, QLabel, 
                             QComboBox, QCheckBox, QScrollArea, QFrame, 
                             QFileDialog, QMessageBox, QProgressBar, QLineEdit,
                             QGroupBox, QTextEdit)
from PySide6.QtCore import Qt, Signal, QSize, QObject
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QTextCursor

# Stream class to catch stdout/stderr
class ConsoleStream(QObject):
    message = Signal(str)
    def write(self, text):
        self.message.emit(str(text))
    def flush(self):
        pass

# Core logic imports
try:
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
    from ct_dlubal.dlubal.importer import DlubalImporter
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
    from ct_dlubal.dlubal.importer import DlubalImporter

CONFIG_FILE = os.path.expanduser("~/.ct_dlubal_prefs.json")

class DropZone(QFrame):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setLineWidth(2)
        self.setMinimumHeight(80)
        
        layout = QVBoxLayout(self)
        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Segoe UI Semibold", 9))
        layout.addWidget(self.label)
        
        self.set_content("DRAG & DROP TIMBER MODEL JSON HERE\n(or click to browse)", False)

    def set_content(self, text, is_file=False):
        self.label.setText(text)
        if is_file:
            self.setStyleSheet("""
                DropZone {
                    background-color: #ffffff;
                    border: 1px solid #0078d4;
                    border-radius: 6px;
                    color: #0078d4;
                }
            """)
        else:
            self.setStyleSheet("""
                DropZone {
                    background-color: #f8f9fa;
                    border: 2px dashed #dee2e6;
                    border-radius: 6px;
                    color: #6c757d;
                }
                DropZone:hover {
                    background-color: #e9ecef;
                    border-color: #adb5bd;
                }
            """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files and files[0].lower().endswith(".json"):
            self.fileDropped.emit(files[0])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(self, "Open Model JSON", "", "JSON Files (*.json)")
            if path: self.fileDropped.emit(path)

class DlubalExportGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CT Dlubal")
        self.setMinimumSize(540, 620)
        self.resize(540, 620)

        self.setStyleSheet("""
            QMainWindow { background-color: #ffffff; }
            QTabWidget::pane { border: 1px solid #dee2e6; top: -1px; background: white; }
            QTabBar::tab {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 8px 15px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { background: white; border-bottom-color: white; font-weight: bold; }
            QGroupBox { font-weight: bold; border: 1px solid #e9ecef; border-radius: 4px; margin-top: 10px; padding-top: 10px; }
            QPushButton { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #e9ecef; }
            QPushButton#accentBtn { background-color: #0078d4; color: white; font-weight: bold; border: none; }
            QPushButton#accentBtn:hover { background-color: #005a9e; }
        """)

        self.input_path = ""
        self.model_data = None
        self.load_cases_vars = {}
        self.setup_ui()
        self.load_prefs()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_l = QVBoxLayout(central)
        main_l.setContentsMargins(10, 5, 10, 10)

        self.tabs = QTabWidget()
        main_l.addWidget(self.tabs)

        # Tab 1: Setup
        setup_tab = QWidget()
        setup_l = QVBoxLayout(setup_tab)
        
        self.drop_zone = DropZone()
        self.drop_zone.fileDropped.connect(self.handle_file_loaded)
        setup_l.addWidget(self.drop_zone)

        self.path_label = QLabel("No file selected.")
        self.path_label.setStyleSheet("color: #adb5bd; font-size: 10px;")
        self.path_label.setWordWrap(True)
        setup_l.addWidget(self.path_label)

        mat_group = QGroupBox("Materials")
        mat_l = QVBoxLayout(mat_group)
        self.mat_combo = QComboBox()
        self.mat_combo.addItems(["C16", "C24", "C30", "GL24h", "GL28h", "GL32h"])
        self.mat_combo.setCurrentText("C24")
        mat_l.addWidget(self.mat_combo)
        setup_l.addWidget(mat_group)

        supp_group = QGroupBox("Supports")
        supp_l = QHBoxLayout(supp_group)
        self.supp_checks = {}
        for label in ["uX", "uY", "uZ", "rX", "rY", "rZ"]:
            cb = QCheckBox(label)
            if label.startswith("u"): cb.setChecked(True)
            self.supp_checks[label] = cb
            supp_l.addWidget(cb)
        setup_l.addWidget(supp_group)

        lc_group = QGroupBox("Select Load Cases for Export")
        lc_l = QVBoxLayout(lc_group)
        
        # Grid layout for 2 columns of checkboxes
        lc_cols = QHBoxLayout()
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        lc_cols.addLayout(left_col)
        lc_cols.addLayout(right_col)
        lc_l.addLayout(lc_cols)
        
        self.load_cases_vars = {}
        standard_cases = [
            "1: Self Weight", "2: Permanent",
            "3: Live Load", "4: Snow",
            "5: Wind +X", "6: Wind -X",
            "7: Wind +Y", "8: Wind -Y"
        ]
        
        for i, name in enumerate(standard_cases):
            cb = QCheckBox(name)
            self.load_cases_vars[name] = cb
            if i % 2 == 0:
                left_col.addWidget(cb)
            else:
                right_col.addWidget(cb)
            
        left_col.addStretch()
        right_col.addStretch()
        setup_l.addWidget(lc_group)
        setup_l.addStretch() # <- remove if want to revert
        self.tabs.addTab(setup_tab, "1. Setup")

        # Tab 2: Workflow
        work_tab = QWidget()
        work_l = QVBoxLayout(work_tab)
        
        saf_g = QGroupBox("Fast SAF Export")
        saf_l = QVBoxLayout(saf_g)
        saf_btn = QPushButton("GENERATE SAF EXCEL FILE")
        saf_btn.setObjectName("accentBtn")
        saf_btn.setFixedHeight(40)
        saf_btn.clicked.connect(self.run_saf_export)
        saf_l.addWidget(saf_btn)

        work_l.addWidget(saf_g)

        grpc_g = QGroupBox("Dlubal Live Sync")
        grpc_l = QVBoxLayout(grpc_g)
        grpc_btn = QPushButton("PUSH TO RFEM/RSTAB")
        grpc_btn.setFixedHeight(40)
        grpc_btn.clicked.connect(self.run_grpc_sync)
        grpc_l.addWidget(grpc_btn)
        work_l.addWidget(grpc_g)
        
        # Console Log
        console_g = QGroupBox("Execution Log")
        console_l = QVBoxLayout(console_g)
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setFont(QFont("Consolas", 8))
        self.console_output.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6;")
        self.console_output.setFixedHeight(140)
        console_l.addWidget(self.console_output)
        work_l.addWidget(console_g)
        
        self.stream = ConsoleStream()
        self.stream.message.connect(self.update_console)
        sys.stdout = self.stream
        sys.stderr = self.stream
        
        work_l.addStretch()
        self.tabs.addTab(work_tab, "2. Workflow")

        # Tab 3: Config
        conf_tab = QWidget()
        conf_l = QVBoxLayout(conf_tab)
        api_g = QGroupBox("API Settings")
        api_l = QVBoxLayout(api_g)
        api_l.addWidget(QLabel("Dlubal Machine Key:"))
        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.Password)
        api_l.addWidget(self.api_input)
        conf_l.addWidget(api_g)
        save_btn = QPushButton("Save Preferences")
        save_btn.clicked.connect(self.save_prefs)
        conf_l.addWidget(save_btn, alignment=Qt.AlignRight)
        conf_l.addStretch()
        self.tabs.addTab(conf_tab, "3. Config")

        # Footer
        footer = QVBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        footer.addWidget(self.progress)
        status_row = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        status_row.addWidget(self.status_label)
        ver_label = QLabel("ct_dlubal v1.1")
        ver_label.setStyleSheet("color: #adb5bd; font-size: 10px;")
        status_row.addWidget(ver_label, alignment=Qt.AlignRight)
        footer.addLayout(status_row)
        main_l.addLayout(footer)

    def update_console(self, text):
        self.console_output.moveCursor(QTextCursor.End)
        self.console_output.insertPlainText(text)
        self.console_output.moveCursor(QTextCursor.End)

    def handle_file_loaded(self, path):
        self.input_path = path
        self.path_label.setText(path)
        filename = os.path.basename(path)
        self.drop_zone.set_content(f"CURRENT MODEL: {filename}\n(Click to change)", True)
        self.status_label.setText("Model loaded.")
        try:
            with open(path, "r") as f: self.model_data = json.load(f)
        except Exception as e: self.status_label.setText(f"Error: {e}")

    def create_model_from_ui(self):
        """Helper to build the structural model based on model_data and UI toggle settings."""
        if not self.model_data: return None
        
        # NOTE: Using direct dict access because model_data IS the json dict.
        # If the StructuralModel dataclass doesnt have a helper, we instantiate it manually.
        from compas.geometry import Point, Vector
        from ct_dlubal.core.model import StructuralNode, StructuralMember, StructuralSection, StructuralSupport, StructuralLoadCase
        
        data = self.model_data
        if "structural_model" in data: data = data["structural_model"]
        
        nodes = [StructuralNode(id=n["id"], point=Point(*n["point"])) for n in data.get("nodes", [])]
        members = [StructuralMember(id=m["id"], node_start=m["node_start"], node_end=m["node_end"], section_id=m["section_id"], orientation_vector=Vector(*m.get("orientation_vector", [0,0,1]))) for m in data.get("members", [])]
        sections = [StructuralSection(id=s["id"], name=s["name"], material_id=s["material_id"], width=s.get("width", 0), height=s.get("height", 0)) for s in data.get("sections", [])]
        
        # Map Materials from UI
        materials = {mat_id: self.mat_combo.currentText() for mat_id in data.get("materials", {})}
        
        # Build Supports from UI toggles
        inf = float("inf")
        ui_ux = inf if self.supp_checks["uX"].isChecked() else 0.0
        ui_uy = inf if self.supp_checks["uY"].isChecked() else 0.0
        ui_uz = inf if self.supp_checks["uZ"].isChecked() else 0.0
        ui_rx = inf if self.supp_checks["rX"].isChecked() else 0.0
        ui_ry = inf if self.supp_checks["rY"].isChecked() else 0.0
        ui_rz = inf if self.supp_checks["rZ"].isChecked() else 0.0
        
        supports = []
        for s in data.get("supports", []):
            supports.append(StructuralSupport(id=s["id"], nodes=s["nodes"], ux=ui_ux, uy=ui_uy, uz=ui_uz, rx=ui_rx, ry=ui_ry, rz=ui_rz))
            
        # Filter Load Cases from UI
        active_names = [n for n, cb in self.load_cases_vars.items() if cb.isChecked()]
        all_lcs = [StructuralLoadCase(id=i+1, name=name) for i, name in enumerate(active_names)]
        
        return StructuralModel(nodes=nodes, members=members, sections=sections, supports=supports, materials=materials, load_cases=all_lcs)

    def run_saf_export(self):
        if not self.input_path: return
        out, _ = QFileDialog.getSaveFileName(self, "Save SAF", self.input_path.replace(".json", ".saf"), "SAF Files (*.saf)")
        if not out: return
        try:
            self.progress.setValue(30)
            print(f"Exporting SAF to {os.path.basename(out)}...")
            model = self.create_model_from_ui()
            if model and SAFExporter(model).export(out):
                self.progress.setValue(100)
                print("Export finished successfully.")
                QMessageBox.information(self, "Success", "Export complete.")
        except Exception as e: print(f"ERROR: {e}")
        finally: self.progress.setValue(0)

    def run_grpc_sync(self):
        if not self.input_path: return
        try:
            print("Starting gRPC Live Sync...")
            model = self.create_model_from_ui()
            if not model: return
            
            importer = DlubalImporter(api_key=self.api_input.text(), material_preset=self.mat_combo.currentText())
            if importer.run(model):
                print("gRPC Push successful.")
                QMessageBox.information(self, "Success", "Live Sync finished.")
        except Exception as e: print(f"ERROR: {e}")

    def load_prefs(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.api_input.setText(json.load(f).get("api_key", ""))
            except: pass

    def save_prefs(self):
        with open(CONFIG_FILE, "w") as f: json.dump({"api_key": self.api_input.text()}, f)
        QMessageBox.information(self, "Success", "Saved.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = DlubalExportGUI()
    w.show()
    sys.exit(app.exec())
