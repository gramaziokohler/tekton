import sys
import os
import json
import threading
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QPushButton, QLabel, 
                             QComboBox, QCheckBox, QScrollArea, QFrame, 
                             QFileDialog, QMessageBox, QProgressBar, QLineEdit,
                             QGroupBox)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QPalette, QColor

# Core logic imports (wrapped in case of path issues)
try:
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from ct_dlubal.core.model import StructuralModel
    from ct_dlubal.exporter.formats.saf import SAFExporter

CONFIG_FILE = os.path.expanduser("~/.ct_dlubal_prefs.json")

class DropZone(QFrame):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setLineWidth(2)
        self.setMinimumHeight(80)
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
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files and files[0].lower().endswith(".json"):
            self.fileDropped.emit(files[0])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(self, "Open Model JSON", "", "JSON Files (*.json)")
            if path:
                self.fileDropped.emit(path)

class DlubalExportGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CT Dlubal")
        self.setMinimumSize(540, 520)
        self.resize(540, 520)

        # Style sheet for a modern "Qt Designer/Edge" look
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
            QTabBar::tab:selected {
                background: white;
                border-bottom-color: white;
                font-weight: bold;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #e9ecef;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QPushButton {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover { background-color: #e9ecef; }
            QPushButton#accentBtn {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                border: none;
            }
            QPushButton#accentBtn:hover { background-color: #005a9e; }
        """)

        # Data variables
        self.input_path = ""
        self.output_path = ""
        self.model_data = None
        self.load_cases_vars = {}
        self.api_key = ""

        self.setup_ui()
        self.load_prefs()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 5, 10, 10)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- Tab 1: Setup ---
        setup_tab = QWidget()
        setup_layout = QVBoxLayout(setup_tab)
        
        # 1. Dropzone
        self.drop_zone = DropZone()
        self.drop_zone.fileDropped.connect(self.handle_file_loaded)
        setup_layout.addWidget(self.drop_zone)

        # 2. File Path Display
        self.path_label = QLabel("No file selected.")
        self.path_label.setStyleSheet("color: #adb5bd; font-size: 10px;")
        self.path_label.setWordWrap(True)
        setup_layout.addWidget(self.path_label)

        # 3. Materials
        mat_group = QGroupBox("Materials")
        mat_layout = QVBoxLayout(mat_group)
        self.mat_combo = QComboBox()
        self.mat_combo.addItems(["C16", "C24", "C30", "GL24h", "GL28h", "GL32h"])
        self.mat_combo.setCurrentText("C24")
        mat_layout.addWidget(self.mat_combo)
        setup_layout.addWidget(mat_group)

        # 4. Supports
        supp_group = QGroupBox("Supports")
        supp_layout = QHBoxLayout(supp_group)
        self.supp_checks = {}
        for label in ["uX", "uY", "uZ", "rX", "rY", "rZ"]:
            cb = QCheckBox(label)
            if label.startswith("u"): cb.setChecked(True)
            self.supp_checks[label] = cb
            supp_layout.addWidget(cb)
        setup_layout.addWidget(supp_group)

        # 5. Load Cases
        lc_group = QGroupBox("Select Load Cases for Export")
        lc_layout = QVBoxLayout(lc_group)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedHeight(120)
        self.scroll.setStyleSheet("background: white; border: none;")
        self.lc_container = QWidget()
        self.lc_inner_layout = QVBoxLayout(self.lc_container)
        self.lc_inner_layout.setContentsMargins(5, 5, 5, 5)
        self.lc_inner_layout.setSpacing(2)
        
        # User selectable load cases instead of model parsing
        self.load_cases_vars = {}
        standard_cases = [
            "1: Self Weight",
            "2: Permanent",
            "3: Live Load",
            "4: Snow",
            "5: Wind +X",
            "6: Wind -X",
            "7: Wind +Y",
            "8: Wind -Y"
        ]
        
        for name in standard_cases:
            cb = QCheckBox(name)
            self.lc_inner_layout.addWidget(cb)
            self.load_cases_vars[name] = cb
            
        self.lc_inner_layout.addStretch()
        self.scroll.setWidget(self.lc_container)
        lc_layout.addWidget(self.scroll)
        setup_layout.addWidget(lc_group)

        self.tabs.addTab(setup_tab, "1. Setup")

        # --- Tab 2: Workflow ---
        workflow_tab = QWidget()
        workflow_layout = QVBoxLayout(workflow_tab)
        
        saf_group = QGroupBox("Fast SAF Export")
        saf_l = QVBoxLayout(saf_group)
        saf_btn = QPushButton("GENERATE SAF EXCEL FILE")
        saf_btn.setObjectName("accentBtn")
        saf_btn.setFixedHeight(40)
        saf_btn.clicked.connect(self.run_saf_export)
        saf_l.addWidget(saf_btn)
        workflow_layout.addWidget(saf_group)

        grpc_group = QGroupBox("Dlubal Live Sync")
        grpc_l = QVBoxLayout(grpc_group)
        grpc_btn = QPushButton("PUSH TO RFEM/RSTAB")
        grpc_btn.setFixedHeight(40)
        grpc_btn.clicked.connect(lambda: self.status_label.setText("gRPC Sync starting..."))
        grpc_l.addWidget(grpc_btn)
        workflow_layout.addWidget(grpc_group)
        
        workflow_layout.addStretch()
        self.tabs.addTab(workflow_tab, "2. Workflow")

        # --- Tab 3: Config ---
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        api_group = QGroupBox("API Settings")
        api_l = QVBoxLayout(api_group)
        api_l.addWidget(QLabel("Dlubal Machine Key:"))
        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.Password)
        api_l.addWidget(self.api_input)
        config_layout.addWidget(api_group)
        
        save_btn = QPushButton("Save Preferences")
        save_btn.clicked.connect(self.save_prefs)
        config_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        config_layout.addStretch()
        self.tabs.addTab(config_tab, "3. Config")

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
        
        ver_label = QLabel("ct_dlubal v1.1 (Qt)")
        ver_label.setStyleSheet("color: #adb5bd; font-size: 10px;")
        status_row.addWidget(ver_label, alignment=Qt.AlignRight)
        footer.addLayout(status_row)
        
        main_layout.addLayout(footer)

    def load_prefs(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    prefs = json.load(f)
                    self.api_input.setText(prefs.get("api_key", ""))
            except: pass

    def save_prefs(self):
        prefs = {"api_key": self.api_input.text()}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(prefs, f)
        QMessageBox.information(self, "Success", "Preferences saved.")

    def handle_file_loaded(self, path):
        self.input_path = path
        self.path_label.setText(path)
        
        # Update DropZone to show current filename
        filename = os.path.basename(path)
        self.drop_zone.set_content(f"CURRENT MODEL: {filename}\n(Click to change)", is_file=True)
        
        self.status_label.setText("Model loaded successfully.")
        try:
            with open(path, 'r') as f:
                self.model_data = json.load(f)
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")

    def run_saf_export(self):
        if not self.input_path:
            QMessageBox.warning(self, "No file", "Please load a model first.")
            return
            
        out_path, _ = QFileDialog.getSaveFileName(self, "Save SAF File", self.input_path.replace(".json", ".saf"), "SAF Files (*.saf)")
        if not out_path: return

        self.progress.setValue(20)
        self.status_label.setText("Exporting...")
        
        try:
            model = StructuralModel.from_json(self.model_data)
            
            # Apply UI settings
            for sid in model.materials: 
                model.materials[sid] = self.mat_combo.currentText()
            
            active_lcs = [n for n, cb in self.load_cases_vars.items() if cb.isChecked()]
            model.load_cases = [lc for lc in model.load_cases if lc.name in active_lcs]
            
            inf = float('inf')
            for s in model.supports:
                s.ux = inf if self.supp_checks["uX"].isChecked() else 0.0
                s.uy = inf if self.supp_checks["uY"].isChecked() else 0.0
                s.uz = inf if self.supp_checks["uZ"].isChecked() else 0.0
                s.rx = inf if self.supp_checks["rX"].isChecked() else 0.0
                s.ry = inf if self.supp_checks["rY"].isChecked() else 0.0
                s.rz = inf if self.supp_checks["rZ"].isChecked() else 0.0
            
            self.progress.setValue(60)
            if SAFExporter(model).export(out_path):
                self.progress.setValue(100)
                QMessageBox.information(self, "Success", f"SAF Export successful!\nFile: {os.path.basename(out_path)}")
                self.status_label.setText("Export complete.")
            else:
                raise Exception("Exporter returned False.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Export failed.")
        finally:
            self.progress.setValue(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DlubalExportGUI()
    window.show()
    sys.exit(app.exec())
