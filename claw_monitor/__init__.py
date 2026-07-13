# Claw Monitor Plugin for QGIS
# Author: Mustafa M M Elaham

def classFactory(iface):
    from .claw_monitor import ClawMonitorPlugin
    return ClawMonitorPlugin(iface)
