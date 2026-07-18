# -*- coding: utf-8 -*-
"""
FTTH Auto Labeler v6.8.22 -- QGIS Processing Plugin
Copyright (c) Mustafa M M Ellaham. All rights reserved.

Proprietary and confidential. Unauthorized copying, distribution,
modification, reverse engineering, or use of this plugin, in whole
or in part, is strictly prohibited without express written permission
from Mustafa M M Ellaham.

By Mustafa M M Ellaham

STRICT INPUT (you must provide):
  - AG Polygons: ID column with AG numbers (1, 2, 3...)
  - Block Polygons: ID column with Block numbers (1, 2, 3...)
  - FJ Points: any table (geometry only matters)
  - DJ Points: any table (geometry only matters)
  - DC Lines: individual segments between 2 nodes, any direction

FLEXIBLE INPUT (plugin auto-generates columns):
  - All layers except AG/Block: plugin creates 'name' and all other needed columns
  - AG/Block: plugin auto-creates 'name' column if missing

PARAMETERS (you enter when running):
  - Area Code: any length (type YOUR actual area code)
  - Zone Code: e.g., Z01, Z02 (optional -- leave empty for no zone)
  - AG ID Field Name: defaults to 'ID'
  - Block ID Field Name: defaults to 'ID'

OUTPUT (plugin generates and writes to layers):
  - AG.name = AG01, AG02... (2 digits)
  - Block.name = B001, B002... (3 digits) + ag_parent
  - FJ.name = {AREA}_FJ01_{AG}...
  - DJ.name = {AREA}_DJ001_1:9 + splitter + position + dc_name
  - DC.name = {AREA}_{ZONE}_{AG}_DC{block:03d}.{seq}_1F_ADSS_G.657.A1 + from_node + to_node
  - Pole.name = {AREA}_P0001...
"""

import os
import re
import json
import csv
import datetime
import time

from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsApplication, QgsProcessing,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsWkbTypes,
    QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer,
    QgsProcessingParameterString, QgsProcessingParameterBoolean,
    QgsProcessingParameterNumber, QgsProcessingParameterFolderDestination,
    QgsProcessingOutputFolder,
    QgsProcessingProvider,
)
from qgis import processing

from .trace_engine import FTTHTraceEngine, DJPositionMapper


# =============================================================================
# Module-Level Utility Functions
# =============================================================================

def find_field(layer, field_names):
    """Find field index, case-insensitive. Returns -1 if not found."""
    all_names = [f.name() for f in layer.fields()]
    for fn in field_names:
        fn_lower = fn.lower()
        for actual_name in all_names:
            if actual_name.lower() == fn_lower:
                return layer.fields().indexFromName(actual_name)
    return -1


def _safe_val(v):
    """Convert value to safe string, returning empty string for null/None."""
    if v is None:
        return ""
    v = str(v).strip()
    return "" if v.lower() in ("", "nan", "none", "null") else v


def _batch_write_attrs(layer, attr_map, layer_name):
    """Write attributes via dataProvider -- bypasses edit buffer completely.
    attr_map: {feat_id: {field_idx: value, ...}, ...}
    Returns (written_count, error_msg or None)."""
    if not layer or not layer.isValid():
        return 0, "layer invalid"
    if not attr_map:
        return 0, None
    try:
        # Roll back any stale edit session first
        if layer.isEditable():
            try:
                layer.rollBack()
            except Exception:
                pass
            time.sleep(0.2)
        ok = layer.dataProvider().changeAttributeValues(attr_map)
        if ok:
            layer.triggerRepaint()
            return len(attr_map), None
        else:
            return 0, "dataProvider.changeAttributeValues returned False"
    except Exception as e:
        return 0, str(e)[:200]


def _ensure_field(layer, field_name, field_type=QVariant.String, length=100):
    """Create field via dataProvider (safe when not editing). Returns field index."""
    idx = find_field(layer, [field_name])
    if idx >= 0:
        return idx
    try:
        dp = layer.dataProvider()
        dp.addAttributes([QgsField(field_name, field_type, len=length)])
        layer.updateFields()
        return find_field(layer, [field_name])
    except Exception:
        return -1


def _create_named_field(layer, field_name, field_type=QVariant.String, length=100):
    """Create a named field on a layer if it does not already exist.
    Returns the field index."""
    return _ensure_field(layer, field_name, field_type, length)


# =============================================================================
# FTTH Label Algorithm
# =============================================================================

