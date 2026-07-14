# -*- coding: utf-8 -*-
"""
Routed Drop Lines Generator — QGIS Plugin
Wraps the Processing Provider so QGIS can load it properly.
"""

from qgis.core import QgsApplication
from .routed_drops_provider import RoutedDropsProvider


class RoutedDropsPlugin:
    """Main plugin class that QGIS loads."""
    
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
    
    def initGui(self):
        """Called when QGIS loads the plugin."""
        self.provider = RoutedDropsProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)
    
    def unload(self):
        """Called when QGIS unloads the plugin."""
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
