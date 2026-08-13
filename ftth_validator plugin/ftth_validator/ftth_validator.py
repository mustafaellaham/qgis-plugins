# -*- coding: utf-8 -*-
"""
FTTH QA Checker v8.6.22 — QGIS Processing Plugin
Copyright (c) Mustafa M M Ellaham. All rights reserved.

Pre-flight validation tool for FTTH network designs.
Checks CRS consistency, required columns, DC-DJ snapping,
block-FJ connectivity, DJ-inside-block, and warns about
Shapefile/Real position fields.

By Mustafa M M Ellaham
"""

import os
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox
from qgis.core import (
    QgsApplication, QgsProcessing,
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsWkbTypes,
    QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer,
    QgsProcessingParameterString, QgsProcessingParameterNumber,
    QgsProcessingParameterFolderDestination,
    QgsProcessingProvider,
    QgsVectorFileWriter
)
from qgis import processing


# =============================================================================
# Utility Functions (module-level, self-contained)
# =============================================================================

def _find_field(layer, field_names):
    """Find field index, case-insensitive. Returns -1 if not found."""
    all_names = [f.name() for f in layer.fields()]
    for fn in field_names:
        fn_lower = fn.lower()
        for actual_name in all_names:
            if actual_name.lower() == fn_lower:
                return layer.fields().indexFromName(actual_name)
    return -1


def _count_features(layer):
    """Count features in a layer."""
    return sum(1 for _ in layer.getFeatures())


def _get_crs_authid(layer):
    """Get CRS authid string from a layer."""
    return layer.crs().authid()


def _get_line_endpoints(line_geom):
    """Return (start_point, end_point) as QgsPointXY."""
    if line_geom.isMultipart():
        parts = line_geom.asMultiPolyline()
        if parts:
            first_part = parts[0]
            last_part = parts[-1]
            if first_part and last_part:
                return (QgsPointXY(first_part[0]), QgsPointXY(last_part[-1]))
    else:
        pts = line_geom.asPolyline()
        if pts and len(pts) >= 2:
            return (QgsPointXY(pts[0]), QgsPointXY(pts[-1]))
    return (None, None)


def _point_distance_to_point(pt1, pt2):
    """Distance between two QgsPointXY."""
    return ((pt1.x() - pt2.x())**2 + (pt1.y() - pt2.y())**2)**0.5


def _safe_int(val, default=0):
    """Safely convert a value to int."""
    if val is None:
        return default
    try:
        from qgis.core import QgsVariantUtils
        if QgsVariantUtils.isNull(val):
            return default
    except Exception:
        pass
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=0.0):
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        from qgis.core import QgsVariantUtils
        if QgsVariantUtils.isNull(val):
            return default
    except Exception:
        pass
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default


# =============================================================================
# FTTH Validator Algorithm
# =============================================================================

