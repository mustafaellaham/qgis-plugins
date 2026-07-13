# -*- coding: utf-8 -*-
"""
KMZ/KML Bulk Converter Dialog
"""

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QFileDialog, QMessageBox, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QGroupBox,
    QProgressBar, QWidget, QCheckBox
)
from qgis.core import (
    QgsVectorLayer, QgsDataProvider, QgsVectorFileWriter,
    QgsCoordinateTransformContext, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsProject
)
from qgis.gui import QgsProjectionSelectionWidget
import os
import gc


class ConverterWorker(QThread):
    """Background worker thread to run the conversion without freezing QGIS."""
    
    progress = pyqtSignal(str)
    finished_sig = pyqtSignal(bool, str)
    layer_saved = pyqtSignal(str, int)

    def __init__(self, input_path, output_format, output_folder, target_crs=None):
        super().__init__()
        self.input_path = input_path
        self.output_format = output_format
        self.output_folder = output_folder
        self.target_crs = target_crs  # QgsCoordinateReferenceSystem or None
        self._is_running = True

    def run(self):
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            
            # Derive output filename from input filename (same name, different extension)
            input_basename = os.path.splitext(os.path.basename(self.input_path))[0]
            output_gpkg = os.path.join(self.output_folder, f"{input_basename}.gpkg")
            
            first = True
            saved_count = 0
            total = 0
            
            # CRS info for logging
            crs_info = ""
            if self.target_crs and self.target_crs.isValid():
                crs_info = f" (CRS: {self.target_crs.authid()} - {self.target_crs.description()})"

            self.progress.emit("Opening KML/KMZ file...")
            probe = QgsVectorLayer(self.input_path, "probe", "ogr")
            
            if not probe.isValid():
                self.finished_sig.emit(False, "Failed to open the KML/KMZ file. Check the path.")
                return

            sub_layers = probe.dataProvider().subLayers()
            if not sub_layers:
                self.finished_sig.emit(False, "No layers found in the file.")
                return

            total = len(sub_layers)
            self.progress.emit(f"Found {total} folder(s). Starting export to {self.output_format}{crs_info}...\n")

            for sub in sub_layers:
                if not self._is_running:
                    self.finished_sig.emit(False, "Conversion cancelled by user.")
                    return

                parts = sub.split(QgsDataProvider.SUBLAYER_SEPARATOR)
                name = parts[1] if len(parts) >= 2 else sub
                
                if not name or not name.strip():
                    continue

                # Sanitize name for filesystem
                safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in name).strip()
                if not safe_name:
                    safe_name = "unnamed_layer"

                self.progress.emit(f"Processing: '{name}' ...")

                uri = f"{self.input_path}|layername={name}"
                vlayer = QgsVectorLayer(uri, name, "ogr")
                
                if not vlayer.isValid() or vlayer.featureCount() == 0:
                    self.progress.emit(f"  Skipped: '{name}' (empty or invalid)")
                    continue

                # === CRS FIX: Explicitly set source CRS for KML (always EPSG:4326) ===
                # KML spec uses WGS 84, but OGR doesn't always set it on the layer
                source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                vlayer.setCrs(source_crs)

                options = QgsVectorFileWriter.SaveVectorOptions()
                options.fileEncoding = "UTF-8"

                # Apply target CRS if selected
                if self.target_crs and self.target_crs.isValid():
                    options.destCRS = self.target_crs
                    options.ct = QgsCoordinateTransform(source_crs, self.target_crs, QgsProject.instance())

                if self.output_format == "GPKG":
                    options.driverName = "GPKG"
                    options.layerName = safe_name
                    options.actionOnExistingFile = (
                        QgsVectorFileWriter.CreateOrOverwriteFile if first 
                        else QgsVectorFileWriter.CreateOrOverwriteLayer
                    )
                    out_file = output_gpkg
                    first = False
                else:  # SHP
                    options.driverName = "ESRI Shapefile"
                    safe_shp = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
                    out_file = os.path.join(self.output_folder, f"{safe_shp}.shp")
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

                err, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                    vlayer, out_file, QgsProject.instance().transformContext(), options
                )

                if err == QgsVectorFileWriter.NoError:
                    feat_count = vlayer.featureCount()
                    self.layer_saved.emit(name, feat_count)
                    self.progress.emit(f"  Saved: '{name}' ({feat_count} features)")
                    saved_count += 1
                else:
                    self.progress.emit(f"  FAILED: '{name}' — {msg}")

            # Build summary
            if self.output_format == "GPKG":
                summary = f"\n{'='*50}\nDone! Saved {saved_count}/{total} layers to:\n{output_gpkg}\n{'='*50}"
            else:
                summary = f"\n{'='*50}\nDone! Saved {saved_count}/{total} layers to:\n{self.output_folder}\n{'='*50}"
            
            self.progress.emit(summary)
            self.finished_sig.emit(True, f"Successfully exported {saved_count} layer(s).")

        except Exception as e:
            self.finished_sig.emit(False, f"Error: {str(e)}")

    def stop(self):
        self._is_running = False


