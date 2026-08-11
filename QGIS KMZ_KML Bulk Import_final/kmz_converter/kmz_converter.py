# -*- coding: utf-8 -*-
"""
KMZ/KML Bulk Converter Plugin for QGIS
Imports all KML/KMZ folders as separate layers and exports to GPKG or SHP
"""

from qgis.PyQt.QtCore import Qt, QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsApplication
import os

from .kmz_converter_dialog import KMZConverterDialog


class KMZConverterPlugin:
    """Main plugin class."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dlg = None
        self.action = None

    def initGui(self):
        """Create the menu entry and toolbar icon."""
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        
        # Create action
        self.action = QAction(
            QIcon(icon_path) if os.path.exists(icon_path) else QIcon(),
            "KMZ/KML Bulk Converter",
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        
        # Add to Vector menu
        self.iface.addPluginToVectorMenu("KMZ/KML Bulk Converter", self.action)
        
        # Add to toolbar
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Remove the plugin from QGIS."""
        self.iface.removePluginVectorMenu("KMZ/KML Bulk Converter", self.action)
        self.iface.removeToolBarIcon(self.action)
        del self.action

    def run(self):
        """Run the plugin dialog."""
        if self.dlg is None:
            self.dlg = KMZConverterDialog()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