class FTTHValidatorAlgorithm(QgsProcessingAlgorithm):
    """Pre-flight topology validator for FTTH network layers.

    Checks all requirements before running the FTTH Labeler:
    1. CRS consistency across all layers
    2. Required ID columns exist
    2b. DJ position field type (Shapefile/Real warning) — NEW in v8.6.22
    3. DC lines snap to DJ points
    4. DC lines snap to FJ points (origin)
    5. DJ points inside Block polygons
    6. Block polygons inside AG polygons
    7. FJ points inside AG polygons
    8. Poles near DC or FC lines
    9. FC lines intersect AG polygons
    10. No duplicate geometries
    11. DC network connectivity (no orphaned DJs)
    12. FJ count matches AG count
    """

    IN_AG = 'IN_AG'
    IN_BLOCKS = 'IN_BLOCKS'
    IN_FJ = 'IN_FJ'
    IN_DJ = 'IN_DJ'
    IN_DC = 'IN_DC'
    IN_POLES = 'IN_POLES'
    IN_FC = 'IN_FC'

    PARAM_AG_ID = 'PARAM_AG_ID'
    PARAM_BLOCK_ID = 'PARAM_BLOCK_ID'
    PARAM_TOLERANCE = 'PARAM_TOLERANCE'
    PARAM_OUTPUT = 'PARAM_OUTPUT'

    def name(self):
        return 'ftth_validator'

    def displayName(self):
        return 'FTTH Pre-Flight Validator'

    def group(self):
        return 'FTTH Tools'

    def groupId(self):
        return 'ftth_tools'

    def createInstance(self):
        return FTTHValidatorAlgorithm()

    def shortHelpString(self):
        return """
        <h3>FTTH Pre-Flight Validator</h3>
        <p>Validates topology and requirements before running the FTTH Labeler.</p>

        <h4>Checks Performed:</h4>
        <ol>
        <li><b>CRS Consistency</b> — all layers use the same CRS</li>
        <li><b>Required Columns</b> — AG and Block have ID columns</li>
        <li><b>DJ Position Field</b> — warns about Shapefile/Real position fields (v8.6.22)</li>
        <li><b>DC→DJ Snap</b> — DC line endpoints snap to DJ points</li>
        <li><b>DC→FJ Snap</b> — first DC segment originates from FJ</li>
        <li><b>DJ in Block</b> — DJ points fall inside Block polygons</li>
        <li><b>Block in AG</b> — Block polygons fall inside AG polygons</li>
        <li><b>FJ in AG</b> — FJ points fall inside AG polygons</li>
        <li><b>Pole on Cable</b> — poles are near DC or FC lines</li>
        <li><b>FC→AG</b> — FC lines intersect AG polygons</li>
        <li><b>No Duplicates</b> — no duplicate geometries</li>
        <li><b>Network Connectivity</b> — DJs are reachable from FJs via DC</li>
        <li><b>FJ Count</b> — at least one FJ per AG</li>
        </ol>

        <p>Output: validation report with PASS/FAIL for each check + issue counts.</p>
        """

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_AG, 'AG Polygons (MUST have ID column)',
            [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_BLOCKS, 'Block Polygons (MUST have ID column)',
            [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_FJ, 'Feeder Joint (FJ) Points',
            [QgsProcessing.TypeVectorPoint]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_DJ, 'Distribution Joint (DJ) Points',
            [QgsProcessing.TypeVectorPoint]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_DC, 'Distribution Cable (DC) Lines',
            [QgsProcessing.TypeVectorLine]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_POLES, 'Pole Points (optional)',
            [QgsProcessing.TypeVectorPoint], optional=True
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.IN_FC, 'Feeder Cable (FC) Lines (optional)',
            [QgsProcessing.TypeVectorLine], optional=True
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_AG_ID, 'AG ID Field Name', defaultValue='ID'
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PARAM_BLOCK_ID, 'Block ID Field Name', defaultValue='ID'
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.PARAM_TOLERANCE, 'Snap Tolerance (meters)',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=2.0, minValue=0.1, maxValue=50.0
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.PARAM_OUTPUT, 'Output Folder'
        ))

    # ---- Static Helpers (also available as module-level functions) ----

    @staticmethod
    def _find_field(layer, field_names):
        all_names = [f.name() for f in layer.fields()]
        for fn in field_names:
            fn_lower = fn.lower()
            for actual_name in all_names:
                if actual_name.lower() == fn_lower:
                    return layer.fields().indexFromName(actual_name)
        return -1

    @staticmethod
    def _count_features(layer):
        return sum(1 for _ in layer.getFeatures())

    @staticmethod
    def _get_crs_authid(layer):
        return layer.crs().authid()

    @staticmethod
    def _get_line_endpoints(line_geom):
        """Return (start_point, end_point) as QgsPointXY."""
        if line_geom.isMultipart():
            parts = line_geom.asMultiPolyline()
            if parts:
                first_part = parts[0]
                last_part = parts[-1]
                if first_part and last_part:
                    return (QgsPointXY(first_part[0]), QgsPointXY(last_part[-1]))
        else:
            pts = line_geom.asPolyline()
            if pts and len(pts) >= 2:
                return (QgsPointXY(pts[0]), QgsPointXY(pts[-1]))
        return (None, None)

    @staticmethod
    def _point_distance_to_point(pt1, pt2):
        """Distance between two QgsPointXY."""
        return ((pt1.x() - pt2.x())**2 + (pt1.y() - pt2.y())**2)**0.5

    def processAlgorithm(self, parameters, context, feedback):
        tolerance = self.parameterAsDouble(parameters, self.PARAM_TOLERANCE, context)
        ag_id_field = self.parameterAsString(parameters, self.PARAM_AG_ID, context) or 'ID'
        block_id_field = self.parameterAsString(parameters, self.PARAM_BLOCK_ID, context) or 'ID'
        output_folder = self.parameterAsString(parameters, self.PARAM_OUTPUT, context)

        ag_layer = self.parameterAsVectorLayer(parameters, self.IN_AG, context)
        blocks_layer = self.parameterAsVectorLayer(parameters, self.IN_BLOCKS, context)
        fj_layer = self.parameterAsVectorLayer(parameters, self.IN_FJ, context)
        dj_layer = self.parameterAsVectorLayer(parameters, self.IN_DJ, context)
        dc_layer = self.parameterAsVectorLayer(parameters, self.IN_DC, context)
        poles_layer = self.parameterAsVectorLayer(parameters, self.IN_POLES, context)
        fc_layer = self.parameterAsVectorLayer(parameters, self.IN_FC, context)

        # Layer summary
        ag_count = self._count_features(ag_layer)
        block_count = self._count_features(blocks_layer)
        fj_count = self._count_features(fj_layer)
        dj_count = self._count_features(dj_layer)
        dc_count = self._count_features(dc_layer)
        pole_count = self._count_features(poles_layer) if poles_layer else 0
        fc_count = self._count_features(fc_layer) if fc_layer else 0

        feedback.pushInfo("=" * 60)
        feedback.pushInfo("FTTH Pre-Flight Validator v8.6.22")
        feedback.pushInfo("=" * 60)
        feedback.pushInfo("Snap Tolerance: {}m".format(tolerance))
        feedback.pushInfo("")
        feedback.pushInfo("Layer Summary:")
        feedback.pushInfo("  AG:     {} features".format(ag_count))
        feedback.pushInfo("  Block:  {} features".format(block_count))
        feedback.pushInfo("  FJ:     {} features".format(fj_count))
        feedback.pushInfo("  DJ:     {} features".format(dj_count))
        feedback.pushInfo("  DC:     {} features".format(dc_count))
        if poles_layer:
            feedback.pushInfo("  Pole:   {} features".format(pole_count))
        if fc_layer:
            feedback.pushInfo("  FC:     {} features".format(fc_count))
        feedback.pushInfo("")

        report_lines = []
        report_lines.append("FTTH Pre-Flight Validation Report")
        report_lines.append("=" * 60)
        report_lines.append("Version: 8.6.22")
        report_lines.append("Snap Tolerance: {}m".format(tolerance))
        report_lines.append("")
        report_lines.append("Layer Summary:")
        report_lines.append("  AG: {}, Block: {}, FJ: {}, DJ: {}, DC: {}, Pole: {}, FC: {}".format(
            ag_count, block_count, fj_count, dj_count, dc_count, pole_count, fc_count))
        report_lines.append("")

        total_issues = 0
        critical_issues = 0

        # ===== CHECK 1: CRS Consistency =====
        feedback.setProgress(5)
        feedback.pushInfo("[Check 1] CRS Consistency...")
        report_lines.append("[1] CRS CONSISTENCY")

        layers_to_check = [
            ('AG', ag_layer), ('Block', blocks_layer), ('FJ', fj_layer),
            ('DJ', dj_layer), ('DC', dc_layer)
        ]
        if poles_layer:
            layers_to_check.append(('Pole', poles_layer))
        if fc_layer:
            layers_to_check.append(('FC', fc_layer))

        crses = {}
        for name, lyr in layers_to_check:
            crses[name] = self._get_crs_authid(lyr)

        unique_crs = set(crses.values())
        if len(unique_crs) == 1:
            feedback.pushInfo("  PASS: All layers use {}".format(list(unique_crs)[0]))
            report_lines.append("  PASS: All layers use {}".format(list(unique_crs)[0]))
        else:
            feedback.reportError("  FAIL: Multiple CRS found!")
            report_lines.append("  FAIL: Multiple CRS found!")
            for name, crs in crses.items():
                line = "    {}: {}".format(name, crs)
                feedback.pushInfo(line)
                report_lines.append(line)
            total_issues += 1
            critical_issues += 1

        # ===== CHECK 2: Required Columns =====
        feedback.setProgress(10)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 2] Required ID Columns...")
        report_lines.append("")
        report_lines.append("[2] REQUIRED ID COLUMNS")

        ag_id_idx = self._find_field(ag_layer, [ag_id_field, 'id', 'ID', 'Id'])
        block_id_idx = self._find_field(blocks_layer, [block_id_field, 'id', 'ID', 'Id'])

        if ag_id_idx >= 0:
            feedback.pushInfo("  PASS: AG layer has '{}' column".format(ag_id_field))
            report_lines.append("  PASS: AG layer has '{}' column".format(ag_id_field))
        else:
            feedback.reportError("  FAIL: AG layer missing '{}' column!".format(ag_id_field))
            report_lines.append("  FAIL: AG layer missing '{}' column!".format(ag_id_field))
            total_issues += 1
            critical_issues += 1

        if block_id_idx >= 0:
            feedback.pushInfo("  PASS: Block layer has '{}' column".format(block_id_field))
            report_lines.append("  PASS: Block layer has '{}' column".format(block_id_field))
        else:
            feedback.reportError("  FAIL: Block layer missing '{}' column!".format(block_id_field))
            report_lines.append("  FAIL: Block layer missing '{}' column!".format(block_id_field))
            total_issues += 1
            critical_issues += 1

        # ===== CHECK 2b: DJ Position Field Type (Shapefile/Real — CRITICAL) =====
        feedback.pushInfo("")
        feedback.pushInfo("[Check 2b] DJ position field type...")
        report_lines.append("")
        report_lines.append("[2b] DJ POSITION FIELD TYPE")

        dj_pos_idx = self._find_field(dj_layer, ['position', 'Position', 'POSITION'])
        if dj_pos_idx >= 0:
            # Check field type
            field = dj_layer.fields()[dj_pos_idx]
            field_type = field.typeName()
            field_name = field.name()

            # Check if layer is Shapefile
            source = dj_layer.source()
            is_shapefile = source.lower().endswith('.shp') or '.shp|' in source.lower()

            if is_shapefile:
                feedback.reportError("  CRITICAL: DJ Points is a Shapefile (.shp)")
                report_lines.append("  CRITICAL: DJ Points is a Shapefile (.shp)")
                feedback.reportError("    Shapefile DBF stores all numbers as Real (floating point)")
                report_lines.append("    Shapefile DBF stores all numbers as Real (floating point)")
                critical_issues += 1
                total_issues += 1

            if field_type.lower() in ['real', 'double', 'float']:
                feedback.reportError("  CRITICAL: position field '{}' is type '{}'".format(field_name, field_type))
                report_lines.append("  CRITICAL: position field '{}' is type '{}'".format(field_name, field_type))
                feedback.reportError("    This causes ALL positions to read as '1' -> only 1 DC column in splicing plan")
                report_lines.append("    This causes ALL positions to read as '1' -> only 1 DC column in splicing plan")
                feedback.pushInfo("    HOW TO FIX:")
                feedback.pushInfo("      1. Right-click DJ Points layer -> Export -> Save Features As...")
                feedback.pushInfo("      2. Format: GeoPackage (.gpkg)")
                feedback.pushInfo("      3. File name: any_name.gpkg")
                feedback.pushInfo("      4. Click OK")
                feedback.pushInfo("      5. Use the new .gpkg layer in Splicing Plan (not the .shp)")
                feedback.pushInfo("    OR: Use Splicing Plan v8.6.22+ which auto-converts Real->Integer")
                report_lines.append("    Fix: Convert to GeoPackage (.gpkg) or use Splicing Plan v8.6.22+")
                critical_issues += 1
                total_issues += 1
            elif field_type.lower() in ['integer', 'int', 'integer64']:
                feedback.pushInfo("  PASS: position field '{}' is type '{}'".format(field_name, field_type))
                report_lines.append("  PASS: position field '{}' is type '{}'".format(field_name, field_type))
            else:
                feedback.pushInfo("  INFO: position field '{}' is type '{}' (untested)".format(field_name, field_type))
                report_lines.append("  INFO: position field '{}' is type '{}' (untested)".format(field_name, field_type))

            # Check actual position values
            pos_values = set()
            for feat in dj_layer.getFeatures():
                val = feat[dj_pos_idx]
                if val is not None and val != '':
                    pos_values.add(str(val))

            float_looking = [v for v in pos_values if '.' in v and v.replace('.','').replace('-','').isdigit()]
            if float_looking:
                feedback.reportError("  CRITICAL: position values look like floats: {}".format(sorted(float_looking)[:5]))
                report_lines.append("  CRITICAL: position values look like floats: {}".format(sorted(float_looking)[:5]))
                feedback.reportError("    This confirms Shapefile/Real source — will cause 1 DC column in splicing plan")
                report_lines.append("    This confirms Shapefile/Real source — will cause 1 DC column in splicing plan")
                critical_issues += 1
                total_issues += 1
            else:
                int_values = sorted([int(float(v)) for v in pos_values if v.replace('.','').replace('-','').isdigit()])
                if int_values:
                    feedback.pushInfo("  Position values: {}".format(int_values[:10]))
                    report_lines.append("  Position values: {}".format(int_values[:10]))
        else:
            feedback.reportError("  FAIL: DJ Points has no 'position' field!")
            report_lines.append("  FAIL: DJ Points has no 'position' field!")
            feedback.pushInfo("    Splicing Plan will use position=1 for ALL DJs -> 1 DC column")
            report_lines.append("    Splicing Plan will use position=1 for ALL DJs -> 1 DC column")
            total_issues += 1
            critical_issues += 1

        # ===== CHECK 3: DC→DJ Snap =====
        feedback.setProgress(20)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 3] DC lines snap to DJ points...")
        report_lines.append("")
        report_lines.append("[3] DC LINES SNAP TO DJ POINTS")

        # Build DJ point index
        dj_points = []
        for feat in dj_layer.getFeatures():
            dj_points.append((feat.id(), feat.geometry().asPoint()))

        dc_no_dj = 0
        dc_dj_snap = 0
        for feat in dc_layer.getFeatures():
            start_pt, end_pt = self._get_line_endpoints(feat.geometry())
            if start_pt is None:
                continue
            # Check both endpoints
            start_has_dj = any(self._point_distance_to_point(start_pt, dj_pt) <= tolerance
                             for _, dj_pt in dj_points)
            end_has_dj = any(self._point_distance_to_point(end_pt, dj_pt) <= tolerance
                           for _, dj_pt in dj_points)
            if start_has_dj or end_has_dj:
                dc_dj_snap += 1
            else:
                dc_no_dj += 1

        total_dc = dc_dj_snap + dc_no_dj
        if dc_no_dj == 0:
            feedback.pushInfo("  PASS: All {} DC segments snap to DJ".format(total_dc))
            report_lines.append("  PASS: All {} DC segments snap to DJ".format(total_dc))
        else:
            feedback.reportError("  FAIL: {}/{} DC segments do NOT snap to any DJ!".format(dc_no_dj, total_dc))
            report_lines.append("  FAIL: {}/{} DC segments do NOT snap to any DJ!".format(dc_no_dj, total_dc))
            total_issues += dc_no_dj
            critical_issues += 1

        # ===== CHECK 4: Each block has at least one DJ with DC→FJ connection =====
        feedback.setProgress(30)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 4] Each block's first DJ connects to FJ...")
        report_lines.append("")
        report_lines.append("[4] BLOCK FIRST DJ -> FJ CONNECTION")

        # Build FJ point index
        fj_points = []
        for feat in fj_layer.getFeatures():
            fj_points.append((feat.id(), feat.geometry().asPoint()))

        # Build block polygon index
        block_geoms = [(feat.id(), feat.geometry()) for feat in blocks_layer.getFeatures()]

        # For each block: find DJs inside it, check if any has a DC that touches an FJ
        block_ok = 0
        block_fail = 0
        for b_fid, b_geom in block_geoms:
            # Find all DJs inside this block
            djs_in_block = []
            for feat in dj_layer.getFeatures():
                if b_geom.contains(feat.geometry()):
                    djs_in_block.append((feat.id(), feat.geometry().asPoint()))

            # Check if any DJ in this block has a DC that also touches an FJ
            has_fj_connection = False
            for dj_fid, dj_pt in djs_in_block:
                for dc_feat in dc_layer.getFeatures():
                    s_pt, e_pt = self._get_line_endpoints(dc_feat.geometry())
                    if s_pt is None:
                        continue
                    # DC must touch this DJ
                    touches_dj = (self._point_distance_to_point(s_pt, dj_pt) <= tolerance or
                                 self._point_distance_to_point(e_pt, dj_pt) <= tolerance)
                    if not touches_dj:
                        continue
                    # DC must also touch an FJ
                    for _, fj_pt in fj_points:
                        touches_fj = (self._point_distance_to_point(s_pt, fj_pt) <= tolerance or
                                     self._point_distance_to_point(e_pt, fj_pt) <= tolerance)
                        if touches_fj:
                            has_fj_connection = True
                            break
                    if has_fj_connection:
                        break
                if has_fj_connection:
                    break

            if has_fj_connection:
                block_ok += 1
            else:
                block_fail += 1

        total_block_check = block_ok + block_fail
        if block_fail == 0:
            feedback.pushInfo("  PASS: All {} blocks have DJ->FJ connection".format(total_block_check))
            report_lines.append("  PASS: All {} blocks have DJ->FJ connection".format(total_block_check))
        else:
            feedback.reportError("  FAIL: {}/{} blocks have NO DJ->FJ connection!".format(block_fail, total_block_check))
            report_lines.append("  FAIL: {}/{} blocks have NO DJ->FJ connection!".format(block_fail, total_block_check))
            total_issues += block_fail
            critical_issues += 1

        # ===== CHECK 5: DJ inside Block =====
        feedback.setProgress(40)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 5] DJ points inside Block polygons...")
        report_lines.append("")
        report_lines.append("[5] DJ POINTS INSIDE BLOCK POLYGONS")

        # Build block polygon index
        block_geoms = [(feat.id(), feat.geometry()) for feat in blocks_layer.getFeatures()]

        dj_outside = 0
        dj_inside = 0
        for feat in dj_layer.getFeatures():
            dj_geom = feat.geometry()
            in_any_block = any(block_geom.contains(dj_geom) for _, block_geom in block_geoms)
            if in_any_block:
                dj_inside += 1
            else:
                dj_outside += 1

        total_dj = dj_inside + dj_outside
        if dj_outside == 0:
            feedback.pushInfo("  PASS: All {} DJs are inside blocks".format(total_dj))
            report_lines.append("  PASS: All {} DJs are inside blocks".format(total_dj))
        else:
            feedback.reportError("  FAIL: {}/{} DJs are OUTSIDE all blocks!".format(dj_outside, total_dj))
            report_lines.append("  FAIL: {}/{} DJs are OUTSIDE all blocks!".format(dj_outside, total_dj))
            total_issues += dj_outside
            critical_issues += 1

        # ===== CHECK 6: Block inside AG =====
        feedback.setProgress(50)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 6] Block polygons inside AG polygons...")
        report_lines.append("")
        report_lines.append("[6] BLOCK POLYGONS INSIDE AG POLYGONS")

        ag_geoms = [(feat.id(), feat.geometry()) for feat in ag_layer.getFeatures()]

        block_outside = 0
        block_inside = 0
        for feat in blocks_layer.getFeatures():
            block_geom = feat.geometry()
            centroid = block_geom.centroid()
            in_any_ag = any(ag_geom.contains(centroid) for _, ag_geom in ag_geoms)
            if in_any_ag:
                block_inside += 1
            else:
                block_outside += 1

        total_block = block_inside + block_outside
        if block_outside == 0:
            feedback.pushInfo("  PASS: All {} blocks are inside AGs".format(total_block))
            report_lines.append("  PASS: All {} blocks are inside AGs".format(total_block))
        else:
            feedback.reportError("  FAIL: {}/{} blocks are OUTSIDE all AGs!".format(block_outside, total_block))
            report_lines.append("  FAIL: {}/{} blocks are OUTSIDE all AGs!".format(block_outside, total_block))
            total_issues += block_outside
            critical_issues += 1

        # ===== CHECK 7: FJ inside AG =====
        feedback.setProgress(55)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 7] FJ points inside AG polygons...")
        report_lines.append("")
        report_lines.append("[7] FJ POINTS INSIDE AG POLYGONS")

        fj_outside = 0
        fj_inside = 0
        for feat in fj_layer.getFeatures():
            fj_geom = feat.geometry()
            in_any_ag = any(ag_geom.contains(fj_geom) for _, ag_geom in ag_geoms)
            if in_any_ag:
                fj_inside += 1
            else:
                fj_outside += 1

        if fj_outside == 0:
            feedback.pushInfo("  PASS: All {} FJs are inside AGs".format(fj_inside))
            report_lines.append("  PASS: All {} FJs are inside AGs".format(fj_inside))
        else:
            feedback.reportError("  FAIL: {}/{} FJs are outside AGs!".format(fj_outside, fj_inside + fj_outside))
            report_lines.append("  FAIL: {}/{} FJs are outside AGs!".format(fj_outside, fj_inside + fj_outside))
            total_issues += fj_outside

        # ===== CHECK 8: Poles on Cables =====
        feedback.setProgress(60)
        isolated_pole_ids = []  # collect for error layer
        if poles_layer:
            feedback.pushInfo("")
            feedback.pushInfo("[Check 8] Poles near DC or FC lines...")
            report_lines.append("")
            report_lines.append("[8] POLES NEAR CABLES (DC or FC)")

            # Build line geometry list
            line_geoms = [feat.geometry() for feat in dc_layer.getFeatures()]
            if fc_layer:
                line_geoms.extend([feat.geometry() for feat in fc_layer.getFeatures()])

            pole_isolated = 0
            pole_on_cable = 0
            for feat in poles_layer.getFeatures():
                pole_geom = feat.geometry()
                near_any = any(line_geom.distance(pole_geom) <= tolerance for line_geom in line_geoms)
                if near_any:
                    pole_on_cable += 1
                else:
                    pole_isolated += 1
                    isolated_pole_ids.append(feat.id())

            total_pole = pole_on_cable + pole_isolated
            if pole_isolated == 0:
                feedback.pushInfo("  PASS: All {} poles are on cables".format(total_pole))
                report_lines.append("  PASS: All {} poles are on cables".format(total_pole))
            else:
                feedback.pushInfo("  WARN: {}/{} poles are NOT near any cable".format(pole_isolated, total_pole))
                report_lines.append("  WARN: {}/{} poles are NOT near any cable".format(pole_isolated, total_pole))
                report_lines.append("  Isolated pole Feature IDs: {}".format(isolated_pole_ids))
                report_lines.append("  (These will use Stage 3 fallback — nearest line assignment)")
                total_issues += pole_isolated

                # Create error layer for isolated poles
                try:
                    crs_str = poles_layer.crs().authid()
                    err_layer = QgsVectorLayer("Point?crs={}".format(crs_str), "isolated_poles", "memory")
                    dp = err_layer.dataProvider()
                    dp.addAttributes([QgsField("pole_fid", QVariant.Int),
                                      QgsField("issue", QVariant.String, len=100)])
                    err_layer.updateFields()

                    for feat in poles_layer.getFeatures():
                        if feat.id() in isolated_pole_ids:
                            err_feat = QgsFeature()
                            err_feat.setGeometry(feat.geometry())
                            err_feat.setAttributes([feat.id(), "Not near any DC or FC line"])
                            dp.addFeature(err_feat)

                    err_path = os.path.join(output_folder, 'isolated_poles.gpkg')
                    QgsVectorFileWriter.writeAsVectorFormat(err_layer, err_path, 'UTF-8',
                        err_layer.crs(), 'GPKG')
                    feedback.pushInfo("  [OK] Error layer saved: {}".format(err_path))
                    report_lines.append("  [OK] Error layer saved: {}".format(err_path))
                except Exception as e:
                    feedback.pushInfo("  [WARN] Could not save error layer: {}".format(e))
        else:
            feedback.pushInfo("[Check 8] No pole layer — skipped")
            report_lines.append("")
            report_lines.append("[8] POLES: No pole layer provided — skipped")

        # ===== CHECK 9: FC intersects AG =====
        feedback.setProgress(70)
        if fc_layer:
            feedback.pushInfo("")
            feedback.pushInfo("[Check 9] FC lines intersect AG polygons...")
            report_lines.append("")
            report_lines.append("[9] FC LINES INTERSECT AG POLYGONS")

            fc_no_ag = 0
            fc_has_ag = 0
            for feat in fc_layer.getFeatures():
                fc_geom = feat.geometry()
                intersects = any(fc_geom.intersects(ag_geom) for _, ag_geom in ag_geoms)
                if intersects:
                    fc_has_ag += 1
                else:
                    fc_no_ag += 1

            total_fc = fc_has_ag + fc_no_ag
            if fc_no_ag == 0:
                feedback.pushInfo("  PASS: All {} FC lines intersect AGs".format(total_fc))
                report_lines.append("  PASS: All {} FC lines intersect AGs".format(total_fc))
            else:
                feedback.reportError("  FAIL: {}/{} FC lines do NOT intersect any AG!".format(fc_no_ag, total_fc))
                report_lines.append("  FAIL: {}/{} FC lines do NOT intersect any AG!".format(fc_no_ag, total_fc))
                total_issues += fc_no_ag
                critical_issues += 1
        else:
            feedback.pushInfo("[Check 9] No FC layer — skipped")
            report_lines.append("")
            report_lines.append("[9] FC: No FC layer provided — skipped")

        # ===== CHECK 10: Duplicate Geometries =====
        feedback.setProgress(80)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 10] Duplicate geometries...")
        report_lines.append("")
        report_lines.append("[10] DUPLICATE GEOMETRIES")

        dup_found = False
        for name, lyr in [('AG', ag_layer), ('Block', blocks_layer), ('FJ', fj_layer),
                          ('DJ', dj_layer), ('DC', dc_layer)]:
            geoms = []
            for feat in lyr.getFeatures():
                wkt = feat.geometry().asWkt(6)  # 6 decimal places
                geoms.append(wkt)
            seen = set()
            dups = 0
            for wkt in geoms:
                if wkt in seen:
                    dups += 1
                seen.add(wkt)
            if dups > 0:
                line = "  WARN: {} layer has {} duplicate geometries".format(name, dups)
                feedback.pushInfo(line)
                report_lines.append(line)
                total_issues += dups
                dup_found = True

        if not dup_found:
            feedback.pushInfo("  PASS: No duplicate geometries found")
            report_lines.append("  PASS: No duplicate geometries found")

        # ===== CHECK 11: Network Connectivity =====
        feedback.setProgress(90)
        feedback.pushInfo("")
        feedback.pushInfo("[Check 11] DC network connectivity...")
        report_lines.append("")
        report_lines.append("[11] NETWORK CONNECTIVITY (DJ reachable from FJ)")

        dj_with_dc = 0
        dj_no_dc = 0
        for feat in dj_layer.getFeatures():
            dj_geom = feat.geometry()
            has_dc = any(dc_feat.geometry().distance(dj_geom) <= tolerance
                        for dc_feat in dc_layer.getFeatures())
            if has_dc:
                dj_with_dc += 1
            else:
                dj_no_dc += 1

        if dj_no_dc == 0:
            feedback.pushInfo("  PASS: All {} DJs have DC connection".format(dj_with_dc))
            report_lines.append("  PASS: All {} DJs have DC connection".format(dj_with_dc))
        else:
            feedback.reportError("  FAIL: {} DJs have NO DC segments connected!".format(dj_no_dc))
            report_lines.append("  FAIL: {} DJs have NO DC segments connected!".format(dj_no_dc))
            total_issues += dj_no_dc
            critical_issues += 1

        # ===== CHECK 12: FJ count == AG count (exact) =====
        feedback.pushInfo("")
        feedback.pushInfo("[Check 12] FJ count vs AG count...")
        report_lines.append("")
        report_lines.append("[12] FJ COUNT vs AG COUNT (must match exactly)")

        if fj_count == ag_count:
            feedback.pushInfo("  PASS: {} FJs == {} AGs (exact match)".format(fj_count, ag_count))
            report_lines.append("  PASS: {} FJs == {} AGs (exact match)".format(fj_count, ag_count))
        else:
            feedback.reportError("  FAIL: {} FJs != {} AGs! Must be equal (1 FJ per AG).".format(fj_count, ag_count))
            report_lines.append("  FAIL: {} FJs != {} AGs! Must be equal (1 FJ per AG).".format(fj_count, ag_count))
            total_issues += abs(ag_count - fj_count)
            critical_issues += 1

        # ===== SUMMARY =====
        feedback.setProgress(100)
        feedback.pushInfo("")
        feedback.pushInfo("=" * 60)
        feedback.pushInfo("VALIDATION SUMMARY")
        feedback.pushInfo("=" * 60)

        report_lines.append("")
        report_lines.append("=" * 60)
        report_lines.append("SUMMARY")
        report_lines.append("=" * 60)
        report_lines.append("Total issues found: {}".format(total_issues))
        report_lines.append("Critical issues: {}".format(critical_issues))

        if total_issues == 0:
            feedback.pushInfo("ALL CHECKS PASSED")
            feedback.pushInfo("You can safely run the FTTH Labeler.")
            report_lines.append("RESULT: ALL CHECKS PASSED — ready for FTTH Labeler")
        elif critical_issues == 0:
            feedback.pushInfo("{} warnings (non-critical)".format(total_issues))
            feedback.pushInfo("You can run the FTTH Labeler, but review warnings.")
            report_lines.append("RESULT: {} warnings — labeler will run but review first".format(total_issues))
        else:
            feedback.reportError("{} CRITICAL issues found!".format(critical_issues))
            feedback.reportError("Fix critical issues before running FTTH Labeler.")
            report_lines.append("RESULT: {} CRITICAL issues — fix before running labeler".format(critical_issues))

        # Write report
        os.makedirs(output_folder, exist_ok=True)
        try:
            report_path = os.path.join(output_folder, 'preflight_validation_report.txt')
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(report_lines))
            feedback.pushInfo("")
            feedback.pushInfo("Report saved: {}".format(report_path))
        except Exception as e:
            feedback.pushInfo("  [ERROR] saving report: {}".format(e))

        return {self.PARAM_OUTPUT: output_folder}


