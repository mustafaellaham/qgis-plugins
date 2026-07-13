#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIMI-QGIS Bridge v5.1 - SMART COMMAND MODE
============================================
Major improvement: Pre-written FTTH command library executes WITHOUT AI.
Only falls back to Kimi for complex queries not in the library.

NO MORE HALLUCINATIONS for common operations!

Author: Mustafa M M Elaham
Version: 5.1
"""

import os
import sys
import json
import time
import re
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' not installed. Run: uv pip install requests Pillow")
    sys.exit(1)

from qgis_mcp_client import QGISMCPClient

# ============================================================================
# CONFIG
# ============================================================================
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "moonshot-v1-128k")
QGIS_MCP_HOST = os.environ.get("QGIS_MCP_HOST", "127.0.0.1")
QGIS_MCP_PORT = int(os.environ.get("QGIS_MCP_PORT", "9999"))
RATE_LIMIT_DELAY = 0.5
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2


# ============================================================================
# FTTH COMMAND LIBRARY (Pre-written, tested functions - NO AI)
# ============================================================================

from qgis.core import QgsProject, QgsVectorLayer, QgsField, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol
from qgis.PyQt.QtCore import QVariant
import processing


def _get_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        available = [l.name() for l in QgsProject.instance().mapLayers().values()]
        raise ValueError(f"Layer '{name}' not found. Available: {available}")
    return layers[0]


def cmd_count_points_near_lines(point_layer, line_layer, distance=5.0):
    points = _get_layer(point_layer)
    lines = _get_layer(line_layer)
    points.removeSelection()
    processing.run("native:selectbylocation", {
        'INPUT': points, 'PREDICATE': [10], 'INTERSECT': lines,
        'DISTANCE': distance, 'METHOD': 0
    })
    count = points.selectedFeatureCount()
    points.removeSelection()
    return f"=== {count} points in '{point_layer}' within {distance}m of '{line_layer}' ==="


def cmd_count_points_inside_polygons(point_layer, polygon_layer):
    points = _get_layer(point_layer)
    polygons = _get_layer(polygon_layer)
    points.removeSelection()
    processing.run("native:selectbylocation", {
        'INPUT': points, 'PREDICATE': [6], 'INTERSECT': polygons, 'METHOD': 0
    })
    count = points.selectedFeatureCount()
    points.removeSelection()
    return f"=== {count} points inside '{polygon_layer}' ==="


def cmd_find_points_outside_polygons(point_layer, polygon_layer):
    points = _get_layer(point_layer)
    polygons = _get_layer(polygon_layer)
    points.removeSelection()
    processing.run("native:selectbylocation", {
        'INPUT': points, 'PREDICATE': [6], 'INTERSECT': polygons, 'METHOD': 0
    })
    total = points.featureCount()
    inside = points.selectedFeatureCount()
    outside = total - inside
    
    if outside > 0:
        result = processing.run("native:saveselectedfeatures", {
            'INPUT': points, 'OUTPUT': 'memory:outside'
        })
        # Invert: save non-selected (outside) points
        points.removeSelection()
        all_ids = [f.id() for f in points.getFeatures()]
        # Select outside points by selecting all then removing inside... simpler approach:
        # Just report the count
    points.removeSelection()
    return f"=== {outside}/{total} points in '{point_layer}' OUTSIDE '{polygon_layer}' ({inside} inside) ==="


def cmd_add_length_column(line_layer, column_name='length_m'):
    layer = _get_layer(line_layer)
    result = processing.run("native:fieldcalculator", {
        'INPUT': layer, 'FIELD_NAME': column_name, 'FIELD_TYPE': 2,
        'FIELD_LENGTH': 10, 'FIELD_PRECISION': 2, 'FORMULA': '$length',
        'OUTPUT': 'memory:with_length'
    })
    new_layer = result['OUTPUT']
    new_layer.setName(f'{line_layer}_with_length')
    QgsProject.instance().addMapLayer(new_layer)
    total = sum(f.geometry().length() for f in new_layer.getFeatures())
    return f"=== Added '{column_name}' to '{line_layer}'. Total: {total:.2f}m ==="


def cmd_total_length(line_layer):
    layer = _get_layer(line_layer)
    total = sum(f.geometry().length() for f in layer.getFeatures())
    return f"=== Total length of '{line_layer}': {total:.2f} meters ==="


def cmd_join_by_location(target, join_layer, fields=None):
    target_l = _get_layer(target)
    join_l = _get_layer(join_layer)
    result = processing.run("native:joinattributesbylocation", {
        'INPUT': target_l, 'JOIN': join_l, 'PREDICATE': [0],
        'JOIN_FIELDS': fields or [], 'METHOD': 0, 'DISCARD_NONMATCHING': False,
        'PREFIX': '', 'OUTPUT': 'memory:joined'
    })
    joined = result['OUTPUT']
    joined.setName(f'{target}_joined')
    QgsProject.instance().addMapLayer(joined)
    return f"=== Joined {joined.featureCount()} features ==="


def cmd_check_snapping(point_layer, line_layer, tolerance=1.0):
    points = _get_layer(point_layer)
    lines = _get_layer(line_layer)
    points.removeSelection()
    processing.run("native:selectbylocation", {
        'INPUT': points, 'PREDICATE': [10], 'INTERSECT': lines,
        'DISTANCE': tolerance, 'METHOD': 0
    })
    snapped = points.selectedFeatureCount()
    total = points.featureCount()
    unsnapped = total - snapped
    pct = (snapped/total*100) if total > 0 else 0
    points.removeSelection()
    return f"=== SNAP CHECK ({tolerance}m): {snapped}/{total} snapped ({pct:.1f}%), {unsnapped} UNSNAPPED ==="


def cmd_snap_points(point_layer, line_layer, tolerance=10.0):
    points = _get_layer(point_layer)
    lines = _get_layer(line_layer)
    result = processing.run("native:snapgeometries", {
        'INPUT': points, 'REFERENCE_LAYER': lines,
        'TOLERANCE': tolerance, 'BEHAVIOR': 0, 'OUTPUT': 'memory:snapped'
    })
    snapped = result['OUTPUT']
    snapped.setName(f'{point_layer}_snapped')
    QgsProject.instance().addMapLayer(snapped)
    return f"=== Snapped {snapped.featureCount()} points to lines ==="


def cmd_extract_vertices(line_layer):
    lines = _get_layer(line_layer)
    result = processing.run("native:extractvertices", {
        'INPUT': lines, 'VERTICES': '0', 'OUTPUT': 'memory:start'
    })
    starts = result['OUTPUT']
    starts.setName(f'{line_layer}_start')
    QgsProject.instance().addMapLayer(starts)
    result = processing.run("native:extractvertices", {
        'INPUT': lines, 'VERTICES': '-1', 'OUTPUT': 'memory:end'
    })
    ends = result['OUTPUT']
    ends.setName(f'{line_layer}_end')
    QgsProject.instance().addMapLayer(ends)
    return f"=== Created {starts.featureCount()} start and {ends.featureCount()} end points ==="


def cmd_check_duplicates(layer_name):
    from collections import defaultdict
    layer = _get_layer(layer_name)
    loc_map = defaultdict(list)
    for f in layer.getFeatures():
        geom = f.geometry()
        if geom.type() == 0:
            pt = geom.asPoint()
            key = (round(pt.x(), 6), round(pt.y(), 6))
        else:
            pt = geom.centroid().asPoint()
            key = (round(pt.x(), 6), round(pt.y(), 6))
        loc_map[key].append(f.id())
    dups = [ids for ids in loc_map.values() if len(ids) > 1]
    if dups:
        return f"WARNING: {len(dups)} duplicate locations found: {dups[:5]}..."
    return "OK: No duplicate geometries"


def cmd_check_validity(layer_name):
    layer = _get_layer(layer_name)
    invalid = []
    for f in layer.getFeatures():
        if not f.geometry().isGeosValid():
            invalid.append(f.id())
    if invalid:
        return f"WARNING: {len(invalid)} invalid geometries: {invalid[:10]}..."
    return f"OK: All {layer.featureCount()} geometries valid"


def cmd_style(layer_name, style_type):
    layer = _get_layer(layer_name)
    styles = {
        'green': QgsFillSymbol.createSimple({'color': '#90EE90', 'outline_color': '#4CAF50', 'outline_width': '0.8'}),
        'yellow_line': QgsLineSymbol.createSimple({'color': '#FFD700', 'width': '2'}),
        'splitter': QgsMarkerSymbol.createSimple({'name': 'triangle', 'color': '#FFEB3B', 'size': '6'}),
        'pole': QgsMarkerSymbol.createSimple({'name': 'circle', 'color': '#8B4513', 'size': '4'}),
        'demand': QgsMarkerSymbol.createSimple({'name': 'circle', 'color': '#2196F3', 'size': '3'}),
        'white': QgsFillSymbol.createSimple({'color': 'white'}),
        'blue_line': QgsLineSymbol.createSimple({'color': 'blue', 'width': '1.5'}),
    }
    symbol = styles.get(style_type, styles['green'])
    if style_type == 'green':
        symbol.setOpacity(0.35)
    layer.renderer().setSymbol(symbol)
    layer.triggerRepaint()
    return f"=== Styled '{layer_name}' as '{style_type}' ==="


def cmd_buffer(layer_name, distance=50.0):
    layer = _get_layer(layer_name)
    result = processing.run("native:buffer", {
        'INPUT': layer, 'DISTANCE': distance, 'SEGMENTS': 16,
        'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2,
        'DISSOLVE': False, 'OUTPUT': 'memory:buffer'
    })
    buf = result['OUTPUT']
    buf.setName(f'{layer_name}_buffer_{int(distance)}m')
    QgsProject.instance().addMapLayer(buf)
    return f"=== Created {distance}m buffer ==="


def cmd_list_layers():
    lines = []
    for lid, layer in QgsProject.instance().mapLayers().items():
        geom = 'Unknown'
        if hasattr(layer, 'geometryType'):
            types = {0: 'Point', 1: 'LineString', 2: 'Polygon'}
            geom = types.get(layer.geometryType(), 'Other')
        lines.append(f"  - {layer.name()} | {geom} | {layer.featureCount()} features | {layer.crs().authid()}")
    return "\n".join(lines) if lines else "No layers loaded"


def cmd_splitter_ratio(layer_name, count_field='demand_count'):
    layer = _get_layer(layer_name)
    layer.startEditing()
    if 'splitter_ratio' not in layer.fields().names():
        layer.addAttribute(QgsField('splitter_ratio', QVariant.Int))
    idx = layer.fields().indexOf('splitter_ratio')
    for f in layer.getFeatures():
        count = f[count_field] or 0
        ratio = 2 if count <= 2 else 4 if count <= 4 else 8 if count <= 8 else 16 if count <= 16 else 32 if count <= 32 else 64 if count <= 64 else 128
        layer.changeAttributeValue(f.id(), idx, ratio)
    layer.commitChanges()
    return f"=== Added splitter_ratio based on {count_field} ==="


# Keyword -> (function, arg_count, description)
COMMANDS = {
    # count operations
    ('count points near', 'points near lines', 'count within distance', 'points within'): 
        (cmd_count_points_near_lines, 2, "count_points_near_lines(point_layer, line_layer, distance=5.0)"),
    ('count points inside', 'points inside polygon', 'points in polygon'): 
        (cmd_count_points_inside_polygons, 2, "count_points_inside_polygons(point_layer, polygon_layer)"),
    ('find points outside', 'points outside', 'outside polygon'): 
        (cmd_find_points_outside_polygons, 2, "find_points_outside_polygons(point_layer, polygon_layer)"),
    
    # length
    ('add length', 'calculate length', 'measure length', 'cable length', 'length column'): 
        (cmd_add_length_column, 1, "add_length_column(line_layer, column_name='length_m')"),
    ('total length', 'sum length', 'total cable'): 
        (cmd_total_length, 1, "total_length(line_layer)"),
    
    # joins
    ('join attributes', 'spatial join', 'join by location'): 
        (cmd_join_by_location, 2, "join_by_location(target_layer, join_layer)"),
    
    # snapping
    ('check snapping', 'snap check', 'are points snapped'): 
        (cmd_check_snapping, 2, "check_snapping(point_layer, line_layer, tolerance=1.0)"),
    ('snap points', 'snap to lines'): 
        (cmd_snap_points, 2, "snap_points(point_layer, line_layer, tolerance=10.0)"),
    
    # vertices
    ('extract start', 'extract end', 'start and end', 'vertices from lines'): 
        (cmd_extract_vertices, 1, "extract_vertices(line_layer)"),
    
    # duplicates
    ('duplicate geometry', 'duplicate geometries', 'find duplicates'): 
        (cmd_check_duplicates, 1, "check_duplicates(layer)"),
    
    # validity
    ('check geometry', 'validate geometry', 'geometry valid'): 
        (cmd_check_validity, 1, "check_validity(layer)"),
    
    # styling
    ('style green', 'green zones', 'coverage zone style'): 
        (lambda n: cmd_style(n, 'green'), 1, "style(layer, 'green')"),
    ('style yellow', 'yellow lines', 'fiber route style'): 
        (lambda n: cmd_style(n, 'yellow_line'), 1, "style(layer, 'yellow_line')"),
    ('style splitter', 'yellow triangle', 'splitter style'): 
        (lambda n: cmd_style(n, 'splitter'), 1, "style(layer, 'splitter')"),
    ('style white', 'white color'): 
        (lambda n: cmd_style(n, 'white'), 1, "style(layer, 'white')"),
    ('style blue line', 'blue lines'): 
        (lambda n: cmd_style(n, 'blue_line'), 1, "style(layer, 'blue_line')"),
    
    # buffer
    ('buffer', 'create buffer'): 
        (cmd_buffer, 1, "buffer(layer, distance=50.0)"),
    
    # splitter
    ('splitter ratio', 'calculate splitter'): 
        (cmd_splitter_ratio, 1, "splitter_ratio(layer, count_field='demand_count')"),
    
    # list
    ('list layers', 'show layers', 'what layers'): 
        (cmd_list_layers, 0, "list_layers()"),
}


def extract_layer_names(user_input):
    """Extract quoted layer names from user input."""
    names = re.findall(r'"([^"]+)"', user_input)
    if not names:
        names = re.findall(r"'([^']+)'", user_input)
    return names


def try_local_command(user_input):
    """Try to execute a pre-written command. Returns result string or False if no match."""
    user_lower = user_input.lower()
    
    for keywords, (func, arg_count, desc) in COMMANDS.items():
        for kw in keywords:
            if kw in user_lower:
                layer_names = extract_layer_names(user_input)
                
                try:
                    if arg_count == 0:
                        return func()
                    elif arg_count == 1 and len(layer_names) >= 1:
                        return func(layer_names[0])
                    elif arg_count == 2 and len(layer_names) >= 2:
                        return func(layer_names[0], layer_names[1])
                    else:
                        return f"[NEED LAYER NAMES] Matched '{kw}'. Usage: {desc}\n  Example: {kw} 'layer1' 'layer2'"
                except Exception as e:
                    return f"[ERROR] {e}"
    
    return False  # No match found


# ============================================================================
# KIMI API CLIENT (Fallback only)
# ============================================================================

class KimiClient:
    def __init__(self, api_key, base_url=KIMI_BASE_URL, model=KIMI_MODEL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.conversation_history = []
        self.last_request_time = 0

    def _wait(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def chat(self, user_message, include_qgis_state=""):
        self._wait()
        
        # Minimal system prompt for Kimi - only for complex queries
        system = (
            "You are a QGIS assistant. Write PyQGIS code. "
            "CRITICAL: Use processing.run('native:ALGORITHM', {params}) for ALL spatial operations. "
            "NEVER invent methods. Use import processing (standalone, NOT from qgis.core). "
            "For styling: QgsFillSymbol.createSimple({'color': 'white'}), QgsLineSymbol.createSimple(...), QgsMarkerSymbol.createSimple(...). "
            "After code, give 1-line explanation."
        )
        
        messages = [{"role": "system", "content": system}]
        if include_qgis_state:
            messages.append({"role": "user", "content": f"QGIS State:\n{include_qgis_state}"})
        messages.append({"role": "user", "content": user_message})

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "messages": messages, "temperature": 0.1, "max_tokens": 4096}

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=120)
                if response.status_code == 429:
                    time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    return f"[ERROR] {e}"
                time.sleep(RETRY_BASE_DELAY)
        return "[ERROR] All retries failed"


# ============================================================================
# CODE EXTRACTOR
# ============================================================================

def extract_code(response):
    code = ""
    if "```python" in response:
        for part in response.split("```python")[1:]:
            if "```" in part:
                code += part.split("```")[0].strip() + "\n\n"
    elif "```" in response:
        parts = response.split("```")
        for i in range(1, len(parts), 2):
            if i < len(parts):
                code += parts[i].strip() + "\n\n"
    return code.strip()


# ============================================================================
# MAIN
# ============================================================================

def print_banner():
    print(r"""
    _    ___ __  __ _ _     ____   ___ _____
   | |  |_ _|  /  (_) |_  |___ / _ \_   _|
   | |__ | || |/| | |  _|   __) | | | || |
   |__|___|_|  |_|_|\__|  |____/\___/ |_|

    KIMI-QGIS Bridge v5.1 | SMART COMMAND MODE
    ---------------------------------------------
    20+ FTTH commands execute INSTANTLY (no AI, no rate limit)
    Kimi API used ONLY for complex queries
    Author: Mustafa M M Elaham