class FTTHLabelAlgorithm(QgsProcessingAlgorithm):
    IN_AG = 'IN_AG'
    IN_BLOCKS = 'IN_BLOCKS'
    IN_FJ = 'IN_FJ'
    IN_DJ = 'IN_DJ'
    IN_DC = 'IN_DC'
    IN_POLES = 'IN_POLES'
    IN_FC = 'IN_FC'

    PARAM_AREA = 'PARAM_AREA'
    PARAM_ZONE = 'PARAM_ZONE'
    PARAM_AG_ID = 'PARAM_AG_ID'
    PARAM_BLOCK_ID = 'PARAM_BLOCK_ID'
    PARAM_FC_ID = 'PARAM_FC_ID'
    PARAM_TARGET = 'PARAM_TARGET'
    PARAM_OVERWRITE = 'PARAM_OVERWRITE'
    PARAM_BUFFER = 'PARAM_BUFFER'
    PARAM_OUTPUT = 'PARAM_OUTPUT'

    # Layer selection checkboxes
    PARAM_LABEL_AG = 'PARAM_LABEL_AG'
    PARAM_LABEL_BLOCK = 'PARAM_LABEL_BLOCK'
    PARAM_LABEL_FJ = 'PARAM_LABEL_FJ'
    PARAM_LABEL_DJ = 'PARAM_LABEL_DJ'
    PARAM_LABEL_DC = 'PARAM_LABEL_DC'
    PARAM_LABEL_POLE = 'PARAM_LABEL_POLE'
    PARAM_LABEL_FC = 'PARAM_LABEL_FC'

    def name(self):
        return 'ftth_labeler'

    def displayName(self):
        return 'FTTH Auto Labeler'

    def group(self):
        return 'FTTH Tools'

    def groupId(self):
        return 'ftth_tools'

    def createInstance(self):
        return FTTHLabelAlgorithm()

    def shortHelpString(self):
        return """
        <h3>FTTH Auto Labeler v6.8.22 -- By Mustafa M M Ellaham</h3>

        <h4>STRICT INPUT (you must provide):</h4>
        <ul>
        <li><b>AG Polygons</b>: ID column with AG numbers (1,2,3...)</li>
        <li><b>Block Polygons</b>: ID column with block numbers (1,2,3...)</li>
        <li><b>FJ, DJ, DC</b>: any table structure -- plugin auto-creates all columns</li>
        </ul>

        <h4>OPTIONAL INPUT:</h4>
        <ul>
        <li><b>Feeder Cable (FC) Lines</b>: one line per cable route. ID column with cable numbers. Plugin auto-detects start/end AGs and FJ count along route.</li>
        </ul>

        <h4>PARAMETERS (you enter when running):</h4>
        <ul>
        <li><b>Area Code</b>: any length (type YOUR actual area code)</li>
        <li><b>Zone Code</b>: e.g., Z01, Z02 (optional -- leave empty for no zone)</li>
        <li><b>AG ID Field</b>: column name with AG numbers (default: ID)</li>
        <li><b>Block ID Field</b>: column name with block numbers (default: ID)</li>
        <li><b>FC ID Field</b>: column name with cable numbers (default: ID)</li>
        </ul>

        <h4>Huawei Pre-Con Splitter Logic:</h4>
        <ul>
        <li>Position 4 = always 1:8 (terminal)</li>
        <li>Positions 1,2,3 = always 1:9 (intermediate)</li>
        </ul>
        """

    def initAlgorithm(self, config=None):
        # Required layers
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_AG, 'AG Polygons (MUST have ID column with AG numbers)',
            [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_BLOCKS, 'Block Polygons (MUST have ID column with block numbers)',
            [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_FJ, 'Feeder Joint (FJ) Points (any table structure)',
            [QgsProcessing.TypeVectorPoint]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_DJ, 'Distribution Joint (DJ) Points (any table structure)',
            [QgsProcessing.TypeVectorPoint]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_DC, 'Distribution Cable (DC) Lines -- individual segments',
            [QgsProcessing.TypeVectorLine]
        ))
        # Optional
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_POLES, 'Pole Points (optional, any table)',
            [QgsProcessing.TypeVectorPoint], optional=True
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_FC, 'Feeder Cable (FC) Lines -- optional, one line per cable route',
            [QgsProcessing.TypeVectorLine], optional=True
        ))
        # Parameters
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_AREA, 'Area Code (e.g., VTN_HHS_GMG -- type YOUR actual area code)',
            defaultValue=''
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_ZONE, 'Zone Code (optional, e.g., Z02 -- leave empty for no zone)',
            defaultValue='', optional=True
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_AG_ID, 'AG ID Field Name (your AG number column)',
            defaultValue='ID'
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_BLOCK_ID, 'Block ID Field Name (your block number column)',
            defaultValue='ID'
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_FC_ID, 'FC ID Field Name (your feeder cable number column)',
            defaultValue='ID'
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_TARGET, 'Target Field Name for Labels',
            defaultValue='name'
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_OVERWRITE, 'Overwrite existing values',
            defaultValue=False
        ))
        # Layer selection checkboxes
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_LABEL_AG, 'Label AG layers', defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_LABEL_BLOCK, 'Label Block layers', defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_LABEL_FJ, 'Label FJ layers', defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_LABEL_DJ, 'Label DJ layers', defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_LABEL_DC, 'Label DC cables', defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_LABEL_POLE, 'Label Poles', defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PARAM_LABEL_FC, 'Label FC cables', defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.PARAM_BUFFER, 'Node Snap Tolerance (meters)',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=2.0, minValue=0.1, maxValue=50.0
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.PARAM_OUTPUT, 'Output Folder'
        ))

    # ---- Static Helpers ----

    @staticmethod
    def _find_field(layer, field_names):
        """Find field index, case-insensitive. Returns -1 if not found."""
        all_names = [f.name() for f in layer.fields()]
        for fn in field_names:
            fn_lower = fn.lower()
            for actual_name in all_names:
                if actual_name.lower() == fn_lower:
                    return layer.fields().indexFromName(actual_name)
        return -1

    @staticmethod
    def _list_fields(layer):
        return [(f.name(), f.typeName()) for f in layer.fields()]

    @staticmethod
    def _ensure_field(layer, field_name, field_type=QVariant.String, length=100):
        """Create field via dataProvider (safe when not editing)."""
        idx = FTTHLabelAlgorithm._find_field(layer, [field_name])
        if idx >= 0:
            return idx
        try:
            dp = layer.dataProvider()
            dp.addAttributes([QgsField(field_name, field_type, len=length)])
            layer.updateFields()
            return FTTHLabelAlgorithm._find_field(layer, [field_name])
        except Exception:
            return -1

    @staticmethod
    def _safe_write(layer, feat_id, field_idx, value, overwrite=False):
        """Write attribute safely. Handles QGIS NULL (QVariant) properly."""
        if field_idx < 0 or feat_id < 0:
            return False
        try:
            if not layer.isEditable():
                return False
            feat = layer.getFeature(feat_id)
            if not feat.isValid():
                return False
            if overwrite:
                layer.changeAttributeValue(feat_id, field_idx, value)
                return True
            current = feat.attribute(field_idx)
            if current is None:
                layer.changeAttributeValue(feat_id, field_idx, value)
                return True
            try:
                from qgis.core import QgsVariantUtils
                if QgsVariantUtils.isNull(current):
                    layer.changeAttributeValue(feat_id, field_idx, value)
                    return True
            except Exception:
                pass
            if str(current).strip() in ('', 'NULL', 'None'):
                layer.changeAttributeValue(feat_id, field_idx, value)
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def _batch_write_via_dataprovider(layer, updates, field_idx=None):
        """Batch write attributes via dataProvider -- bypasses edit buffer.
        updates: {feat_id: value} dict
        field_idx: target field index (auto-detected if None)
        Returns: number of successful writes
        """
        if not updates:
            return 0
        dp = layer.dataProvider()
        if field_idx is None:
            field_idx = FTTHLabelAlgorithm._find_field(layer, ['name', 'Name', 'NAME'])
        if field_idx < 0:
            return 0
        changes = {}
        for feat_id, value in updates.items():
            changes[feat_id] = {field_idx: value}
        try:
            ok = dp.changeAttributeValues(changes)
            return len(changes) if ok else 0
        except Exception:
            return 0

    # ---- Main Processing ----

    def processAlgorithm(self, parameters, context, feedback):
        area_code = self.parameterAsString(parameters, self.PARAM_AREA, context)
        zone = self.parameterAsString(parameters, self.PARAM_ZONE, context)
        ag_id_field = self.parameterAsString(parameters, self.PARAM_AG_ID, context) or 'ID'
        block_id_field = self.parameterAsString(parameters, self.PARAM_BLOCK_ID, context) or 'ID'
        fc_id_field = self.parameterAsString(parameters, self.PARAM_FC_ID, context) or 'ID'
        fc_size_default = '144F'
        target_field = self.parameterAsString(parameters, self.PARAM_TARGET, context) or 'name'
        overwrite = self.parameterAsBoolean(parameters, self.PARAM_OVERWRITE, context)
        label_ag = self.parameterAsBoolean(parameters, self.PARAM_LABEL_AG, context)
        label_block = self.parameterAsBoolean(parameters, self.PARAM_LABEL_BLOCK, context)
        label_fj = self.parameterAsBoolean(parameters, self.PARAM_LABEL_FJ, context)
        label_dj = self.parameterAsBoolean(parameters, self.PARAM_LABEL_DJ, context)
        label_dc = self.parameterAsBoolean(parameters, self.PARAM_LABEL_DC, context)
        label_pole = self.parameterAsBoolean(parameters, self.PARAM_LABEL_POLE, context)
        label_fc = self.parameterAsBoolean(parameters, self.PARAM_LABEL_FC, context)
        tolerance = self.parameterAsDouble(parameters, self.PARAM_BUFFER, context)
        output_folder = self.parameterAsString(parameters, self.PARAM_OUTPUT, context)

        ag_layer = self.parameterAsVectorLayer(parameters, self.IN_AG, context)
        blocks_layer = self.parameterAsVectorLayer(parameters, self.IN_BLOCKS, context)
        fj_layer = self.parameterAsVectorLayer(parameters, self.IN_FJ, context)
        dj_layer = self.parameterAsVectorLayer(parameters, self.IN_DJ, context)
        dc_layer = self.parameterAsVectorLayer(parameters, self.IN_DC, context)
        poles_layer = self.parameterAsVectorLayer(parameters, self.IN_POLES, context)
        fc_layer = self.parameterAsVectorLayer(parameters, self.IN_FC, context)

        feedback.pushInfo("=" * 60)
        feedback.pushInfo("FTTH Auto Labeler v6.8.22 -- By Mustafa M M Ellaham")
        feedback.pushInfo("=" * 60)
        feedback.pushInfo(f"Area Code: {area_code}")
        feedback.pushInfo(f"Zone: {zone}")
        feedback.pushInfo(f"AG ID Field: {ag_id_field}")
        feedback.pushInfo(f"Block ID Field: {block_id_field}")
        if fc_layer:
            feedback.pushInfo(f"FC ID Field: {fc_id_field}")
        feedback.pushInfo(f"Target Field: {target_field}")
        feedback.pushInfo(f"Snap Tolerance: {tolerance}m")
        feedback.pushInfo("")
        feedback.pushInfo("Layer selection:")
        feedback.pushInfo("  AG:   {}".format('YES' if label_ag else 'SKIPPED'))
        feedback.pushInfo("  Block: {}".format('YES' if label_block else 'SKIPPED'))
        feedback.pushInfo("  FJ:   {}".format('YES' if label_fj else 'SKIPPED'))
        feedback.pushInfo("  DJ:   {}".format('YES' if label_dj else 'SKIPPED'))
        feedback.pushInfo("  DC:   {}".format('YES' if label_dc else 'SKIPPED'))
        feedback.pushInfo("  Pole: {}".format('YES' if label_pole else 'SKIPPED'))
        feedback.pushInfo("  FC:   {}".format('YES' if label_fc else 'SKIPPED'))

        # ===== PHASE 0: Read AG and Block IDs =====
        feedback.setProgress(5)
        feedback.pushInfo("[Phase 0] Reading AG and Block IDs...")

        engine = FTTHTraceEngine(area_code, zone)

        ag_id_idx = self._find_field(ag_layer, [ag_id_field, 'id', 'ID', 'Id', 'fid', 'FID'])
        feedback.pushInfo(f"  AG layer fields: {self._list_fields(ag_layer)}")
        feedback.pushInfo(f"  AG ID field index: {ag_id_idx}")

        ag_data = []
        if ag_id_idx >= 0:
            for feat in ag_layer.getFeatures():
                val = feat.attribute(ag_id_idx)
                if val is not None:
                    try:
                        ag_num = int(val)
                        ag_data.append((feat.id(), feat, ag_num))
                    except Exception:
                        pass

        feedback.pushInfo(f"  Found {len(ag_data)} AGs:")
        for _, _, num in ag_data:
            feedback.pushInfo(f"    ID={num} -> AG{num:02d} (full: {engine.generate_ag_name(num)})")

        if len(ag_data) == 0:
            feedback.pushInfo("  ERROR: No AGs found. Check AG ID field name.")
            return {self.PARAM_OUTPUT: output_folder}

        # Read Blocks
        block_id_idx = self._find_field(blocks_layer, [block_id_field, 'id', 'ID', 'Id', 'fid', 'FID'])
        feedback.pushInfo(f"  Block layer fields: {self._list_fields(blocks_layer)}")
        feedback.pushInfo(f"  Block ID field index: {block_id_idx}")

        block_data = []
        if block_id_idx >= 0:
            for feat in blocks_layer.getFeatures():
                val = feat.attribute(block_id_idx)
                if val is not None:
                    try:
                        b_num = int(val)
                        ag_short = 'AG01'
                        centroid = feat.geometry().centroid()
                        for _, ag_feat, ag_num in ag_data:
                            if ag_feat.geometry().contains(centroid):
                                ag_short = f"AG{ag_num:02d}"
                                break
                        block_data.append((feat.id(), feat, b_num, f"B{b_num:03d}", ag_short))
                    except Exception:
                        pass

        feedback.pushInfo(f"  Found {len(block_data)} Blocks:")
        for _, _, num, bname, ag_short in block_data:
            feedback.pushInfo(f"    ID={num} -> {bname} (AG: {ag_short}, full: {engine.generate_block_name(num)})")

        if len(block_data) == 0:
            feedback.pushInfo("  ERROR: No Blocks found. Check Block ID field name.")
            return {self.PARAM_OUTPUT: output_folder}

        # Read FC data (optional)
        fc_data = []
        fc_labels_map = {}
        if fc_layer and label_fc:
            feedback.pushInfo("")
            feedback.pushInfo("[FC] Reading Feeder Cable lines...")
            fc_id_idx = self._find_field(fc_layer, [fc_id_field, 'id', 'ID', 'Id'])
            fc_size_idx = self._find_field(fc_layer, ['size', 'Size', 'SIZE', 'cable_size'])
            fc_type_idx = self._find_field(fc_layer, ['type', 'Type', 'TYPE', 'cable_type'])
            feedback.pushInfo(f"  FC layer fields: {self._list_fields(fc_layer)}")
            feedback.pushInfo(f"  FC ID field index: {fc_id_idx}")

            fc_raw = []
            if fc_id_idx >= 0:
                for feat in fc_layer.getFeatures():
                    val = feat.attribute(fc_id_idx)
                    if val is not None:
                        try:
                            fc_num = int(val)
                            fc_size_val = fc_size_default
                            if fc_size_idx >= 0:
                                s = feat.attribute(fc_size_idx)
                                if s is not None and str(s).strip():
                                    fc_size_val = f"{int(s)}F"
                            fc_type_val = 'FC'
                            if fc_type_idx >= 0:
                                t = feat.attribute(fc_type_idx)
                                if t is not None and str(t).strip():
                                    fc_type_val = str(t).strip()
                            fc_raw.append((feat.id(), feat, fc_num, fc_size_val, fc_type_val))
                        except Exception:
                            pass

            fc_raw.sort(key=lambda x: x[2])
            type_counters = {}
            fj_geoms = [(f.id(), f.geometry()) for f in fj_layer.getFeatures()]
            ag_geom_index = [(ag_num, ag_feat.geometry()) for _, ag_feat, ag_num in ag_data]

            for feat_id, feat, fc_num, cable_size_from_layer, fc_type in fc_raw:
                fc_geom = feat.geometry()
                route_length = fc_geom.length()

                if fc_type not in type_counters:
                    type_counters[fc_type] = 0
                type_counters[fc_type] += 1
                type_num = type_counters[fc_type]

                intersected_ags = []
                for ag_num, ag_geom in ag_geom_index:
                    if fc_geom.intersects(ag_geom):
                        intersected_ags.append(ag_num)

                if len(intersected_ags) >= 2:
                    ag_start = min(intersected_ags)
                    ag_end = max(intersected_ags)
                elif len(intersected_ags) == 1:
                    ag_start = ag_end = intersected_ags[0]
                else:
                    start_pt = fc_geom.interpolate(0)
                    end_pt = fc_geom.interpolate(fc_geom.length())
                    ag_start = ag_geom_index[0][0] if ag_geom_index else 1
                    ag_end = ag_geom_index[-1][0] if ag_geom_index else 1
                    min_start = min_end = float('inf')
                    for ag_num, ag_geom in ag_geom_index:
                        d_start = start_pt.distance(ag_geom)
                        d_end = end_pt.distance(ag_geom)
                        if d_start < min_start:
                            min_start = d_start
                            ag_start = ag_num
                        if d_end < min_end:
                            min_end = d_end
                            ag_end = ag_num

                ag_start_short = f"AG{ag_start:02d}"
                ag_end_short = f"AG{ag_end:02d}"

                fj_count = 0
                for _, fj_geom in fj_geoms:
                    if fc_geom.distance(fj_geom) <= tolerance:
                        fj_count += 1

                fc_name = engine.generate_fc_name(
                    ag_start_short, ag_end_short, type_num,
                    cable_size=cable_size_from_layer, route_length=route_length,
                    fj_count=fj_count, fc_type=fc_type
                )

                fc_slack = int(route_length * 0.08)
                fc_data.append((feat_id, feat, fc_num))
                fc_labels_map[feat_id] = {
                    'fc_name': fc_name,
                    'fc_num': type_num,
                    'fc_type': fc_type,
                    'ag_start': ag_start_short,
                    'ag_end': ag_end_short,
                    'route_length': route_length,
                    'fj_count': fj_count,
                    'slack': fc_slack
                }
                display_prefix = fc_type if fc_type.upper() == 'CC0X' else f"{fc_type}{type_num:02d}"
                feedback.pushInfo(f"    {display_prefix}: {ag_start_short}-{ag_end_short}, "
                                  f"{route_length:.0f}m, {fj_count} FJs, "
                                  f"slack={fc_slack}m (8%), size={cable_size_from_layer}")

            feedback.pushInfo(f"  Found {len(fc_data)} Feeder Cable(s)")

        # ===== PHASE 1: Read geometry layers =====
        feedback.setProgress(15)
        feedback.pushInfo("")
        feedback.pushInfo("[Phase 1] Reading FJ, DJ, DC geometry layers...")

        fj_data = [(f.id(), f, '') for f in fj_layer.getFeatures()]
        for i, (fid, feat, _) in enumerate(fj_data):
            ag_assigned = None
            fj_geom = feat.geometry()
            for _, ag_feat, ag_num in ag_data:
                if ag_feat.geometry().contains(fj_geom):
                    ag_assigned = f"AG{ag_num:02d}"
                    break
            if ag_assigned is None:
                min_dist = float('inf')
                ag_assigned = f"AG{ag_data[0][2]:02d}" if ag_data else 'AG01'
                for _, ag_feat, ag_num in ag_data:
                    d = ag_feat.geometry().centroid().distance(fj_geom)
                    if d < min_dist:
                        min_dist = d
                        ag_assigned = f"AG{ag_num:02d}"
            fj_data[i] = (fid, feat, ag_assigned)

        dj_data = [(f.id(), f) for f in dj_layer.getFeatures()]
        dc_data = [(f.id(), f) for f in dc_layer.getFeatures()]
        poles_data = [(f.id(), f) for f in poles_layer.getFeatures()] if poles_layer else []

        feedback.pushInfo(f"  FJs: {len(fj_data)}")
        feedback.pushInfo(f"  DJs: {len(dj_data)}")
        feedback.pushInfo(f"  DC segments: {len(dc_data)}")
        feedback.pushInfo(f"  Poles: {len(poles_data)}")

        # ===== PHASE 2: Run tracing engine =====
        feedback.setProgress(30)
        feedback.pushInfo("")
        feedback.pushInfo("[Phase 2] Tracing DC network and generating labels...")

        results = engine.run_full_labeling(
            ag_data, block_data, fj_data, dj_data, dc_data,
            poles_data=None, debug_log=feedback.pushInfo
        )

        for ag_name, fj_result in results['ags'].items():
            feedback.pushInfo(f"  {fj_result['fj_name']} (AG: {ag_name}):")
            for chain in fj_result['block_chains']:
                names = [d['dj_name'] for d in chain['djs']]
                positions = [str(d['position']) for d in chain['djs']]
                ratios = [d['ratio'] for d in chain['djs']]
                feedback.pushInfo(f"    Block {chain['block_name']} ({chain['dj_count']} DJs):")
                feedback.pushInfo(f"      DJs: {', '.join(names)}")
                feedback.pushInfo(f"      Positions: {', '.join(positions)}")
                feedback.pushInfo(f"      Ratios: {', '.join(ratios)}")

        # ===== PHASE 2.5: Three-stage Pole Labeling =====
        pole_labels = {}
        pole_stage1_count = 0
        pole_stage2_count = 0
        pole_stage3_count = 0

        if label_pole:
            if not label_dc:
                feedback.pushInfo("")
                feedback.pushInfo("[Phase 2.5] Labeling poles (3-stage)...")
                feedback.reportError("  ERROR: Cannot label poles without DC labels. Enable 'Label DC cables' or skip poles.")
            elif poles_layer and poles_data:
                feedback.pushInfo("")
                feedback.pushInfo("[Phase 2.5] Labeling poles (3-stage)...")

                def _find_poles_on_line(line_geom, pole_candidates, tol=2.0):
                    on_line = []
                    for p_fid, p_feat in pole_candidates:
                        p_geom = p_feat.geometry()
                        dist = line_geom.distance(p_geom)
                        if dist <= tol:
                            projected_dist = line_geom.lineLocatePoint(p_geom)
                            on_line.append((p_fid, projected_dist))
                    on_line.sort(key=lambda x: x[1])
                    return on_line

                all_lines = []

                # ---- STAGE 1: FC Poles ----
                if fc_data and fc_layer:
                    fc_sorted = sorted(fc_data, key=lambda x: x[2])
                    for fc_fid, fc_feat, fc_num in fc_sorted:
                        fc_geom = fc_feat.geometry()
                        all_lines.append((fc_geom, 1, fc_num))
                        poles_on_fc = _find_poles_on_line(fc_geom, poles_data, tolerance)
                        for p_fid, proj_dist in poles_on_fc:
                            if p_fid not in pole_labels:
                                pole_labels[p_fid] = (engine.generate_pole_name(), proj_dist, 1)
                                pole_stage1_count += 1
                    feedback.pushInfo(f"  Stage 1 (FC): {pole_stage1_count} poles on FC cables")

                # ---- STAGE 2: DC Poles ----
                def _ag_sort_key(ag_name):
                    try:
                        return int(re.search(r'\d+', ag_name).group())
                    except Exception:
                        return 0

                dj_geom_lookup = {}
                for d_fid, d_feat in dj_data:
                    dj_geom_lookup[d_fid] = d_feat.geometry()

                fj_geom_lookup = {}
                for f_fid, f_feat, f_ag in fj_data:
                    fj_geom_lookup[f_fid] = f_feat.geometry()

                dj_name_to_fid = {}
                for agn, fj_res in results['ags'].items():
                    for chain in fj_res['block_chains']:
                        for dj in chain['djs']:
                            dj_name_to_fid[dj['dj_name']] = dj['feat_id']

                dc_geom_lookup = {fid: feat.geometry() for fid, feat in dc_data}

                for ag_name in sorted(results['ags'].keys(), key=_ag_sort_key):
                    fj_result = results['ags'][ag_name]
                    for chain in fj_result['block_chains']:
                        for dc in chain['dc_cables']:
                            dc_fid = dc.get('dc_feat_id')
                            if dc_fid is None or dc_fid not in dc_geom_lookup:
                                continue
                            dc_geom = dc_geom_lookup[dc_fid]
                            all_lines.append((dc_geom, 2, len(all_lines)))

                            poles_on_dc = _find_poles_on_line(dc_geom, poles_data, tolerance)

                            if len(poles_on_dc) == 0:
                                continue

                            from_node_name = dc.get('from_node', '')
                            to_node_name = dc.get('to_node', '')

                            from_geom = None
                            to_geom = None

                            for f_fid, f_feat, f_ag in fj_data:
                                fj_display = engine.generate_fj_name(f_ag)
                                if fj_display == from_node_name:
                                    from_geom = f_feat.geometry()
                                    break

                            if from_geom is None:
                                d_fid = dj_name_to_fid.get(from_node_name)
                                if d_fid and d_fid in dj_geom_lookup:
                                    from_geom = dj_geom_lookup[d_fid]

                            d_fid = dj_name_to_fid.get(to_node_name)
                            if d_fid and d_fid in dj_geom_lookup:
                                to_geom = dj_geom_lookup[d_fid]

                            if from_geom is not None and to_geom is not None:
                                from_proj = dc_geom.lineLocatePoint(from_geom)
                                to_proj = dc_geom.lineLocatePoint(to_geom)
                                if from_proj > to_proj:
                                    max_dist = dc_geom.length()
                                    poles_on_dc = [(p_fid, max_dist - proj_dist)
                                                   for p_fid, proj_dist in poles_on_dc]
                                    poles_on_dc.sort(key=lambda x: x[1])

                            for p_fid, _ in poles_on_dc:
                                if p_fid not in pole_labels:
                                    pole_labels[p_fid] = (engine.generate_pole_name(), 0, 2)
                                    pole_stage2_count += 1
                feedback.pushInfo(f"  Stage 2 (DC): {pole_stage2_count} poles on DC cables")

                # ---- STAGE 3: Nearest-line fallback ----
                unlabeled = [(pf, pf) for pf, _ in poles_data if pf not in pole_labels]
                if unlabeled:
                    feedback.pushInfo(f"  Stage 3 (Fallback): {len(unlabeled)} poles not on any cable within {tolerance}m...")
                    for p_fid, _ in unlabeled:
                        p_geom = None
                        for pf, pft in poles_data:
                            if pf == p_fid:
                                p_geom = pft.geometry()
                                break
                        if p_geom is None:
                            continue
                        best_dist = float('inf')
                        best_geom = None
                        best_priority = 999
                        for line_geom, priority, _ in all_lines:
                            d = line_geom.distance(p_geom)
                            if d < best_dist or (abs(d - best_dist) < 0.001 and priority < best_priority):
                                best_dist = d
                                best_geom = line_geom
                                best_priority = priority
                        if best_geom is not None:
                            proj_dist = best_geom.lineLocatePoint(p_geom)
                            pole_labels[p_fid] = (engine.generate_pole_name(), proj_dist, 3)
                            pole_stage3_count += 1
                    feedback.pushInfo(f"  Stage 3 (Fallback): {pole_stage3_count} assigned to nearest line")

                feedback.pushInfo(f"  Total: {len(pole_labels)} / {len(poles_data)} poles labeled")
                if len(pole_labels) < len(poles_data):
                    feedback.pushInfo(f"  WARNING: {len(poles_data) - len(pole_labels)} poles unlabeled")
        else:
            feedback.pushInfo("")
            feedback.pushInfo("[Phase 2.5] Pole labeling SKIPPED")

        # ===== PHASE 3: Create ALL fields first =====
        feedback.setProgress(60)
        feedback.pushInfo("")
        feedback.pushInfo("[Phase 3] Creating fields...")

        ag_name_idx = -1
        if label_ag:
            ag_name_idx = self._ensure_field(ag_layer, target_field)
            feedback.pushInfo(f"  AG '{target_field}': {'OK' if ag_name_idx >= 0 else 'FAILED'}")

        block_name_idx = -1
        block_ag_idx = -1
        if label_block:
            block_name_idx = self._ensure_field(blocks_layer, target_field)
            block_ag_idx = self._ensure_field(blocks_layer, 'ag_parent')
            feedback.pushInfo(f"  Block '{target_field}': {'OK' if block_name_idx >= 0 else 'FAILED'}")
            feedback.pushInfo(f"  Block 'ag_parent': {'OK' if block_ag_idx >= 0 else 'FAILED'}")

        fj_name_idx = -1
        if label_fj:
            fj_name_idx = self._ensure_field(fj_layer, target_field)
            feedback.pushInfo(f"  FJ '{target_field}': {'OK' if fj_name_idx >= 0 else 'FAILED'}")

        dj_name_idx = -1
        dj_split_idx = -1
        dj_pos_idx = -1
        dj_dc_idx = -1
        if label_dj:
            dj_name_idx = self._ensure_field(dj_layer, target_field)
            dj_split_idx = self._ensure_field(dj_layer, 'splitter', QVariant.String, 10)
            dj_pos_idx = self._ensure_field(dj_layer, 'position', QVariant.Int)
            dj_dc_idx = self._ensure_field(dj_layer, 'dc_name', QVariant.String, 200)
            feedback.pushInfo(f"  DJ '{target_field}': {'OK' if dj_name_idx >= 0 else 'FAILED'}")
            feedback.pushInfo(f"  DJ 'splitter': {'OK' if dj_split_idx >= 0 else 'FAILED'}")
            feedback.pushInfo(f"  DJ 'position': {'OK' if dj_pos_idx >= 0 else 'FAILED'}")
            feedback.pushInfo(f"  DJ 'dc_name': {'OK' if dj_dc_idx >= 0 else 'FAILED'}")

        dc_name_idx = -1
        dc_from_idx = -1
        dc_to_idx = -1
        if label_dc:
            dc_name_idx = self._ensure_field(dc_layer, target_field)
            dc_from_idx = self._ensure_field(dc_layer, 'from_node', QVariant.String, 100)
            dc_to_idx = self._ensure_field(dc_layer, 'to_node', QVariant.String, 100)
            feedback.pushInfo(f"  DC '{target_field}': {'OK' if dc_name_idx >= 0 else 'FAILED'}")
            feedback.pushInfo(f"  DC 'from_node': {'OK' if dc_from_idx >= 0 else 'FAILED'}")
            feedback.pushInfo(f"  DC 'to_node': {'OK' if dc_to_idx >= 0 else 'FAILED'}")

        pole_name_idx = -1
        if label_pole and poles_layer:
            pole_name_idx = self._ensure_field(poles_layer, target_field)
            feedback.pushInfo(f"  Pole '{target_field}': {'OK' if pole_name_idx >= 0 else 'FAILED'}")

        fc_name_idx = -1
        if label_fc and fc_layer:
            fc_name_idx = self._ensure_field(fc_layer, target_field)
            feedback.pushInfo(f"  FC '{target_field}': {'OK' if fc_name_idx >= 0 else 'FAILED'}")

        # ===== VALIDATION GATE =====
        validation_report = os.path.join(output_folder, 'preflight_validation_report.txt')
        if os.path.exists(validation_report):
            try:
                with open(validation_report, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'CRITICAL issues' in content or 'CRITICAL' in content:
                    feedback.reportError("=" * 60)
                    feedback.reportError("VALIDATION GATE BLOCKED")
                    feedback.reportError("=" * 60)
                    feedback.reportError("A pre-flight validation report with CRITICAL issues was found.")
                    feedback.reportError("File: " + validation_report)
                    feedback.reportError("")
                    feedback.reportError("Please either:")
                    feedback.reportError("  1. Fix the critical issues and delete the validation report, OR")
                    feedback.reportError("  2. Run the FTTH Validator again to re-check and clear the report.")
                    feedback.reportError("")
                    feedback.reportError("The labeler will NOT proceed to prevent data corruption.")
                    feedback.reportError("=" * 60)
                    return {self.PARAM_OUTPUT: output_folder}
                elif 'warnings' in content.lower() and 'ALL CHECKS PASSED' not in content:
                    feedback.pushInfo("[Validation Gate] Non-critical warnings found in previous validation.")
                    feedback.pushInfo("  File: " + validation_report)
                    feedback.pushInfo("  Proceeding with caution...")
                    feedback.pushInfo("")
            except Exception:
                pass

        # ===== BUILD LABEL LOOKUPS =====
        ag_labels = {fid: engine.generate_ag_name(num) for fid, _, num in ag_data}
        block_labels = {fid: engine.generate_block_name(bnum) for fid, _, bnum, _, _ in block_data}
        block_ag_map = {fid: f"{engine._az()}_{ag_short}" for fid, _, _, _, ag_short in block_data}

        dj_labels = {}
        dc_labels = {}
        dc_none_count = 0
        dc_dup_count = 0
        seen_dc_fids = set()
        for ag_name, fj_result in results['ags'].items():
            for chain in fj_result['block_chains']:
                for dj in chain['djs']:
                    dj_labels[dj['feat_id']] = dj
                for dc in chain['dc_cables']:
                    dc_fid = dc.get('dc_feat_id')
                    if dc_fid is not None:
                        if dc_fid in seen_dc_fids:
                            dc_dup_count += 1
                        else:
                            seen_dc_fids.add(dc_fid)
                            dc_labels[dc_fid] = dc
                    else:
                        dc_none_count += 1
        if dc_none_count > 0:
            feedback.pushInfo(f"  WARNING: {dc_none_count} DC cable(s) have no feature ID")
        if dc_dup_count > 0:
            feedback.pushInfo(f"  WARNING: {dc_dup_count} DC cable(s) have duplicate feature IDs")

        fj_labels = {}
        for fid, _, ag_name in fj_data:
            for agn, fj_res in results['ags'].items():
                if agn == ag_name:
                    fj_labels[fid] = fj_res['fj_name']
                    break

        # ===== PHASE 4: Write data (dataProvider batch) =====
        feedback.setProgress(75)
        feedback.pushInfo("")
        feedback.pushInfo("[Phase 4] Writing labels to QGIS layers (batch mode)...")

        # Write AG
        if label_ag and ag_name_idx >= 0 and ag_labels:
            updates = {}
            for feat in ag_layer.getFeatures():
                fid = feat.id()
                if fid in ag_labels:
                    updates[fid] = {ag_name_idx: ag_labels[fid]}
            written, err = _batch_write_attrs(ag_layer, updates, "AG")
            if err:
                feedback.pushInfo(f"  AG layer: ERROR -- {err}")
            else:
                feedback.pushInfo(f"  AG layer: {written} written")

        # Write Block
        if label_block and block_name_idx >= 0 and block_labels:
            updates = {}
            for feat in blocks_layer.getFeatures():
                fid = feat.id()
                if fid in block_labels:
                    up = {block_name_idx: block_labels[fid]}
                    if fid in block_ag_map and block_ag_idx >= 0:
                        up[block_ag_idx] = block_ag_map[fid]
                    updates[fid] = up
            written, err = _batch_write_attrs(blocks_layer, updates, "Block")
            if err:
                feedback.pushInfo(f"  Block layer: ERROR -- {err}")
            else:
                feedback.pushInfo(f"  Block layer: {written} written")

        # Write FJ
        if label_fj and fj_name_idx >= 0 and fj_labels:
            updates = {}
            for feat in fj_layer.getFeatures():
                fid = feat.id()
                if fid in fj_labels:
                    updates[fid] = {fj_name_idx: fj_labels[fid]}
            written, err = _batch_write_attrs(fj_layer, updates, "FJ")
            if err:
                feedback.pushInfo(f"  FJ layer: ERROR -- {err}")
            else:
                feedback.pushInfo(f"  FJ layer: {written} written")

        # Write DJ
        if label_dj and dj_name_idx >= 0 and dj_labels:
            updates = {}
            for feat in dj_layer.getFeatures():
                if feedback.isCanceled():
                    return {self.PARAM_OUTPUT: output_folder}
                fid = feat.id()
                if fid in dj_labels:
                    info = dj_labels[fid]
                    up = {dj_name_idx: info["dj_name"]}
                    if dj_split_idx >= 0:
                        up[dj_split_idx] = info["ratio"]
                    if dj_pos_idx >= 0:
                        up[dj_pos_idx] = info["position"]
                    if dj_dc_idx >= 0:
                        up[dj_dc_idx] = info["dc_name"]
                    updates[fid] = up
            written, err = _batch_write_attrs(dj_layer, updates, "DJ")
            if err:
                feedback.pushInfo(f"  DJ layer: ERROR -- {err}")
            else:
                feedback.pushInfo(f"  DJ layer: {written} written")

        # Write DC
        if label_dc and dc_name_idx >= 0 and dc_labels:
            updates = {}
            for feat in dc_layer.getFeatures():
                if feedback.isCanceled():
                    return {self.PARAM_OUTPUT: output_folder}
                fid = feat.id()
                if fid in dc_labels:
                    info = dc_labels[fid]
                    up = {dc_name_idx: info["dc_name"]}
                    if dc_from_idx >= 0:
                        up[dc_from_idx] = info["from_node"]
                    if dc_to_idx >= 0:
                        up[dc_to_idx] = info["to_node"]
                    updates[fid] = up
            written, err = _batch_write_attrs(dc_layer, updates, "DC")
            if err:
                feedback.pushInfo(f"  DC layer: ERROR -- {err}")
            else:
                feedback.pushInfo(f"  DC layer: {written} written")

        # Write Poles
        if label_pole and pole_name_idx >= 0 and pole_labels:
            updates = {}
            for feat in poles_layer.getFeatures():
                if feedback.isCanceled():
                    return {self.PARAM_OUTPUT: output_folder}
                fid = feat.id()
                if fid in pole_labels:
                    updates[fid] = {pole_name_idx: pole_labels[fid][0]}
            written, err = _batch_write_attrs(poles_layer, updates, "Pole")
            if err:
                feedback.pushInfo(f"  Pole layer: ERROR -- {err}")
            else:
                feedback.pushInfo(f"  Pole layer: {written} written (FC:{pole_stage1_count} DC:{pole_stage2_count} Fallback:{pole_stage3_count})")

        # Write FC
        if label_fc and fc_name_idx >= 0 and fc_labels_map:
            updates = {}
            for feat in fc_layer.getFeatures():
                fid = feat.id()
                if fid in fc_labels_map:
                    updates[fid] = {fc_name_idx: fc_labels_map[fid]["fc_name"]}
            written, err = _batch_write_attrs(fc_layer, updates, "FC")
            if err:
                feedback.pushInfo(f"  FC layer: ERROR -- {err}")
            else:
                feedback.pushInfo(f"  FC layer: {written} written")

        # ===== PHASE 5: Write output files =====
        feedback.setProgress(90)
        feedback.pushInfo("")
        feedback.pushInfo("[Phase 5] Writing output files...")

        os.makedirs(output_folder, exist_ok=True)

        try:
            json_path = os.path.join(output_folder, 'labeled_network.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            feedback.pushInfo(f"  [OK] labeled_network.json")
        except Exception as e:
            feedback.pushInfo(f"  [ERROR] JSON: {e}")

        try:
            csv_path = os.path.join(output_folder, 'naming_summary.csv')
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['FJ', 'Block', 'DJ_Name', 'Position', 'Ratio', 'DC_Name', 'From', 'To'])
                for ag_name, fj_result in results['ags'].items():
                    for chain in fj_result['block_chains']:
                        for i, dj in enumerate(chain['djs']):
                            dc = chain['dc_cables'][i] if i < len(chain['dc_cables']) else {}
                            writer.writerow([fj_result['fj_name'], chain['block_name'],
                                           dj['dj_name'], dj['position'], dj['ratio'],
                                           dc.get('dc_name', ''),
                                           dc.get('from_node', ''), dc.get('to_node', '')])
            feedback.pushInfo(f"  [OK] naming_summary.csv")
        except Exception as e:
            feedback.pushInfo(f"  [ERROR] CSV: {e}")

        if fc_labels_map:
            try:
                fc_csv_path = os.path.join(output_folder, 'fc_summary.csv')
                with open(fc_csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['FC_Name', 'FC_Num', 'Start_AG', 'End_AG',
                                     'Route_Length_m', 'FJ_Count', 'Slack_m'])
                    for fid, info in fc_labels_map.items():
                        writer.writerow([info['fc_name'], info['fc_num'],
                                         info['ag_start'], info['ag_end'],
                                         f"{info['route_length']:.0f}",
                                         info['fj_count'], info['slack']])
                feedback.pushInfo(f"  [OK] fc_summary.csv")
            except Exception as e:
                feedback.pushInfo(f"  [ERROR] FC CSV: {e}")

        try:
            report_path = os.path.join(output_folder, 'validation_report.txt')
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("FTTH Labeler V1.0 -- Report\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Area: {area_code}, Zone: {zone}\n\n")
                f.write(f"AGs: {results['summary']['total_ags']}\n")
                f.write(f"Blocks: {results['summary']['total_blocks']}\n")
                f.write(f"DJs: {results['summary']['total_djs']}\n")
                f.write(f"DC Cables: {results['summary']['total_dc']}\n")
                if fc_labels_map:
                    f.write(f"FC Cables: {len(fc_labels_map)}\n")
                if results['summary']['total_poles'] > 0:
                    f.write(f"Poles: {results['summary']['total_poles']}\n")
            feedback.pushInfo(f"  [OK] validation_report.txt")
        except Exception as e:
            feedback.pushInfo(f"  [ERROR] Report: {e}")

        # ===== DONE =====
        feedback.setProgress(100)
        feedback.pushInfo("")
        feedback.pushInfo("=" * 60)
        feedback.pushInfo("LABELING COMPLETE")
        feedback.pushInfo("=" * 60)
        feedback.pushInfo(f"Output: {output_folder}")

        return {self.PARAM_OUTPUT: output_folder}


# =============================================================================
# FTTH Labeler Provider
# =============================================================================

class FTTHLabelerProvider(QgsProcessingProvider):
    def loadAlgorithms(self, *args, **kwargs):
        self.addAlgorithm(FTTHLabelAlgorithm())

    def id(self):
        return 'ftth_labeler'

    def name(self):
        return 'FTTH Tools'


# =============================================================================
# FTTH Labeler Plugin
# =============================================================================

class FTTHLabelerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = FTTHLabelerProvider()
        self.menu = None
        self.actions = []

    def initGui(self):
        # Add Processing algorithms
        QgsApplication.processingRegistry().addProvider(self.provider)

        # Add menu under Plugins menu
        self.menu = QMenu("FTTH Auto Labeler", self.iface.mainWindow())

        # Labeler action
        action_label = QAction("FTTH Labeler", self.iface.mainWindow())
        action_label.triggered.connect(self._run_labeler)
        self.menu.addAction(action_label)
        self.actions.append(action_label)

        # Add separator
        self.menu.addSeparator()

        # About action
        action_about = QAction("About", self.iface.mainWindow())
        action_about.triggered.connect(self._show_about)
        self.menu.addAction(action_about)
        self.actions.append(action_about)

        # Add menu to Plugins menu bar
        plugins_menu = self.iface.pluginMenu()
        plugins_menu.addMenu(self.menu)

    def unload(self):
        # Remove Processing provider
        QgsApplication.processingRegistry().removeProvider(self.provider)
        # Remove menu actions
        plugins_menu = self.iface.pluginMenu()
        if self.menu:
            plugins_menu.removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None
        self.actions = []

    def _run_labeler(self):
        processing.execAlgorithmDialog('ftth_labeler:ftth_labeler', {})

    def _show_about(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(
            self.iface.mainWindow(),
            "About FTTH Auto Labeler",
            "<h3>FTTH Auto Labeler v6.8.22</h3>"
            "<p>By Mustafa M M Ellaham</p>"
            "<p>Automated FTTH network labeling for QGIS</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Auto-label AG, Block, FJ, DJ, DC, Pole</li>"
            "<li>FC cable auto-labeling</li>"
            "<li>Huawei Pre-Con splitter logic</li>"
            "<li>3-stage pole labeling</li>"
            "</ul>"
        )
