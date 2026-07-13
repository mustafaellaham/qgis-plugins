# -*- coding: utf-8 -*-
"""
Precon Cable Optimizer - Main Plugin File

Author: Mustafa M M Elaham
Copyright (c) 2026 Mustafa M M Elaham. All rights reserved.

Reads route lengths from a 'length' column in the active QGIS vector layer,
then calculates the optimal precon cable length by trying different slack
values (10, 9, 8, 7 meters) to minimize waste.

Fixed precon cable lengths: 50, 80, 100, 120, 150, 180, 200, 250, 300, 350
"""

from qgis.PyQt.QtCore import Qt, QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from qgis.core import (
    QgsVectorLayer,
    QgsField,
    Qgis
)
from qgis.utils import iface

import os

# ============================================================================
# FIXED CONSTANTS
# ============================================================================

# Available precon cable lengths in ascending order (meters)
PRECON_CABLES = [50, 80, 100, 120, 150, 180, 200, 250, 300, 350]

# Slack values to try, in order (meters)
SLACK_VALUES = [10, 9, 8, 7]

# Source field name for route length
LENGTH_FIELD = "length"

# Output field names
FIELD_PRECON_CABLE = "precon_cable"
FIELD_SLACK_USED = "slack_used"
FIELD_WASTE_M = "waste_m"


# ============================================================================
# CORE OPTIMIZATION LOGIC
# ============================================================================

def find_best_cable(length_value):
    """Find the optimal precon cable and slack combination for a given route length.

    For each slack value in SLACK_VALUES, calculates:
        total_needed = length_value + slack
        precon_cable = smallest cable >= total_needed (round UP)
        waste = precon_cable - total_needed

    Returns the (slack, precon_cable, waste) combination with MINIMUM waste.

    If the route length exceeds all available cable sizes (even with slack),
    returns (None, None, None).

    :param length_value: The route length in meters (numeric).
    :type length_value: float or int

    :return: Tuple of (best_slack, best_cable, best_waste) or (None, None, None).
    :rtype: tuple
    """
    best_slack = None
    best_cable = None
    best_waste = None

    for slack in SLACK_VALUES:
        total_needed = length_value + slack

        # Find the smallest precon cable >= total_needed (round UP)
        chosen_cable = None
        for cable in PRECON_CABLES:
            if cable >= total_needed:
                chosen_cable = cable
                break

        # If no cable can accommodate this total, skip this slack
        if chosen_cable is None:
            continue

        waste = chosen_cable - total_needed

        # Keep track of the combination with minimum waste
        if best_waste is None or waste < best_waste:
            best_waste = waste
            best_slack = slack
            best_cable = chosen_cable

    return best_slack, best_cable, best_waste


# ============================================================================
# MAIN PLUGIN CLASS
# ============================================================================

