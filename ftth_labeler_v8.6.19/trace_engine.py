# -*- coding: utf-8 -*-
"""
FTTH Geometric Tracing Engine v5.6
Copyright (c) Mustafa M M Ellaham. All rights reserved.

Proprietary and confidential. Unauthorized copying, distribution,
modification, reverse engineering, or use of this software, in whole
or in part, is strictly prohibited without express written permission
from Mustafa M M Ellaham.

Handles individual DC line segments (each connects exactly 2 nodes).
Direction-agnostic: checks both endpoints of each line.
Generates correct DJ/DC labels following Huawei pre-con splitter logic.

INPUT:
  - AG polygons: ID column with AG numbers (1, 2, 3...)
  - Block polygons: ID column with block numbers (1, 2, 3...)
  - FJ points: no strict table requirements
  - DJ points: no strict table requirements  
  - DC lines: individual segments, any direction

DJ Position-to-Ratio (Huawei Pre-Con box) — CORRECTED:
  ONLY physical position 4 in the Huawei box has a 1:8 splitter.
  Positions 1, 2, 3 ALWAYS have 1:9 (intermediate with bypass).
  
  N=1 DJ  → positions [4]            → ratios [1:8]              (MDU)
  N=2 DJs → positions [1, 2]         → ratios [1:9, 1:9]
  N=3 DJs → positions [1, 2, 3]      → ratios [1:9, 1:9, 1:9]
  N=4 DJs → positions [1, 2, 3, 4]   → ratios [1:9, 1:9, 1:9, 1:8]
"""

import re
from collections import OrderedDict, defaultdict


class DJPositionMapper:
    """Maps DJ chain index to physical position and splitter ratio."""
    
    # Huawei Pre-Con box: ONLY position 4 has 1:8 splitter
    # Positions 1, 2, 3 always have 1:9 (intermediate with bypass)
    # Position 4 always has 1:8 (terminal, no bypass)
    POSITION_MAP = {
        1: [(4, '1:8')],                          # MDU: only slot 4
        2: [(1, '1:9'), (2, '1:9')],              # slots 1, 2
        3: [(1, '1:9'), (2, '1:9'), (3, '1:9')],  # slots 1, 2, 3
        4: [(1, '1:9'), (2, '1:9'), (3, '1:9'), (4, '1:8')]  # all 4 slots
    }
    
    @staticmethod
    def get_positions(dj_count):
        """Get (position, ratio) list for N DJs."""
        n = min(dj_count, 4)
        return DJPositionMapper.POSITION_MAP.get(n, [])


