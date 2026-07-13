"""
FTTH Auto BOM Generator - Main QGIS Plugin
Fully automated BOM from QGIS layers.
Author: Mustafa M M Elaham
"""
import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QCheckBox, QPushButton, QFileDialog, QComboBox,
    QMessageBox, QTextEdit, QGroupBox, QGridLayout, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject


class AutoBOMDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FTTH Auto BOM Generator v2.0")
        self.setMinimumSize(750, 850)
        self.setup_ui()
        self.auto_detect_layers()

    def setup_ui(self):
        layout = QVBoxLayout()

        # === TITLE ===
        title = QLabel("FTTH Auto BOM Generator")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F4E78;")
        layout.addWidget(title)

        subtitle = QLabel("Fully automated - reads cable, pole, hub, block & MDU layers")
        subtitle.setStyleSheet("font-size: 11px; color: #666666;")
        layout.addWidget(subtitle)

        # === LAYER SELECTION ===
        grp_layers = QGroupBox("1. Select Layers (auto-detected)")
        g = QGridLayout()

        self.cmb_cable = QComboBox(); self.cmb_cable.addItem("-- Not found --")
        self.cmb_pole = QComboBox(); self.cmb_pole.addItem("-- Not found --")
        self.cmb_hub = QComboBox(); self.cmb_hub.addItem("-- Not found --")
        self.cmb_block = QComboBox(); self.cmb_block.addItem("-- Not found --")
        self.cmb_mdu = QComboBox(); self.cmb_mdu.addItem("-- Optional --")

        g.addWidget(QLabel("Cable Layer:"), 0, 0)
        g.addWidget(self.cmb_cable, 0, 1)
        g.addWidget(QLabel("Pole Layer:"), 1, 0)
        g.addWidget(self.cmb_pole, 1, 1)
        g.addWidget(QLabel("HUB/AG Layer:"), 2, 0)
        g.addWidget(self.cmb_hub, 2, 1)
        g.addWidget(QLabel("Block Layer:"), 3, 0)
        g.addWidget(self.cmb_block, 3, 1)
        g.addWidget(QLabel("MDU Layer (opt):"), 4, 0)
        g.addWidget(self.cmb_mdu, 4, 1)

        btn_refresh = QPushButton("Refresh Layers")
        btn_refresh.clicked.connect(self.auto_detect_layers)
        g.addWidget(btn_refresh, 5, 1)

        grp_layers.setLayout(g)
        layout.addWidget(grp_layers)

        # === PROJECT PARAMS ===
        grp_proj = QGroupBox("2. Project Parameters")
        g2 = QGridLayout()

        self.txt_project = QLineEdit("GMGZZ Zone")
        self.txt_zone = QLineEdit("GMGZZ")
        self.spn_manholes = QSpinBox(); self.spn_manholes.setRange(1, 99); self.spn_manholes.setValue(1)

        g2.addWidget(QLabel("Project Name:"), 0, 0); g2.addWidget(self.txt_project, 0, 1)
        g2.addWidget(QLabel("Zone Code:"), 1, 0); g2.addWidget(self.txt_zone, 1, 1)
        g2.addWidget(QLabel("Manholes:"), 2, 0); g2.addWidget(self.spn_manholes, 2, 1)

        grp_proj.setLayout(g2)
        layout.addWidget(grp_proj)

        # === TOPOLOGY OPTIONS ===
        grp_topo = QGroupBox("3. Topology Options")
        g3 = QGridLayout()

        self.chk_olt = QCheckBox("OLT Termination"); self.chk_olt.setChecked(True)
        self.chk_core = QCheckBox("Core Manhole"); self.chk_core.setChecked(True)
        self.chk_lmj_existing = QCheckBox("LMJ is EXISTING (not new)"); self.chk_lmj_existing.setChecked(False)
        self.chk_smart_lock = QCheckBox("Smart Lock Lids"); self.chk_smart_lock.setChecked(True)
        self.chk_spur = QCheckBox("Spur Route"); self.chk_spur.setChecked(False)

        self.cmb_core = QComboBox(); self.cmb_core.addItems(["144F", "288F"])
        self.cmb_core.setCurrentText("144F")

        g3.addWidget(self.chk_olt, 0, 0)
        g3.addWidget(self.chk_core, 0, 1)
        g3.addWidget(self.chk_lmj_existing, 1, 0)
        g3.addWidget(self.chk_smart_lock, 1, 1)
        g3.addWidget(QLabel("Core Cable:"), 2, 0)
        g3.addWidget(self.cmb_core, 2, 1)
        g3.addWidget(self.chk_spur, 3, 0)

        grp_topo.setLayout(g3)
        layout.addWidget(grp_topo)

        # === GENERATE BUTTON ===
        btn_gen = QPushButton("GENERATE BOM FROM LAYERS")
        btn_gen.setStyleSheet("background-color: #2E75B6; color: white; font-size: 14px; font-weight: bold; padding: 12px;")
        btn_gen.clicked.connect(self.generate_bom)
        layout.addWidget(btn_gen)

        # === PROGRESS ===
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # === LOG ===
        layout.addWidget(QLabel("Log:"))
        self.txt_log = QTextEdit()
        self.txt_log.setMaximumHeight(120)
        layout.addWidget(self.txt_log)

        # === RESULT TABLE ===
        layout.addWidget(QLabel("BOM Preview:"))
        self.tbl_bom = QTableWidget(0, 4)
        self.tbl_bom.setHorizontalHeaderLabels(["Item Code", "Description", "Qty", "Notes"])
        self.tbl_bom.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_bom.setMaximumHeight(200)
        layout.addWidget(self.tbl_bom)

        # === EXPORT BUTTON ===
        btn_export = QPushButton("Export to Excel")
        btn_export.setStyleSheet("background-color: #1F4E78; color: white; font-size: 12px; font-weight: bold; padding: 8px;")
        btn_export.clicked.connect(self.export_excel)
        layout.addWidget(btn_export)

        self.setLayout(layout)
        self.bom_items = []
        self.project_params = {}

    def log(self, msg):
        self.txt_log.append(msg)

    def auto_detect_layers(self):
        """Auto-populate layer combos from QGIS project"""
        from .layer_reader import LayerReader
        reader = LayerReader()

        combos = {
            self.cmb_cable: reader.find_layer("cable"),
            self.cmb_pole: reader.find_layer("pole"),
            self.cmb_hub: reader.find_layer("hub"),
            self.cmb_block: reader.find_layer("block"),
            self.cmb_mdu: reader.find_layer("mdu"),
        }

        for combo, layer in combos.items():
            combo.clear()
            if layer:
                combo.addItem(layer.name(), layer.id())
            else:
                combo.addItem("-- Not found --")
            # Add all other layers as options
            project = QgsProject.instance()
            for lid, lyr in project.mapLayers().items():
                if lyr and combo.findText(lyr.name()) == -1:
                    combo.addItem(lyr.name(), lid)

    def get_selected_layer(self, combo):
        """Get the selected QGIS layer from combo"""
        idx = combo.currentIndex()
        if idx < 0:
            return None
        lid = combo.itemData(idx)
        if lid:
            return QgsProject.instance().mapLayer(lid)
        return None

    def generate_bom(self):
        """Main generation pipeline"""
        self.log("=== Starting Auto BOM Generation ===")
        self.progress.setValue(10)

        try:
            from .layer_reader import LayerReader
            from .auto_calculator import calculate_auto_bom
            from .drop_cable_optimizer import drop_cables_from_layer, get_drop_bom_items

            # Setup reader with selected layers
            reader = LayerReader()
            reader.cable_layer = self.get_selected_layer(self.cmb_cable)
            reader.pole_layer = self.get_selected_layer(self.cmb_pole)
            reader.hub_layer = self.get_selected_layer(self.cmb_hub)
            reader.block_layer = self.get_selected_layer(self.cmb_block)
            reader.mdu_layer = self.get_selected_layer(self.cmb_mdu)

            self.log("Reading layers...")
            self.progress.setValue(20)

            # Analyze cables
            cables = reader.analyze_cables()
            self.log(f"Found {len(cables)} cables")
            for c in cables:
                self.log(f"  {c['name']}: {c['type']} {c['fibers']}F, "
                        f"{c['length_m']}m, {c['poles_count']} poles, "
                        f"{c['direction_changes']} direction changes")

            self.progress.setValue(40)

            # Count everything
            num_hubs = reader.count_hubs()
            num_blocks = reader.count_blocks()
            num_mdus = reader.count_mdus()
            poles = reader.count_poles_by_type()
            total_dir_changes = sum(c["direction_changes"] for c in cables)

            self.log(f"Hubs: {num_hubs} | Standalone Blocks: {num_blocks} | MDUs: {num_mdus}")
            self.log(f"Poles: {poles['total']} (6M:{poles['6m']}, 7M:{poles['7m']}, 9M:{poles['9m']})")
            self.log(f"Direction Changes (>30 deg): {total_dir_changes}")

            self.progress.setValue(60)

            # Drop cables
            drop_counts = drop_cables_from_layer(reader.block_layer)
            if drop_counts:
                self.log(f"Drop cables optimized: {drop_counts}")

            self.progress.setValue(70)

            # Build layer data
            layer_data = {
                "cables": cables,
                "hubs": num_hubs,
                "blocks": num_blocks,
                "mdus": num_mdus,
                "poles": poles,
                "dir_changes": total_dir_changes,
            }

            # Build params
            self.project_params = {
                "project_name": self.txt_project.text(),
                "zone_code": self.txt_zone.text(),
                "is_olt_termination": self.chk_olt.isChecked(),
                "is_core_mh": self.chk_core.isChecked(),
                "is_lmj_existing": self.chk_lmj_existing.isChecked(),
                "core_cable_fibers": int(self.cmb_core.currentText().replace("F", "")),
                "num_manholes": self.spn_manholes.value(),
                "need_smart_lock": self.chk_smart_lock.isChecked(),
                "is_spur": self.chk_spur.isChecked(),
            }

            # Calculate BOM
            self.bom_items = calculate_auto_bom(layer_data, self.project_params)

            # Add drop cables
            drop_items = get_drop_bom_items(drop_counts)
            for code, qty, desc in drop_items:
                self.bom_items.append((code, qty, desc))

            self.progress.setValue(90)

            # Show in table
            self.tbl_bom.setRowCount(len(self.bom_items))
            for i, (code, qty, note) in enumerate(self.bom_items):
                from .auto_calculator import ITEMS
                desc = ITEMS.get(code, {}).get("desc", note)
                self.tbl_bom.setItem(i, 0, QTableWidgetItem(code))
                self.tbl_bom.setItem(i, 1, QTableWidgetItem(desc))
                self.tbl_bom.setItem(i, 2, QTableWidgetItem(str(qty)))
                self.tbl_bom.setItem(i, 3, QTableWidgetItem(note))

            self.progress.setValue(100)
            self.log(f"=== COMPLETE: {len(self.bom_items)} BOM items generated ===")

            QMessageBox.information(self, "Success",
                f"BOM Generated!\n"
                f"Cables: {len(cables)}\n"
                f"Hubs: {num_hubs}\n"
                f"Blocks: {num_blocks}\n"
                f"MDUs: {num_mdus}\n"
                f"Poles: {poles['total']}\n"
                f"Direction Changes: {total_dir_changes}\n"
                f"Total BOM Items: {len(self.bom_items)}")

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Generation failed: {str(e)}")
            self.progress.setValue(0)

    def export_excel(self):
        """Export current BOM to Excel"""
        if not self.bom_items:
            QMessageBox.warning(self, "Warning", "Generate BOM first!")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save BOM",
            f"{self.project_params.get('project_name', 'BOM')}_Auto.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not output_path:
            return

        try:
            from .excel_export import export_bom_to_excel
            success, msg = export_bom_to_excel(self.bom_items, self.project_params, output_path)
            if success:
                self.log(f"Exported: {msg}")
                QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.critical(self, "Error", msg)
        except Exception as e:
            self.log(f"Export error: {str(e)}")
            QMessageBox.critical(self, "Error", str(e))


class AutoBOMPlugin:
    """QGIS Plugin Entry Point"""

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        self.action = QAction("FTTH Auto BOM Generator", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToVectorMenu("FTTH Auto BOM", self.action)
        self.iface.addVectorToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginVectorMenu("FTTH Auto BOM", self.action)
        self.iface.removeVectorToolBarIcon(self.action)
        del self.action

    def run(self):
        if self.dialog is None:
            self.dialog = AutoBOMDialog()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