class PreconCableOptimizer:
    """QGIS Plugin for optimizing precon cable selection in FTTH planning.

    Reads route lengths from a 'length' column in the active vector layer,
    calculates the optimal precon cable length by trying slack values 10-7m,
    and writes results to three new columns: precon_cable, slack_used, waste_m.
    """

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
                      which provides the hook by which you can manipulate the
                      QGIS application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        # Actions and menu references
        self.action = None
        self.menu = None
        self.toolbar = None

        # Plugin name for display
        self.plugin_name = "Precon Cable Optimizer"

    # ------------------------------------------------------------------
    # TRANSLATION HELPER
    # ------------------------------------------------------------------

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        :param message: String for translation.
        :type message: str

        :returns: Translated version of message.
        :rtype: str
        """
        return QCoreApplication.translate("PreconCableOptimizer", message)

    # ------------------------------------------------------------------
    # ICON HELPER
    # ------------------------------------------------------------------

    def _get_icon(self):
        """Return the plugin icon, falling back to a default theme icon.

        :return: QIcon instance.
        :rtype: QIcon
        """
        icon_path = os.path.join(self.plugin_dir, "icon.svg")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    # ------------------------------------------------------------------
    # QGIS PLUGIN LIFECYCLE
    # ------------------------------------------------------------------

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        # Create the action for the plugin
        self.action = QAction(
            self._get_icon(),
            self.tr("Optimize Precon Cables"),
            self.iface.mainWindow()
        )
        self.action.setWhatsThis(
            self.tr("Optimize precon cable selection for FTTH planning")
        )
        self.action.setStatusTip(
            self.tr("Calculate optimal precon cable lengths with minimum waste")
        )
        self.action.triggered.connect(self.run)

        # Add to Vector menu
        self.iface.addPluginToVectorMenu(
            self.tr("Precon Cable Optimizer"),
            self.action
        )

        # Add to toolbar
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        # Remove from Vector menu
        self.iface.removePluginVectorMenu(
            self.tr("Precon Cable Optimizer"),
            self.action
        )

        # Remove from toolbar
        self.iface.removeToolBarIcon(self.action)

        # Delete action
        del self.action

    # ------------------------------------------------------------------
    # FIELD HELPERS
    # ------------------------------------------------------------------

    def _field_exists(self, layer, field_name):
        """Check if a field exists in the layer (case-insensitive).

        :param layer: The vector layer to check.
        :type layer: QgsVectorLayer
        :param field_name: The field name to look for.
        :type field_name: str

        :return: True if the field exists, False otherwise.
        :rtype: bool
        """
        field_name_lower = field_name.lower()
        for field in layer.fields():
            if field.name().lower() == field_name_lower:
                return True
        return False

    def _get_field_index(self, layer, field_name):
        """Get the index of a field in the layer (case-insensitive).

        :param layer: The vector layer to check.
        :type layer: QgsVectorLayer
        :param field_name: The field name to look for.
        :type field_name: str

        :return: The field index, or -1 if not found.
        :rtype: int
        """
        field_name_lower = field_name.lower()
        for idx, field in enumerate(layer.fields()):
            if field.name().lower() == field_name_lower:
                return idx
        return -1

    def _ensure_output_fields(self, layer):
        """Create the three output fields if they do not already exist.

        Adds fields through the edit buffer (not provider) for reliability.
        Must be called AFTER startEditing().

        :param layer: The vector layer being edited.
        :type layer: QgsVectorLayer

        :return: Tuple of (precon_cable_idx, slack_used_idx, waste_m_idx).
        :rtype: tuple
        """
        fields_added = False

        if not self._field_exists(layer, FIELD_PRECON_CABLE):
            layer.addAttribute(QgsField(FIELD_PRECON_CABLE, QVariant.Int))
            fields_added = True

        if not self._field_exists(layer, FIELD_SLACK_USED):
            layer.addAttribute(QgsField(FIELD_SLACK_USED, QVariant.Int))
            fields_added = True

        if not self._field_exists(layer, FIELD_WASTE_M):
            layer.addAttribute(QgsField(FIELD_WASTE_M, QVariant.Int))
            fields_added = True

        if fields_added:
            layer.updateFields()

        precon_idx = self._get_field_index(layer, FIELD_PRECON_CABLE)
        slack_idx = self._get_field_index(layer, FIELD_SLACK_USED)
        waste_idx = self._get_field_index(layer, FIELD_WASTE_M)

        return precon_idx, slack_idx, waste_idx

    # ------------------------------------------------------------------
    # MAIN PROCESSING METHOD
    # ------------------------------------------------------------------

    def run(self):
        """Execute the precon cable optimization.

        This method:
        1. Gets the active vector layer
        2. Validates that a 'length' column exists
        3. Creates output columns (precon_cable, slack_used, waste_m)
        4. Runs optimization for each feature
        5. Reports results via the message bar
        """
        # ------------------------------------------------------------------
        # Step 1: Get active layer
        # ------------------------------------------------------------------
        layer = self.iface.activeLayer()

        if layer is None:
            self.iface.messageBar().pushMessage(
                self.tr("Precon Cable Optimizer"),
                self.tr("No active layer. Please select a vector layer."),
                level=Qgis.Warning,
                duration=5
            )
            return

        # ------------------------------------------------------------------
        # Step 2: Validate layer type
        # ------------------------------------------------------------------
        if not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushMessage(
                self.tr("Precon Cable Optimizer"),
                self.tr("The active layer is not a vector layer."),
                level=Qgis.Warning,
                duration=5
            )
            return

        # ------------------------------------------------------------------
        # Step 3: Check if 'length' field exists (case-insensitive)
        # ------------------------------------------------------------------
        length_field_idx = self._get_field_index(layer, LENGTH_FIELD)

        if length_field_idx == -1:
            self.iface.messageBar().pushMessage(
                self.tr("Precon Cable Optimizer"),
                self.tr(
                    "No '{0}' column found in layer '{1}'. "
                    "Please ensure your layer has a numeric '{0}' field."
                ).format(LENGTH_FIELD, layer.name()),
                level=Qgis.Warning,
                duration=5
            )
            return

        # ------------------------------------------------------------------
        # Step 4: Start editing FIRST (required before adding fields)
        # ------------------------------------------------------------------
        if not layer.startEditing():
            self.iface.messageBar().pushMessage(
                self.tr("Precon Cable Optimizer"),
                self.tr("Cannot edit layer '{0}'. Check: (1) Layer is not read-only, (2) You have write permission, (3) For file layers, the file is not locked.").format(layer.name()),
                level=Qgis.Critical,
                duration=8
            )
            return

        # ------------------------------------------------------------------
        # Step 5: Create output fields (inside edit session for reliability)
        # ------------------------------------------------------------------
        try:
            precon_idx, slack_idx, waste_idx = self._ensure_output_fields(layer)
        except Exception as e:
            layer.rollBack()
            self.iface.messageBar().pushMessage(
                self.tr("Precon Cable Optimizer"),
                self.tr("Failed to add output fields: {0}").format(str(e)),
                level=Qgis.Critical,
                duration=5
            )
            return

        # ------------------------------------------------------------------
        # Step 6: Show info message that processing is starting
        # ------------------------------------------------------------------
        feature_count = layer.featureCount()
        self.iface.messageBar().pushMessage(
            self.tr("Precon Cable Optimizer"),
            self.tr(
                "Processing {0} features in layer '{1}'..."
            ).format(feature_count, layer.name()),
            level=Qgis.Info,
            duration=3
        )

        # ------------------------------------------------------------------
        # Step 7: Process each feature
        # ------------------------------------------------------------------
        processed_count = 0
        skipped_count = 0
        too_long_count = 0
        total_waste = 0

        try:
            for feature in layer.getFeatures():
                fid = feature.id()

                # Read the length value
                length_value = feature.attribute(length_field_idx)

                # Handle null/None values
                if length_value is None or length_value == "":
                    skipped_count += 1
                    continue

                # Convert to numeric, skip non-numeric
                try:
                    length_value = float(length_value)
                except (ValueError, TypeError):
                    skipped_count += 1
                    continue

                # Run the optimization
                best_slack, best_cable, best_waste = find_best_cable(length_value)

                # If no cable can accommodate (route too long)
                if best_cable is None:
                    too_long_count += 1
                    layer.changeAttributeValue(fid, precon_idx, None)
                    layer.changeAttributeValue(fid, slack_idx, None)
                    layer.changeAttributeValue(fid, waste_idx, None)
                    continue

                # Write results to output fields
                layer.changeAttributeValue(fid, precon_idx, int(best_cable))
                layer.changeAttributeValue(fid, slack_idx, int(best_slack))
                layer.changeAttributeValue(fid, waste_idx, int(best_waste))

                processed_count += 1
                total_waste += best_waste

            # Commit changes
            if not layer.commitChanges():
                commit_err = layer.commitErrors()
                layer.rollBack()
                self.iface.messageBar().pushMessage(
                    self.tr("Precon Cable Optimizer"),
                    self.tr(
                        "Failed to commit changes. Error: {0}"
                    ).format(str(commit_err)),
                    level=Qgis.Critical,
                    duration=5
                )
                return

        except Exception as e:
            # Rollback on error
            layer.rollBack()
            self.iface.messageBar().pushMessage(
                self.tr("Precon Cable Optimizer"),
                self.tr("Error during processing: {0}").format(str(e)),
                level=Qgis.Critical,
                duration=5
            )
            return

        # ------------------------------------------------------------------
        # Step 8: Report results via message bar
        # ------------------------------------------------------------------
        messages = []
        messages.append(
            self.tr("Processed {0}/{1} features successfully.").format(processed_count, feature_count)
        )
        messages.append(
            self.tr("Total waste: {0}m.").format(int(round(total_waste)))
        )

        if skipped_count > 0:
            messages.append(
                self.tr("Skipped {0} non-numeric/empty rows.").format(skipped_count)
            )

        if too_long_count > 0:
            messages.append(
                self.tr("{0} routes exceed all cable sizes (even with 7m slack).").format(
                    too_long_count
                )
            )

        self.iface.messageBar().pushMessage(
            self.tr("Precon Cable Optimizer"),
            " ".join(messages),
            level=Qgis.Success,
            duration=8
        )
