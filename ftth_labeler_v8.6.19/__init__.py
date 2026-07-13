# -*- coding: utf-8 -*-
"""
FTTH Network Labeler V1.0 — QGIS Plugin
Copyright (c) Mustafa M M Ellaham. All rights reserved.

Proprietary and confidential. Unauthorized copying, distribution,
modification, reverse engineering, or use of this plugin, in whole
or in part, is strictly prohibited without express written permission
from Mustafa M M Ellaham.

Developed by: Mustafa M M Ellaham
"""


def classFactory(iface):
    """Plugin entry point with license check."""
    from qgis.PyQt.QtWidgets import QMessageBox
    from .license_checker import check_license
    from .config import WARNING_DAYS

    # --- License check ---
    valid, msg, days_left = check_license()

    if not valid:
        # License expired or tampered — show error and return dummy
        QMessageBox.critical(None, "FTTH Labeler — License", msg)
        return _ExpiredPlugin(iface)

    # License valid — show warning if near expiry
    if days_left is not None and days_left <= WARNING_DAYS:
        if days_left <= 0:
            QMessageBox.critical(None, "FTTH Labeler — License Expired", msg)
            return _ExpiredPlugin(iface)
        elif days_left <= 7:
            QMessageBox.warning(None, "FTTH Labeler — License Expiring Soon",
                f"Your license expires in {days_left} day(s).\n\n{msg}")
        else:
            QMessageBox.information(None, "FTTH Labeler — License",
                f"Your license expires in {days_left} day(s).\n\n{msg}")

    # Load the real plugin
    from .ftth_labeler_v2 import FTTHLabelerV2Plugin
    return FTTHLabelerV2Plugin(iface)


class _ExpiredPlugin:
    """Dummy plugin — loads nothing when license is expired."""

    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        """No UI elements added."""
        pass

    def unload(self):
        """Nothing to unload."""
        pass