class FTTHTraceEngine:
    """Geometric tracing engine for FTTH network labeling."""
    
    def __init__(self, area_code, zone):
        self.area_code = area_code  # Can be any length, e.g., "VTN_HHS_GGM"
        self.zone = zone.strip() if zone else ''  # e.g., "Z02" or empty
        self.global_dj_counter = 0
        self.global_pole_counter = 0
        self.global_fj_counter = 0
        self.global_lj_counter = 0
    
    def _az(self):
        """Area + Zone separator. Returns '{area}_{zone}_' or '{area}_' if zone is empty."""
        if self.zone:
            return f"{self.area_code}_{self.zone}"
        return self.area_code
    
    def _sz(self):
        """Short area + Zone separator. Returns '{short}_{zone}_' or '{short}_' if zone is empty."""
        if self.zone:
            return f"{self._short_area()}_{self.zone}"
        return self._short_area()
    
    def reset_counters(self):
        self.global_dj_counter = 0
        self.global_pole_counter = 0
        self.global_fj_counter = 0
        self.global_lj_counter = 0
    
    # ---- Name Generators ----
    
    def generate_ag_name(self, ag_id):
        """Full AG name: {AREA}_{ZONE}_AG01 or {AREA}_AG01 if no zone."""
        return f"{self._az()}_AG{int(ag_id):02d}"
    
    def generate_block_name(self, block_id):
        """Full Block name: {AREA}_{ZONE}_B001 or {AREA}_B001 if no zone."""
        return f"{self._az()}_B{int(block_id):03d}"
    
    def generate_fj_name(self, ag_short_name):
        """FJ name: {SHORT_AREA}_{ZONE}_FJ01_AG01 or {SHORT_AREA}_FJ01_AG01.
        Example: GMG_Z02_FJ01_AG01 or GMG_FJ01_AG01"""
        self.global_fj_counter += 1
        return f"{self._sz()}_FJ{self.global_fj_counter:02d}_{ag_short_name}"
    
    def generate_lj_name(self, ag_short_name):
        """Full LJ name: {AREA}_{ZONE}_LJ01_AG01 or {AREA}_LJ01_AG01."""
        self.global_lj_counter += 1
        return f"{self._az()}_LJ{self.global_lj_counter:02d}_{ag_short_name}"
    
    def _short_area(self):
        """Extract short area code from full area code.
        VTN_HHS_GGM -> GGM, TKG -> TKG"""
        parts = self.area_code.split('_')
        return parts[-1] if parts else self.area_code
    
    def generate_dj_name(self, ratio):
        """DJ name: {SHORT_AREA}_{ZONE}_DJ001_1:9
        Example: GGM_Z02_DJ001_1:9 or GGM_DJ001_1:9"""
        self.global_dj_counter += 1
        return f"{self._sz()}_DJ{self.global_dj_counter:03d}_{ratio}"
    
    def generate_dc_name(self, ag_short_name, block_id, cable_seq, 
                         slack_start=0, slack_end=10):
        """Full DC name with slack: {AREA}_{ZONE}_{AG}_DC... or {AREA}_{AG}_DC..."""
        return (f"{self._az()}_{ag_short_name}_"
                f"DC{int(block_id):03d}.{int(cable_seq)}_"
                f"1F_ADSS_G.657.A1({int(slack_start):04d}m-{int(slack_end):04d}m)")
    
    def generate_fc_name(self, ag_start_short, ag_end_short, fc_num=1,
                         cable_size='144F', route_length=0, fj_count=0,
                         fc_type='FC'):
        """Full FC name with slack: {AREA}_{ZONE}_{startAG}-{endAG}_{TYPE}{NN}_{SIZE}F...
        
        fc_type can be 'FC', 'LC', or 'CC0x'. For 'CC0x' the num is omitted.
        For 'FC'/'LC', per-type sequential numbering is used (FC01, FC02...).
        
        Example: VTN_HHS_GMG_Z02_AG01-AG16_FC01_144F_ADSS_G.657.A1(4251m-4411m)
                 VTN_HHS_GMG_Z02_AG01-AG03_LC01_12F_ADSS_G.657.A1(0370m-0399m)
                 VTN_HHS_GMG_Z02_AG01-AG23_CC0x_144F_ADSS_G.657.A1(5057m-5461m)
        
        Slack = 8% of route length (user requirement June 2026)."""
        slack = int(route_length * 0.08)
        end_length = route_length + slack
        if fc_type.upper() == 'CC0X':
            type_prefix = "CC0x"  # literal, no number
        else:
            type_prefix = f"{fc_type.upper()}{int(fc_num):02d}"
        return (f"{self._az()}_"
                f"{ag_start_short}-{ag_end_short}_"
                f"{type_prefix}_{cable_size}_"
                f"ADSS_G.657.A1({int(route_length):04d}m-{int(end_length):04d}m)")
    
    def generate_lc_name(self, ag_from_short, ag_to_short, lc_num=1):
        """Full LC name."""
        return (f"{self._az()}_"
                f"{ag_from_short}-{ag_to_short}_LC{int(lc_num):02d}_12F_ADSS_G.657.A")
    
    def generate_pole_name(self, height=None):
        """Pole name: {SHORT_AREA}_{ZONE}_P0001
        Example: GMG_Z02_P0001 or GMG_P0001"""
        self.global_pole_counter += 1
        base = f"{self._sz()}_P{self.global_pole_counter:04d}"
        if height:
            return f"{base}_{height}m"
        return base
    
    # ---- DC Segment Processing ----
    
    @staticmethod
    def get_line_endpoints(line_geom):
        """Get start and end points of a LineString. Works regardless of direction."""
        from qgis.core import QgsGeometry, QgsPointXY
        
        points = []
        if line_geom.isMultipart():
            for part in line_geom.constGet():
                for i in range(part.numPoints()):
                    points.append(QgsPointXY(part.pointN(i)))
        else:
            polyline = line_geom.constGet()
            if polyline:
                for i in range(polyline.numPoints()):
                    points.append(QgsPointXY(polyline.pointN(i)))
        
        if len(points) >= 2:
            return (QgsGeometry.fromPointXY(points[0]),
                    QgsGeometry.fromPointXY(points[-1]))
        return None, None
    
    @staticmethod
    def find_node_at_point(point_geom, node_features, tolerance=2.0):
        """Find which node (FJ or DJ) is at a given point."""
        for feat_id, feat, node_label in node_features:
            if point_geom.distance(feat.geometry()) < tolerance:
                return feat_id, node_label
        return None, None
    
    @staticmethod
    def build_network_graph(dc_features, upstream_nodes, downstream_nodes, tolerance=2.0):
        """Build undirected network graph from individual DC line segments."""
        graph = defaultdict(list)
        all_nodes = upstream_nodes + downstream_nodes
        
        for dc_feat_id, dc_feat in dc_features:
            line_geom = dc_feat.geometry()
            start_geom, end_geom = FTTHTraceEngine.get_line_endpoints(line_geom)
            
            if start_geom is None or end_geom is None:
                continue
            
            start_id, start_label = FTTHTraceEngine.find_node_at_point(
                start_geom, all_nodes, tolerance
            )
            end_id, end_label = FTTHTraceEngine.find_node_at_point(
                end_geom, all_nodes, tolerance
            )
            
            if start_label and end_label and start_label != end_label:
                graph[start_label].append((end_label, dc_feat_id, dc_feat))
                graph[end_label].append((start_label, dc_feat_id, dc_feat))
        
        return graph
    
    @staticmethod
    def traverse_from_fj(fj_label, network_graph):
        """Traverse network from FJ outward using BFS."""
        visited = set([fj_label])
        queue = [(fj_label, 0, None)]
        order = []
        
        while queue:
            current, dist, dc_id = queue.pop(0)
            
            if current != fj_label:
                order.append((current, dist, dc_id))
            
            for neighbor, dc_feat_id, dc_feat in network_graph.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    line_len = dc_feat.geometry().length()
                    queue.append((neighbor, dist + line_len, dc_feat_id))
        
        order.sort(key=lambda x: x[1])
        return order
    
    @staticmethod
    def find_dj_block(dj_geom, block_features, tolerance=0.1):
        """Find which block polygon contains a DJ point."""
        for feat_id, feat, block_id, block_name, ag_name in block_features:
            if feat.geometry().contains(dj_geom):
                return block_id, block_name, ag_name
        # Fallback: nearest block centroid
        min_dist = float('inf')
        nearest = (None, None, None)
        for feat_id, feat, block_id, block_name, ag_name in block_features:
            d = feat.geometry().centroid().distance(dj_geom)
            if d < min_dist:
                min_dist = d
                nearest = (block_id, block_name, ag_name)
        return nearest
    
    # ---- Full Labeling Run ----
    
    @staticmethod
    def _ag_sort_key(ag_name):
        """Extract numeric AG ID for reliable numeric sorting.
        
        Handles: 'AG01'->1, 'AG1'->1, 'AG20'->20, 'MGMZ1_AG01'->1, etc.
        Falls back to string sorting if no number found.
        """
        if ag_name:
            m = re.search(r'AG(\d+)', str(ag_name), re.IGNORECASE)
            if m:
                return int(m.group(1))
        return ag_name or ''
    
    @staticmethod
    def _block_sort_key(block_item):
        """Extract numeric block ID for reliable numeric sorting.
        
        block_item is (key, group_dict). Sorts by group['block_id'].
        Handles both integer and string block IDs.
        """
        _, group = block_item
        block_id = group.get('block_id', 0)
        try:
            return int(block_id)
        except (ValueError, TypeError):
            return str(block_id)
    
    def run_full_labeling(self, ag_data, block_data, fj_data, dj_data, dc_data, poles_data=None, debug_log=None):
        """
        Run complete labeling — BLOCK-ID-DRIVEN DJ numbering.
        
        Each DJ is numbered exactly once, in AG order -> Block ID order.
        Multiple FJs per AG are handled correctly — DJs are NOT re-counted.
        
        :param ag_data: List of (feat_id, feat, ag_num)
        :param block_data: List of (feat_id, feat, block_num, block_name, ag_short_name)
        :param fj_data: List of (feat_id, feat, ag_short_name) 
        :param dj_data: List of (feat_id, feat)
        :param dc_data: List of (feat_id, feat)
        :param poles_data: Optional list of (feat_id, feat)
        :param debug_log: Optional callable for debug messages
        :returns: Complete labeling results
        """
        self.reset_counters()
        
        def _log(msg):
            if debug_log:
                debug_log(msg)
        
        _log(f"[TraceEngine] === BLOCK-ID-DRIVEN LABELING v8.6.8 ===")
        _log(f"[TraceEngine] Input: {len(dj_data)} DJs, {len(fj_data)} FJs, "
             f"{len(block_data)} Blocks, {len(dc_data)} DC segments")
        
        # ===== PHASE 1: Build network graph =====
        sorted_fj = sorted(fj_data, key=self._ag_sort_key)
        
        fj_nodes = []
        for feat_id, feat, ag_name in sorted_fj:
            fj_nodes.append((feat_id, feat, f"FJ_{ag_name}"))
        
        dj_nodes = []
        for feat_id, feat in dj_data:
            dj_nodes.append((feat_id, feat, f"DJ_{feat_id}"))
        
        network_graph = self.build_network_graph(dc_data, fj_nodes, dj_nodes)
        
        # ===== PHASE 2: Pre-compute DJ-to-Block mapping =====
        # Determine which block each DJ belongs to (point-in-polygon)
        _log(f"[TraceEngine] Mapping {len(dj_data)} DJs to blocks...")
        dj_block_map = {}  # dj_feat_id -> (block_id, block_name, ag_name)
        unmapped_djs = 0
        
        for feat_id, feat in dj_data:
            block_id, block_name, dj_ag = self.find_dj_block(
                feat.geometry(), block_data
            )
            if block_id is not None:
                dj_block_map[feat_id] = (block_id, block_name, dj_ag)
            else:
                unmapped_djs += 1
        
        _log(f"[TraceEngine]   {len(dj_block_map)} DJs mapped to blocks, "
             f"{unmapped_djs} unmapped")
        
        # ===== PHASE 3: Trace from ALL FJs to collect DJ connectivity =====
        # For each DJ, store the tracing info (dist, dc_feat_id, fj_label)
        # A DJ may be reachable from multiple FJs — we pick the closest one
        dj_trace_info = {}  # dj_feat_id -> {'dist': X, 'dc_feat_id': Y, 'fj_label': Z}
        
        for feat_id, feat, ag_name in sorted_fj:
            fj_label = f"FJ_{ag_name}"
            ordered_nodes = self.traverse_from_fj(fj_label, network_graph)
            
            for node_label, dist, dc_feat_id in ordered_nodes:
                if not node_label.startswith("DJ_"):
                    continue
                dj_feat_id = int(node_label.replace("DJ_", ""))
                # Only keep the SHORTEST path to this DJ
                if dj_feat_id not in dj_trace_info or dist < dj_trace_info[dj_feat_id]['dist']:
                    dj_trace_info[dj_feat_id] = {
                        'dist': dist,
                        'dc_feat_id': dc_feat_id,
                        'fj_label': fj_label,
                        'ag_name': ag_name
                    }
        
        _log(f"[TraceEngine] Traced paths to {len(dj_trace_info)} unique DJs from {len(sorted_fj)} FJs")
        
        # ===== PHASE 4: Group DJs by (AG, Block) and process in BLOCK ID order =====
        # This ensures DJ numbering follows: AG01/B001, AG01/B002, ... AG02/B001, etc.
        from collections import defaultdict
        ag_block_djs = defaultdict(lambda: defaultdict(list))
        
        for dj_feat_id, (block_id, block_name, dj_ag) in dj_block_map.items():
            if dj_feat_id not in dj_trace_info:
                continue  # DJ not reachable from any FJ
            trace = dj_trace_info[dj_feat_id]
            ag_block_djs[dj_ag][block_id].append({
                'feat_id': dj_feat_id,
                'block_name': block_name,
                'dist': trace['dist'],
                'dc_feat_id': trace['dc_feat_id'],
                'fj_label': trace['fj_label'],
            })
        
        # ===== PHASE 5: Generate labels in BLOCK ID order =====
        results = {
            'overview': f"{self.area_code}_{self.zone}" if self.zone else self.area_code,
            'ags': OrderedDict(),
            'summary': {'total_ags': 0, 'total_blocks': 0, 'total_djs': 0, 'total_dc': 0, 'total_poles': 0}
        }
        
        # Pre-build FJ name map — ONE NAME PER AG (1 FJ per AG = fixed rule)
        fj_name_map = {}  # ag_name -> fj_display_name
        temp_engine = FTTHTraceEngine(self.area_code, self.zone)
        temp_engine.global_fj_counter = 0
        for _, _, ag_name in sorted_fj:
            if ag_name not in fj_name_map:
                temp_engine.global_fj_counter += 1
                fj_name_map[ag_name] = f"{temp_engine._sz()}_FJ{temp_engine.global_fj_counter:02d}_{ag_name}"
        
        # Track which DJs have been labeled (safety check)
        labeled_dj_ids = set()
        
        # Process each AG in numeric order
        for ag_name in sorted(ag_block_djs.keys(), key=self._ag_sort_key):
            blocks = ag_block_djs[ag_name]
            fj_display_name = fj_name_map.get(ag_name, f"FJ_{ag_name}")
            
            fj_result = {
                'fj_name': fj_display_name,
                'ag_name': ag_name,
                'block_chains': []
            }
            
            ag_dj_start = self.global_dj_counter + 1
            
            # Process each Block in numeric ID order
            for block_id in sorted(blocks.keys()):
                djs = blocks[block_id]
                block_name = djs[0]['block_name']
                
                # Sort DJs within block by distance from FJ for consistent ordering
                djs.sort(key=lambda x: x['dist'])
                
                # Filter out already-labeled DJs (safety — should not happen)
                unique_djs = []
                for d in djs:
                    if d['feat_id'] not in labeled_dj_ids:
                        labeled_dj_ids.add(d['feat_id'])
                        unique_djs.append(d)
                
                if not unique_djs:
                    continue
                
                dj_count = len(unique_djs)
                positions = DJPositionMapper.get_positions(dj_count)
                
                chain_result = {
                    'block_name': block_name,
                    'block_id': block_id,
                    'ag_name': ag_name,
                    'dj_count': dj_count,
                    'djs': [],
                    'dc_cables': []
                }
                
                prev_dist = 0
                for i, (dj_info, (position, ratio)) in enumerate(zip(unique_djs, positions)):
                    dj_name = self.generate_dj_name(ratio)
                    cable_seq = i + 1
                    
                    curr_dist = dj_info['dist']
                    seg_length = curr_dist - prev_dist
                    slack_start = seg_length
                    slack_end = seg_length + 10
                    
                    dc_name = self.generate_dc_name(
                        ag_name, block_id, cable_seq,
                        slack_start, slack_end
                    )
                    
                    chain_result['djs'].append({
                        'feat_id': dj_info['feat_id'],
                        'dj_name': dj_name,
                        'position': position,
                        'ratio': ratio,
                        'dc_name': dc_name,
                        'dist_from_fj': curr_dist
                    })
                    
                    if i == 0:
                        from_node = fj_display_name
                    else:
                        from_node = chain_result['djs'][i-1]['dj_name']
                    
                    chain_result['dc_cables'].append({
                        'dc_name': dc_name,
                        'from_node': from_node,
                        'to_node': dj_name,
                        'cable_seq': cable_seq,
                        'block_id': block_id,
                        'dc_feat_id': dj_info['dc_feat_id'],
                        'seg_length': seg_length,
                        'slack_start': slack_start,
                        'slack_end': slack_end
                    })
                    
                    prev_dist = curr_dist
                
                fj_result['block_chains'].append(chain_result)
                results['summary']['total_djs'] += dj_count
                results['summary']['total_dc'] += len(chain_result['dc_cables'])
            
            ag_dj_end = self.global_dj_counter
            num_djs = ag_dj_end - ag_dj_start + 1 if ag_dj_end >= ag_dj_start else 0
            _log(f"[TraceEngine] AG {ag_name}: DJs {ag_dj_start:03d}-{ag_dj_end:03d} "
                 f"({num_djs} DJs, {len(fj_result['block_chains'])} blocks)")
            
            if fj_result['block_chains']:
                results['ags'][ag_name] = fj_result
                results['summary']['total_ags'] += 1
        
        # Pole names
        if poles_data:
            results['poles'] = []
            for feat_id, feat in poles_data:
                p_name = self.generate_pole_name()
                results['poles'].append({'feat_id': feat_id, 'name': p_name})
            results['summary']['total_poles'] = len(results['poles'])
        
        results['summary']['total_blocks'] = len(block_data)
        
        _log(f"[TraceEngine] === LABELING COMPLETE ===")
        _log(f"[TraceEngine] Total DJs labeled: {results['summary']['total_djs']} "
             f"(input: {len(dj_data)}, counter: {self.global_dj_counter:03d})")
        if results['summary']['total_djs'] != len(dj_data):
            _log(f"[TraceEngine] WARNING: Labeled DJs ({results['summary']['total_djs']}) != "
                 f"input DJs ({len(dj_data)})")
        if self.global_dj_counter != results['summary']['total_djs']:
            _log(f"[TraceEngine] WARNING: Counter ({self.global_dj_counter}) != "
                 f"labeled DJs ({results['summary']['total_djs']})")
        
        return results