class KMZConverterDialog(QDialog):
    """Main plugin dialog with file pickers and run button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KMZ/KML Bulk Converter")
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)
        
        self.worker = None
        self._output_folder_path = None  # Stores path for "Open Output Folder" button
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # --- Header ---
        header = QLabel("<b>KMZ/KML Bulk Converter</b>")
        header.setStyleSheet("font-size: 14px;")
        layout.addWidget(header)
        
        desc = QLabel("Import all KML/KMZ folders as separate layers and export to GPKG or SHP.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)
        layout.addSpacing(8)

        # --- Input File Group ---
        input_group = QGroupBox("Input File (KML or KMZ)")
        input_layout = QHBoxLayout()
        
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Select your KML or KMZ file...")
        
        self.input_btn = QPushButton("Browse...")
        self.input_btn.setToolTip("Select KML or KMZ file")
        self.input_btn.clicked.connect(self._browse_input)
        
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.input_btn)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # --- Output Format Group ---
        format_group = QGroupBox("Output Format")
        format_layout = QHBoxLayout()
        
        self.format_combo = QComboBox()
        self.format_combo.addItem("GeoPackage (.gpkg) — Single file, all layers", "GPKG")
        self.format_combo.addItem("Shapefile (.shp) — One file per layer", "SHP")
        self.format_combo.setToolTip(
            "GPKG: All layers in one file (recommended)\n"
            "SHP: One .shp file per folder"
        )
        
        format_layout.addWidget(QLabel("Format:"))
        format_layout.addWidget(self.format_combo, 1)
        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # --- CRS Group ---
        crs_group = QGroupBox("Output Coordinate Reference System (CRS)")
        crs_layout = QVBoxLayout()
        
        # Checkbox to enable/disable CRS reprojection
        crs_hbox = QHBoxLayout()
        self.crs_checkbox = QCheckBox("Reproject to different CRS")
        self.crs_checkbox.setToolTip(
            "Check this to reproject output to a different CRS.\n"
            "Leave unchecked to keep original WGS 84 (EPSG:4326)."
        )
        self.crs_checkbox.stateChanged.connect(self._on_crs_toggled)
        crs_hbox.addWidget(self.crs_checkbox)
        crs_hbox.addStretch()
        crs_layout.addLayout(crs_hbox)
        
        # CRS selector widget
        crs_select_hbox = QHBoxLayout()
        self.crs_widget = QgsProjectionSelectionWidget()
        self.crs_widget.setToolTip("Click to select output CRS")
        self.crs_widget.setEnabled(False)  # Disabled until checkbox is checked
        # Set default to project CRS if available, otherwise EPSG:4326
        project_crs = QgsProject.instance().crs()
        if project_crs.isValid() and project_crs.authid() != "":
            self.crs_widget.setCrs(project_crs)
        else:
            self.crs_widget.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        
        crs_select_hbox.addWidget(QLabel("Target CRS:"))
        crs_select_hbox.addWidget(self.crs_widget, 1)
        crs_layout.addLayout(crs_select_hbox)
        
        crs_group.setLayout(crs_layout)
        layout.addWidget(crs_group)

        # --- Output Folder Group ---
        output_group = QGroupBox("Output Folder")
        output_layout = QHBoxLayout()
        
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Select destination folder...")
        
        self.output_btn = QPushButton("Browse...")
        self.output_btn.setToolTip("Select output folder")
        self.output_btn.clicked.connect(self._browse_output)
        
        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(self.output_btn)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # --- Run Button ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.run_btn = QPushButton("Convert")
        self.run_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-weight: bold; padding: 8px 24px; font-size: 12px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self.run_btn.clicked.connect(self._run_conversion)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_conversion)
        
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.cancel_btn)
        
        # Open Output Folder button (hidden until conversion completes)
        self.open_folder_btn = QPushButton("Open Output Folder")
        self.open_folder_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "font-weight: bold; padding: 8px 24px; font-size: 12px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        btn_layout.addWidget(self.open_folder_btn)
        
        layout.addLayout(btn_layout)

        # --- Progress / Log ---
        log_group = QGroupBox("Progress")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("Progress will appear here...")
        self.log_area.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: Consolas, Monaco, monospace; font-size: 11px; }"
        )
        
        log_layout.addWidget(self.log_area)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, 1)
        
        # --- Status Label ---
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_label)

        # --- Copyright / Author Footer ---
        footer = QLabel("\u00a9 2025 MUstafa M M Ellaham. All rights reserved.")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999; font-size: 10px; padding-top: 4px;")
        layout.addWidget(footer)

        self.setLayout(layout)

    def _on_crs_toggled(self, state):
        """Enable/disable CRS widget based on checkbox state."""
        self.crs_widget.setEnabled(state == Qt.Checked)

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select KML/KMZ File", "",
            "KML/KMZ Files (*.kml *.kmz);;KML Files (*.kml);;KMZ Files (*.kmz)"
        )
        if path:
            self.input_edit.setText(path)
            # Auto-suggest output folder based on input location
            if not self.output_edit.text():
                parent_dir = os.path.dirname(path)
                suggested = os.path.join(parent_dir, "output")
                self.output_edit.setText(suggested)

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self.output_edit.setText(path)

    def _run_conversion(self):
        input_path = self.input_edit.text().strip()
        output_folder = self.output_edit.text().strip()
        output_format = self.format_combo.currentData()

        # Validate
        if not input_path:
            QMessageBox.warning(self, "Missing Input", "Please select a KML or KMZ file.")
            return
        if not os.path.exists(input_path):
            QMessageBox.warning(self, "File Not Found", f"File not found:\n{input_path}")
            return
        if not output_folder:
            QMessageBox.warning(self, "Missing Output", "Please select an output folder.")
            return

        # Get target CRS if enabled
        target_crs = None
        if self.crs_checkbox.isChecked():
            target_crs = self.crs_widget.crs()
            if not target_crs.isValid():
                QMessageBox.warning(self, "Invalid CRS", "Please select a valid target CRS.")
                return

        # Store output folder path for "Open Output Folder" button
        self._output_folder_path = output_folder
        self.open_folder_btn.setVisible(False)

        # Clear log
        self.log_area.clear()
        self.status_label.setText("Converting...")
        self.status_label.setStyleSheet("color: #2196F3; font-style: italic;")
        
        # Disable controls during conversion
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.input_btn.setEnabled(False)
        self.output_btn.setEnabled(False)
        self.input_edit.setEnabled(False)
        self.output_edit.setEnabled(False)
        self.format_combo.setEnabled(False)
        self.crs_checkbox.setEnabled(False)
        self.crs_widget.setEnabled(False)

        # Start worker thread
        self.worker = ConverterWorker(input_path, output_format, output_folder, target_crs)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_sig.connect(self._on_finished)
        self.worker.start()

    def _cancel_conversion(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.status_label.setText("Cancelling...")

    def _on_progress(self, message):
        self.log_area.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_finished(self, success, message):
        # Re-enable controls
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.input_btn.setEnabled(True)
        self.output_btn.setEnabled(True)
        self.input_edit.setEnabled(True)
        self.output_edit.setEnabled(True)
        self.format_combo.setEnabled(True)
        self.crs_checkbox.setEnabled(True)
        self.crs_widget.setEnabled(self.crs_checkbox.isChecked())

        if success:
            self.status_label.setText("Completed successfully!")
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.open_folder_btn.setVisible(True)  # Show "Open Output Folder" button
            QMessageBox.information(self, "Success", message)
        else:
            self.status_label.setText(f"Failed: {message}")
            self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
            self.open_folder_btn.setVisible(False)
            QMessageBox.critical(self, "Error", message)

    def _open_output_folder(self):
        """Open the output folder in the system's file manager."""
        if self._output_folder_path and os.path.exists(self._output_folder_path):
            folder_url = QUrl.fromLocalFile(self._output_folder_path)
            QDesktopServices.openUrl(folder_url)
        else:
            QMessageBox.warning(self, "Folder Not Found", "The output folder no longer exists.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        event.accept()