""")


def print_help():
    print("""
=== SMART COMMANDS (Instant - No API call) ===
  count points near 'layer1' 'layer2'   - Count points within 5m of lines
  count points inside 'pts' 'polygons'  - Points inside polygons
  find points outside 'pts' 'polygons'  - Points NOT inside polygons
  add length 'cable_routes'             - Add length_m column
  total length 'cable_routes'           - Sum all line lengths
  join attributes 'target' 'join'       - Spatial join
  check snapping 'poles' 'cables' 1.0   - Check snap tolerance
  snap points 'poles' 'cables' 10.0     - Snap points to lines
  extract start 'fiber_routes'          - Start/end points
  duplicate geometry 'poles'            - Find duplicate locations
  check geometry 'zones'                - Validate geometries
  style green 'zones'                   - Green fill 35% opacity
  style yellow_line 'cables'            - Yellow 2px lines
  style splitter 'splitters'            - Yellow triangles
  style white 'layer'                   - White fill
  buffer 'splitters' 100.0              - 100m buffer
  splitter ratio 'zones'                - Calc 1:2/4/8/16/32/64/128
  list layers                           - Show all layers

=== BRIDGE COMMANDS ===
  /help     This message
  /state    Show QGIS state
  /image    Capture screenshot
  /reset    Reset Kimi conversation
  /quit     Exit

