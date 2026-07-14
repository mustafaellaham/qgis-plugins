# -*- coding: utf-8 -*-
"""
Routed Drop Lines Generator v3.0 — Preserves Original DJ Connections

CRITICAL RULE: Each premise stays connected to its ORIGINAL DJ.
The existing drop line defines which DJ serves which premise.
We only reroute the path to pass through the closest intermediate pole.

Logic:
  1. Read existing drop lines to find which DJ each premise connects to
  2. Match each DJ to its nearest Pole (dj_pole = destination)
  3. Use DC cable layer to order poles along the cable route
  4. For each premise: find closest pole on DC cable (prev/current/next)
  5. Create one polyline: Premise → Closest Pole on DC → DJ Pole

Inputs:
  - Premises (points)
  - Distribution Joints (points/polygons) 
  - Poles (points)
  - Existing Drop Lines (lines) — defines premise→DJ connections
  - Distribution Cables (lines) — defines pole ordering

Author: Mustafa M M Ellaham
"""

from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingParameterVectorDestination, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsSpatialIndex, QgsFeatureRequest,
    QgsVectorFileWriter, QgsVectorLayer, QgsProcessingException
)
from qgis.PyQt.QtCore import QVariant


class RoutedDropsAlgorithm(QgsProcessingAlgorithm):

    PREMISE_LAYER = 'PREMISE_LAYER'
    PREMISE_NAME_FIELD = 'PREMISE_NAME_FIELD'
    DJ_LAYER = 'DJ_LAYER'
    DJ_NAME_FIELD = 'DJ_NAME_FIELD'
    POLE_LAYER = 'POLE_LAYER'
    POLE_NAME_FIELD = 'POLE_NAME_FIELD'
    DROP_LAYER = 'DROP_LAYER'           # NEW: Existing drop lines
    DC_LAYER = 'DC_LAYER'
    SEARCH_DISTANCE = 'SEARCH_DISTANCE'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def name(self): return 'routeddropgenerator'
    def displayName(self): return 'Routed Drop Lines Generator'
    def group(self): return 'FTTH Tools'
    def groupId(self): return 'ftth_tools'

    def shortHelpString(self):
        return """
        <h3>Routed Drop Lines Generator v3 — Preserves DJ Connections</h3>
        <p><b>CRITICAL:</b> Each premise stays connected to its ORIGINAL DJ.
        The plugin reads existing drop lines to know which DJ serves which premise.
        It only changes the path to pass through the closest pole on the DC cable.</p>
        
        <p><b>Inputs (5 layers):</b></p>
        <ol>
        <li><b>Premises</b> (points) — house locations</li>
        <li><b>Distribution Joints</b> (points) — DJ locations with names</li>
        <li><b>Poles</b> (points) — all poles with names</li>
        <li><b>Existing Drop Lines</b> (lines) — current premise→DJ connections (PRESERVED)</li>
        <li><b>Distribution Cables</b> (lines) — DC cable routes for pole ordering</li>
        </ol>
        """

    def createInstance(self): return RoutedDropsAlgorithm()

    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterVectorLayer(self.PREMISE_LAYER, '1. Premises Layer (Points)', [QgsProcessing.TypeVectorPoint], optional=False))
        self.addParameter(QgsProcessingParameterField(self.PREMISE_NAME_FIELD, 'Premise Name Field (optional)', parentLayerParameterName=self.PREMISE_LAYER, type=QgsProcessingParameterField.Any, optional=True, defaultValue=''))
        
        self.addParameter(QgsProcessingParameterVectorLayer(self.DJ_LAYER, '2. Distribution Joints Layer (Points)', [QgsProcessing.TypeVectorPoint], optional=False))
        self.addParameter(QgsProcessingParameterField(self.DJ_NAME_FIELD, 'DJ Name Field', parentLayerParameterName=self.DJ_LAYER, type=QgsProcessingParameterField.Any, optional=True, defaultValue=''))
        
        self.addParameter(QgsProcessingParameterVectorLayer(self.POLE_LAYER, '3. Poles Layer (Points)', [QgsProcessing.TypeVectorPoint], optional=False))
        self.addParameter(QgsProcessingParameterField(self.POLE_NAME_FIELD, 'Pole Name Field', parentLayerParameterName=self.POLE_LAYER, type=QgsProcessingParameterField.Any, optional=True, defaultValue=''))
        
        self.addParameter(QgsProcessingParameterVectorLayer(self.DROP_LAYER, '4. Existing Drop Lines (lines — defines premise→DJ connections)', [QgsProcessing.TypeVectorLine], optional=False))
        
        self.addParameter(QgsProcessingParameterVectorLayer(self.DC_LAYER, '5. Distribution Cable Lines (DC — for pole ordering)', [QgsProcessing.TypeVectorLine], optional=False))
        
        self.addParameter(QgsProcessingParameterNumber(self.SEARCH_DISTANCE, 'Search Distance (m)', type=QgsProcessingParameterNumber.Double, defaultValue=100.0, optional=True, minValue=1.0, maxValue=5000.0))
        self.addParameter(QgsProcessingParameterVectorDestination(self.OUTPUT_LAYER, 'Routed Drop Lines', QgsProcessing.TypeVectorLine))

    def _find_field(self, layer, field_names, param_value=None):
        if param_value:
            idx = layer.fields().lookupField(param_value)
            if idx >= 0: return idx
        for fname in field_names:
            idx = layer.fields().lookupField(fname)
            if idx >= 0: return idx
        return -1

    def _point_from_geom(self, geom):
        if geom.type() == 2:  # Polygon
            return geom.centroid().asPoint()
        return geom.asPoint()

    def _find_poles_on_dc(self, dc_geom, all_poles, search_dist=20.0):
        """Find all poles that lie on a DC cable line, ordered along the line."""
        poles_on_line = []
        for pole in all_poles:
            dist = dc_geom.distance(pole['geom'])
            if dist <= search_dist:
                proj_dist = dc_geom.lineLocatePoint(pole['geom'])
                poles_on_line.append({**pole, 'proj_dist': proj_dist})
        poles_on_line.sort(key=lambda x: x['proj_dist'])
        return poles_on_line

    def _find_closest_pole_on_dc(self, premise_geom, poles_on_dc):
        """Find closest pole among prev/current/next on DC cable."""
        if not poles_on_dc:
            return None

        # Find which pole index is closest to premise
        closest_idx = 0
        min_dist = float('inf')
        for i, pole in enumerate(poles_on_dc):
            d = premise_geom.distance(pole['geom'])
            if d < min_dist:
                min_dist = d
                closest_idx = i

        # Check previous, current, next
        candidates = [poles_on_dc[closest_idx]]
        if closest_idx > 0:
            candidates.append(poles_on_dc[closest_idx - 1])
        if closest_idx < len(poles_on_dc) - 1:
            candidates.append(poles_on_dc[closest_idx + 1])

        best = None
        best_dist = float('inf')
        for cand in candidates:
            d = premise_geom.distance(cand['geom'])
            if d < best_dist:
                best_dist = d
                best = cand
        return best

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushInfo("=" * 60)
        feedback.pushInfo("Routed Drop Lines Generator v3.0")
        feedback.pushInfo("RULE: Each premise keeps its ORIGINAL DJ connection")
        feedback.pushInfo("=" * 60)

        # ── Step 1: Read parameters ──
        feedback.pushInfo("Step 1: Reading 5 layers...")
        premise_layer = self.parameterAsVectorLayer(parameters, self.PREMISE_LAYER, context)
        dj_layer = self.parameterAsVectorLayer(parameters, self.DJ_LAYER, context)
        pole_layer = self.parameterAsVectorLayer(parameters, self.POLE_LAYER, context)
        drop_layer = self.parameterAsVectorLayer(parameters, self.DROP_LAYER, context)
        dc_layer = self.parameterAsVectorLayer(parameters, self.DC_LAYER, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT_LAYER, context)
        search_dist = self.parameterAsDouble(parameters, self.SEARCH_DISTANCE, context)

        if not all([premise_layer, dj_layer, pole_layer, drop_layer, dc_layer]):
            raise QgsProcessingException("All 5 layers are required!")

        feedback.pushInfo(f"  Premises: {premise_layer.name()} ({premise_layer.featureCount()})")
        feedback.pushInfo(f"  DJs: {dj_layer.name()} ({dj_layer.featureCount()})")
        feedback.pushInfo(f"  Poles: {pole_layer.name()} ({pole_layer.featureCount()})")
        feedback.pushInfo(f"  Existing Drops: {drop_layer.name()} ({drop_layer.featureCount()})")
        feedback.pushInfo(f"  DC Cables: {dc_layer.name()} ({dc_layer.featureCount()})")

        # ── Step 2: Find fields ──
        feedback.pushInfo("Step 2: Finding field names...")
        premise_name_idx = self._find_field(premise_layer, ['name', 'Name', 'house_id', 'ID'], self.parameterAsString(parameters, self.PREMISE_NAME_FIELD, context))
        dj_name_idx = self._find_field(dj_layer, ['name', 'Name', 'dj_name', 'label'], self.parameterAsString(parameters, self.DJ_NAME_FIELD, context))
        pole_name_idx = self._find_field(pole_layer, ['name', 'Name', 'pole_name', 'label'], self.parameterAsString(parameters, self.POLE_NAME_FIELD, context))

        # ── Step 3: Build spatial indexes ──
        feedback.pushInfo("Step 3: Building spatial indexes...")
        
        # Index premises
        premise_index = QgsSpatialIndex()
        premise_map = {}
        for feat in premise_layer.getFeatures():
            premise_index.addFeature(feat)
            premise_map[feat.id()] = {
                'fid': feat.id(),
                'geom': feat.geometry(),
                'point': feat.geometry().asPoint(),
                'name': str(feat[premise_name_idx]) if premise_name_idx >= 0 and feat[premise_name_idx] is not None else str(feat.id())
            }

        # Index DJs
        dj_index = QgsSpatialIndex()
        dj_map = {}
        for feat in dj_layer.getFeatures():
            dj_point = self._point_from_geom(feat.geometry())
            f = QgsFeature(feat.id())
            f.setGeometry(QgsGeometry.fromPointXY(dj_point))
            dj_index.addFeature(f)
            dj_map[feat.id()] = {
                'fid': feat.id(),
                'point': dj_point,
                'geom': feat.geometry(),
                'name': str(feat[dj_name_idx]) if dj_name_idx >= 0 and feat[dj_name_idx] is not None else str(feat.id())
            }

        # Index poles
        pole_index = QgsSpatialIndex()
        all_poles = []
        for feat in pole_layer.getFeatures():
            pole_index.addFeature(feat)
            p_name = str(feat[pole_name_idx]) if pole_name_idx >= 0 and feat[pole_name_idx] is not None else str(feat.id())
            pole_data = {'fid': feat.id(), 'name': p_name, 'point': feat.geometry().asPoint(), 'geom': feat.geometry()}
            all_poles.append(pole_data)
            
            # Also store by name for lookup
            pole_data['name_lookup'] = p_name

        # ── Step 4: Match DJs to poles (destination) ──
        feedback.pushInfo("Step 4: Matching DJs to poles...")
        dj_to_pole = {}
        for dj_fid, dj_data in dj_map.items():
            nearest_ids = pole_index.nearestNeighbor(dj_data['point'], 1, search_dist)
            if not nearest_ids:
                continue
            pole_feat = next(pole_layer.getFeatures(QgsFeatureRequest(nearest_ids[0])))
            pole_name = str(pole_feat[pole_name_idx]) if pole_name_idx >= 0 and pole_feat[pole_name_idx] is not None else str(nearest_ids[0])
            dj_to_pole[dj_fid] = {
                'dj_name': dj_data['name'],
                'pole_name': pole_name,
                'pole_point': pole_feat.geometry().asPoint(),
            }
        feedback.pushInfo(f"  Matched {len(dj_to_pole)} DJs to poles")

        # ── Step 5: CRITICAL — Read drop lines to find premise→DJ connections ──
        feedback.pushInfo("Step 5: Reading existing drop lines to preserve premise→DJ connections...")
        
        premise_to_dj = {}  # premise_fid -> dj_fid (ORIGINAL connection)
        missing_matches = 0

        for drop_feat in drop_layer.getFeatures():
            if feedback.isCanceled(): break
            
            drop_geom = drop_feat.geometry()
            
            # Get start (premise end) and end (DJ end) of the line
            if drop_geom.isMultipart():
                parts = drop_geom.asMultiPolyline()
                if not parts: continue
                vertices = parts[0]
            else:
                vertices = drop_geom.asPolyline()
            
            if len(vertices) < 2:
                continue
            
            # Start point = premise side, End point = DJ side
            start_point = vertices[0]   # Near premise
            end_point = vertices[-1]     # Near DJ
            
            # Find premise near start
            premise_ids = premise_index.nearestNeighbor(start_point, 1, search_dist)
            # Find DJ near end
            dj_ids = dj_index.nearestNeighbor(end_point, 1, search_dist)
            
            if premise_ids and dj_ids:
                premise_fid = premise_ids[0]
                dj_fid = dj_ids[0]
                
                # Store the original connection
                premise_to_dj[premise_fid] = dj_fid
            else:
                missing_matches += 1

        feedback.pushInfo(f"  Preserved {len(premise_to_dj)} premise→DJ connections from drop lines")
        if missing_matches > 0:
            feedback.pushWarning(f"  {missing_matches} drop lines could not be matched")

        # ── Step 6: Find poles along DC cables ──
        feedback.pushInfo("Step 6: Finding poles along DC cables...")
        dc_poles_map = {}
        dc_feat_map = {}
        dc_index = QgsSpatialIndex()
        
        for feat in dc_layer.getFeatures():
            dc_index.addFeature(feat)
            dc_feat_map[feat.id()] = feat
            poles = self._find_poles_on_dc(feat.geometry(), all_poles, search_dist=20.0)
            if poles:
                dc_poles_map[feat.id()] = poles
        feedback.pushInfo(f"  Found {len(dc_poles_map)} DC cables with poles")

        # ── Step 7: Create output ──
        feedback.pushInfo("Step 7: Creating output...")
        output_fields = [
            QgsField("premise_id", QVariant.Int),
            QgsField("premise_name", QVariant.String),
            QgsField("dj_name", QVariant.String),
            QgsField("dj_pole", QVariant.String),
            QgsField("via_pole", QVariant.String),
            QgsField("total_length_m", QVariant.Double),
            QgsField("seg1_to_via_m", QVariant.Double),
            QgsField("seg2_via_to_dj_m", QVariant.Double),
            QgsField("original_kept", QVariant.String),
        ]

        crs = premise_layer.crs()
        output_layer = QgsVectorLayer(f"LineString?crs={crs.authid()}", "routed_drops", "memory")
        output_layer.dataProvider().addAttributes(output_fields)
        output_layer.updateFields()

        # ── Step 8: Process each premise, preserving its ORIGINAL DJ ──
        feedback.pushInfo("Step 8: Routing premises (preserving original DJ connections)...")
        features_to_add = []
        processed = 0
        kept_original = 0
        fallback_nearest = 0

        for premise_fid, dj_fid in premise_to_dj.items():
            if feedback.isCanceled(): break

            premise_data = premise_map.get(premise_fid)
            dj_data = dj_to_pole.get(dj_fid)
            
            if premise_data is None or dj_data is None:
                continue

            premise_geom = premise_data['geom']
            premise_point = premise_data['point']
            premise_name = premise_data['name']
            dj_name = dj_data['dj_name']
            dj_pole_name = dj_data['pole_name']
            dj_pole_point = dj_data['pole_point']
            connection_source = "YES"  # Original connection preserved

            # Find DC cable near this premise
            nearest_dc_ids = dc_index.nearestNeighbor(premise_point, 5, search_dist * 2)

            best_via_pole = None
            best_via_name = dj_pole_name
            best_via_point = dj_pole_point

            for dc_id in nearest_dc_ids:
                poles_on_dc = dc_poles_map.get(dc_id)
                if not poles_on_dc:
                    continue
                
                # Check DJ pole is on this DC
                dj_pole_on_dc = any(p['name'] == dj_pole_name for p in poles_on_dc)
                if not dj_pole_on_dc:
                    continue

                # Find closest pole on DC (prev/current/next)
                via_pole = self._find_closest_pole_on_dc(premise_geom, poles_on_dc)
                if via_pole:
                    best_via_pole = via_pole
                    best_via_name = via_pole['name']
                    best_via_point = via_pole['point']
                    break

            if best_via_pole is None:
                # Fallback: direct to DJ pole
                polyline = QgsGeometry.fromPolylineXY([premise_point, dj_pole_point])
                seg1 = premise_geom.distance(QgsGeometry.fromPointXY(dj_pole_point))
                seg2 = 0.0
            else:
                # One polyline: Premise -> Via Pole -> DJ Pole
                polyline = QgsGeometry.fromPolylineXY([
                    premise_point, best_via_point, dj_pole_point
                ])
                seg1_geom = QgsGeometry.fromPolylineXY([premise_point, best_via_point])
                seg2_geom = QgsGeometry.fromPolylineXY([best_via_point, dj_pole_point])
                seg1 = seg1_geom.length()
                seg2 = seg2_geom.length()

            total_length = polyline.length()

            feat = QgsFeature()
            feat.setGeometry(polyline)
            feat.setAttributes([
                premise_fid, premise_name, dj_name, dj_pole_name,
                best_via_name, round(total_length, 2), round(seg1, 2), round(seg2, 2),
                connection_source
            ])
            features_to_add.append(feat)
            processed += 1
            kept_original += 1

            if processed % 100 == 0:
                feedback.setProgress(int(processed / len(premise_to_dj) * 100))

        # ── Save ──
        feedback.pushInfo("Step 9: Saving output...")
        output_layer.dataProvider().addFeatures(features_to_add)
        output_layer.updateExtents()
        
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = "routed_drops"
        QgsVectorFileWriter.writeAsVectorFormat(output_layer, output_path, options)

        feedback.pushInfo("=" * 60)
        feedback.pushInfo("COMPLETED!")
        feedback.pushInfo(f"  Premises routed: {processed}")
        feedback.pushInfo(f"  Original DJ connections PRESERVED: {kept_original}")
        feedback.pushInfo(f"  Total cable: {sum(f.attributes()[5] for f in features_to_add):.2f}m")
        feedback.pushInfo("=" * 60)

        return {self.OUTPUT_LAYER: output_path}