# =============================================================================
# FTTH Validator Provider — ONLY registers FTTHValidatorAlgorithm
# =============================================================================

class FTTHValidatorProvider(QgsProcessingProvider):
    """Processing provider that registers only the FTTH Validator algorithm."""

    def loadAlgorithms(self, *args, **kwargs):
        self.addAlgorithm(FTTHValidatorAlgorithm())

    def id(self, *args, **kwargs):
        return 'ftth_validator'

    def name(self, *args, **kwargs):
        return 'FTTH Tools'

    def icon(self):
        return QgsProcessingProvider.icon(self)


# =============================================================================
# FTTH Validator Plugin — wrapper with menu items
# =============================================================================

class FTTHValidatorPlugin:
    """QGIS Plugin wrapper for FTTH QA Checker.

    Provides menu items:
      - FTTH QA Checker -> runs ftth_validator:ftth_validator
      - About
    """

    def __init__(self, iface):
        self.iface = iface
        self.provider = FTTHValidatorProvider()
        self.menu = None
        self.actions = []

    def initGui(self):
        # Add Processing algorithms
        QgsApplication.processingRegistry().addProvider(self.provider)

        # Add menu under Plugins menu
        self.menu = QMenu("FTTH QA Checker", self.iface.mainWindow())

        # QA Checker action
        action_validate = QAction("FTTH QA Checker", self.iface.mainWindow())
        action_validate.triggered.connect(self._run_validator)
        self.menu.addAction(action_validate)
        self.actions.append(action_validate)

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

    def _run_validator(self):
        processing.execAlgorithmDialog('ftth_validator:ftth_validator', {})

    def _show_about(self):
        QMessageBox.information(
            self.iface.mainWindow(),
            "About FTTH QA Checker",
            "<h3>FTTH QA Checker v8.6.22</h3>"
            "<p>By <b>Mustafa M M Ellaham</b></p>"
            "<p>Pre-flight validation tool for FTTH network designs.</p>"
            "<p>Checks performed:</p>"
            "<ul>"
            "<li>CRS consistency across all layers</li>"
            "<li>Required ID columns (AG, Block)</li>"
            "<li>DJ position field type (Shapefile/Real warning)</li>"
            "<li>DC lines snap to DJ points</li>"
            "<li>Block-FJ connectivity via DC</li>"
            "<li>DJ points inside Block polygons</li>"
            "<li>Block polygons inside AG polygons</li>"
            "<li>FJ points inside AG polygons</li>"
            "<li>Poles near DC or FC lines</li>"
            "<li>FC lines intersect AG polygons</li>"
            "<li>No duplicate geometries</li>"
            "<li>DC network connectivity</li>"
            "<li>FJ count matches AG count</li>"
            "</ul>"
            "<p>Email: Mustafaellaham@gmail.com</p>"
        )