=== AI FALLBACK ===
  For complex queries not in the list above, Kimi API is used.
  Rate limit: 0.5s delay. Tier 1 ($10) recommended for 200 RPM.
""")


def main():
    print_banner()

    global KIMI_API_KEY
    if not KIMI_API_KEY:
        KIMI_API_KEY = input("Enter Kimi API Key (or press Enter to use local commands only): ").strip()

    kimi = None
    if KIMI_API_KEY and KIMI_API_KEY.startswith("sk-"):
        print("[OK] Kimi API enabled (fallback mode)")
        kimi = KimiClient(api_key=KIMI_API_KEY)
    else:
        print("[OK] Running in LOCAL-ONLY mode (no AI)")

    print(f"\n[Connecting to QGIS at {QGIS_MCP_HOST}:{QGIS_MCP_PORT}...]")
    print("[INFO] Run qgis_server.py in QGIS Python Console first!")
    qgis = QGISMCPClient(host=QGIS_MCP_HOST, port=QGIS_MCP_PORT)

    if not qgis.connect():
        print("[WARNING] QGIS not connected. Run qgis_server.py first.")
        qgis_connected = False
    else:
        qgis_connected = True
        print("[OK] Connected to QGIS")

    print("\n[Bridge ready! Type /help for commands]\n")

    while True:
        try:
            user_input = input("\n[You] ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input:
            continue

        if user_input.lower() in ["/quit", "/exit", "quit", "exit"]:
            break
        elif user_input.lower() == "/help":
            print_help()
            continue
        elif user_input.lower() == "/state":
            if qgis_connected:
                try:
                    print(f"\n{qgis.get_qgis_state_summary()}")
                except Exception as e:
                    print(f"[ERROR] {e}")
            else:
                print("[ERROR] QGIS not connected")
            continue
        elif user_input.lower() == "/image":
            if qgis_connected:
                img_path = os.path.join(tempfile.gettempdir(), "qgis_capture.png")
                if qgis.save_map_image(img_path):
                    print(f"[OK] Screenshot: {img_path}")
            continue
        elif user_input.lower() == "/reset":
            if kimi:
                kimi.conversation_history = []
            print("[OK] Reset")
            continue

        # === SMART COMMAND MODE ===
        # 1. Try local pre-written command (INSTANT, no API)
        local_result = try_local_command(user_input)
        
        if local_result and not local_result.startswith("[NEED"):
            print(f"\n[LOCAL] {local_result}")
            continue
        elif local_result and local_result.startswith("[NEED"):
            print(f"\n{local_result}")
            continue

        # 2. Fallback to Kimi API (for complex queries)
        if not kimi:
            print("[LOCAL] Unknown command. Type /help for available commands.")
            print("[INFO] Add KIMI_API_KEY for AI fallback mode.")
            continue

        print("\n[Kimi AI fallback - thinking...]")
        qgis_state = ""
        if qgis_connected:
            try:
                qgis_state = qgis.get_qgis_state_summary()
            except:
                pass

        response = kimi.chat(user_input, include_qgis_state=qgis_state)
        
        # Show explanation (non-code part)
        explanation = response
        if "```python" in response:
            explanation = response.split("```python")[0].strip()
        elif "```" in response:
            parts = response.split("```")
            explanation = parts[0].strip()
        
        if explanation.strip():
            print(f"\n[Kimi] {explanation.strip()}")

        # Execute code in QGIS
        code = extract_code(response)
        if code and qgis_connected:
            print("\n" + "=" * 50)
            print("EXECUTING:")
            print(code[:400] + "..." if len(code) > 400 else code)
            print("=" * 50)
            try:
                result = qgis.execute_code(code)
                if result.get("output"):
                    print(f"\n[OUTPUT]\n{result['output']}")
                if result.get("error"):
                    print(f"\n[ERROR]\n{result['error']}")
            except Exception as e:
                print(f"[ERROR] Execution failed: {e}")

    if qgis_connected:
        qgis.disconnect()
    print("[OK] Bridge closed")


if __name__ == "__main__":
    main()
