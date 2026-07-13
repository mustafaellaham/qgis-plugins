#!/usr/bin/env python3
"""
FTTH Command Library v2 - Advanced Operations
==============================================
NEW in v2:
1. Text editing in columns (regex replace, number padding)
2. Duplicate name detection in specific column
3. Move data between layers using shared key
4. Multi-layer snap chaining (premise → drop → dist → feeder) with path table

Author: Mustafa M M Elaham
"""

import re
from collections import defaultdict, Counter
from qgis.core import QgsProject, QgsVectorLayer, QgsField, QgsFeatureRequest
from qgis.PyQt.QtCore import QVariant
import processing


def _get_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        available = [l.name() for l in QgsProject.instance().mapLayers().values()]
        raise ValueError(f"Layer '{name}' not found. Available: {available}")
    return layers[0]


# ============================================================================
# 1. EDIT TEXT IN COLUMN - Regex Replace
# ============================================================================

def cmd_edit_column_regex(layer_name, column_name, pattern, replacement):
    """Replace text in column using regex pattern."""
    layer = _get_layer(layer_name)
    layer.startEditing()
    idx = layer.fields().indexOf(column_name)
    if idx < 0:
        raise ValueError(f"Column '{column_name}' not found in '{layer_name}'")
    
    updated = 0
    regex = re.compile(pattern)
    for f in layer.getFeatures():
        old_val = f[column_name] or ""
        new_val = regex.sub(replacement, str(old_val))
        if new_val != old_val:
            layer.changeAttributeValue(f.id(), idx, new_val)
            updated += 1
    layer.commitChanges()
    return f"=== Updated {updated} features in '{column_name}' ==="


def cmd_pad_numbers_in_column(layer_name, column_name, digits=4):
    """Pad numbers inside parentheses with leading zeros.
    
    Example: '(174m-184m)' -> '(0174m-0184m)'
    Usage: pad numbers 'cable' 'name'
    """
    layer = _get_layer(layer_name)
    layer.startEditing()
    idx = layer.fields().indexOf(column_name)
    if idx < 0:
        raise ValueError(f"Column '{column_name}' not found")
    
    def pad_match(match):
        """Pad a single number to specified digits."""
        num = match.group(1)
        return num.zfill(digits)
    
    updated = 0
    for f in layer.getFeatures():
        old_val = f[column_name] or ""
        new_val = re.sub(r'\((\d+)', lambda m: f"({m.group(1).zfill(digits)}", str(old_val))
        if new_val != old_val:
            layer.changeAttributeValue(f.id(), idx, new_val)
            updated += 1
    layer.commitChanges()
    return f"=== Padded numbers in {updated} features in '{column_name}' to {digits} digits ==="


def cmd_extract_to_column(layer_name, source_column, target_column, pattern, group=1):
    """Extract text matching regex from source column to target column.
    Example: extract '174' from '(174m-184m)' using pattern '\\((\\d+)m'
    """
    layer = _get_layer(layer_name)
    layer.startEditing()
    
    if target_column not in layer.fields().names():
        layer.addAttribute(QgsField(target_column, QVariant.String, len=100))
    
    idx = layer.fields().indexOf(target_column)
    regex = re.compile(pattern)
    extracted = 0
    
    for f in layer.getFeatures():
        val = f[source_column] or ""
        match = regex.search(str(val))
        if match:
            layer.changeAttributeValue(f.id(), idx, match.group(group))
            extracted += 1
    layer.commitChanges()
    return f"=== Extracted {extracted} values from '{source_column}' to '{target_column}' ==="


# ============================================================================
# 2. DUPLICATE NAME CHECK IN SPECIFIC COLUMN
# ============================================================================

def cmd_find_duplicate_names(layer_name, column_name):
    """Find and report duplicate values in a specific column.
    Returns full list of duplicates with counts and feature IDs.
    """
    layer = _get_layer(layer_name)
    values = []
    for f in layer.getFeatures():
        val = f[column_name]
        if val:
            values.append((str(val), f.id()))
    
    # Count occurrences
    value_counts = Counter(v[0] for v in values)
    duplicates = {k: v for k, v in value_counts.items() if v > 1}
    
    if not duplicates:
        return f"OK: No duplicates in '{column_name}' ({len(values)} unique values)"
    
    lines = [f"WARNING: {len(duplicates)} duplicate values in '{column_name}':"]
    for val, count in sorted(duplicates.items(), key=lambda x: -x[1]):
        ids = [fid for v, fid in values if v == val]
        lines.append(f"  '{val}': {count} times (IDs: {ids})")
    return "\n".join(lines)


def cmd_select_duplicates(layer_name, column_name):
    """Select features that have duplicate values in a column."""
    layer = _get_layer(layer_name)
    values = [str(f[column_name]) for f in layer.getFeatures() if f[column_name]]
    counts = Counter(values)
    dup_values = {k for k, v in counts.items() if v > 1}
    
    layer.removeSelection()
    ids_to_select = [f.id() for f in layer.getFeatures() if f[column_name] and str(f[column_name]) in dup_values]
    layer.selectByIds(ids_to_select)
    
    return f"=== Selected {len(ids_to_select)} features with duplicate '{column_name}' values ==="


# ============================================================================
# 3. MOVE DATA BETWEEN LAYERS USING SHARED KEY
# ============================================================================

def cmd_copy_field_by_key(target_layer, target_key_field, target_new_field,
                          source_layer, source_key_field, source_value_field):
    """Copy field value from source to target using matching key columns.
    
    Example: copy 'fiber_count' from 'cable_table' to 'cables' layer 
             matching on 'cable_id'
    """
    target = _get_layer(target_layer)
    source = _get_layer(source_layer)
    
    # Build lookup from source
    lookup = {}
    for f in source.getFeatures():
        key = f[source_key_field]
        if key:
            lookup[str(key)] = f[source_value_field]
    
    target.startEditing()
    if target_new_field not in target.fields().names():
        # Determine field type from source
        source_idx = source.fields().indexOf(source_value_field)
        source_field = source.fields()[source_idx]
        target.addAttribute(QgsField(target_new_field, source_field.type(), len=source_field.length()))
    
    idx = target.fields().indexOf(target_new_field)
    updated = 0
    not_found = 0
    
    for f in target.getFeatures():
        key = f[target_key_field]
        if key and str(key) in lookup:
            target.changeAttributeValue(f.id(), idx, lookup[str(key)])
            updated += 1
        else:
            not_found += 1
    
    target.commitChanges()
    return f"=== Copied '{source_value_field}' to '{target_new_field}': {updated} matched, {not_found} not found ==="


def cmd_update_field_from_join(target_layer, target_key, source_layer, source_key, fields_to_copy):
    """Update multiple fields in target from source using key columns.
    fields_to_copy: list of field names to copy
    """
    target = _get_layer(target_layer)
    source = _get_layer(source_layer)
    
    # Build lookup
    lookup = {}
    for f in source.getFeatures():
        key = f[source_key]
        if key:
            lookup[str(key)] = {fld: f[fld] for fld in fields_to_copy}
    
    target.startEditing()
    
    # Add missing fields
    field_indices = {}
    for fld in fields_to_copy:
        if fld not in target.fields().names():
            src_idx = source.fields().indexOf(fld)
            src_field = source.fields()[src_idx]
            target.addAttribute(QgsField(fld, src_field.type(), len=src_field.length()))
        field_indices[fld] = target.fields().indexOf(fld)
    
    updated = 0
    for f in target.getFeatures():
        key = f[target_key]
        if key and str(key) in lookup:
            for fld, idx in field_indices.items():
                target.changeAttributeValue(f.id(), idx, lookup[str(key)][fld])
            updated += 1
    
    target.commitChanges()
    return f"=== Updated {updated} features, copied {fields_to_copy} ==="


# ============================================================================
# 4. MULTI-LAYER SNAP CHAIN + PATH TABLE
# ============================================================================

def cmd_snap_chain(layers_chain, tolerances=None):
    """Snap a chain of layers: each layer snaps to the next.
    
    Example: snap chain 'premises' 'drop_cables' 'distribution_joints' 'feeder_joints'
    With tolerances: 10, 15, 20
    
    Returns: dict mapping each layer to its snapped targets
    """
    if tolerances is None:
        tolerances = [10.0] * (len(layers_chain) - 1)
    
    results = {}
    for i in range(len(layers_chain) - 1):
        source_name = layers_chain[i]
        target_name = layers_chain[i + 1]
        tol = tolerances[i] if i < len(tolerances) else 10.0
        
        source = _get_layer(source_name)
        target = _get_layer(target_name)
        
        result = processing.run("native:snapgeometries", {
            'INPUT': source,
            'REFERENCE_LAYER': target,
            'TOLERANCE': tol,
            'BEHAVIOR': 0,  # Prefer closest point
            'OUTPUT': 'memory:snap_result'
        })
        snapped = result['OUTPUT']
        snapped.setName(f"{source_name}_snapped_to_{target_name}")
        QgsProject.instance().addMapLayer(snapped)
        
        results[f"{source_name} → {target_name}"] = snapped
        print(f"  [{i+1}] Snapped '{source_name}' → '{target_name}' (tol: {tol}m): {snapped.featureCount()} features")
    
    return results


def cmd_nearest_join(from_layer, to_layer, from_field='id', to_field='id', 
                     max_distance=50.0, prefix='nearest_'):
    """Join each feature in from_layer to its NEAREST feature in to_layer.
    Adds distance and target ID columns.
    
    This is the key for building path tables.
    """
    source = _get_layer(from_layer)
    target = _get_layer(to_layer)
    
    # Use join attributes by NEAREST (processing algorithm)
    result = processing.run("native:joinbynearest", {
        'INPUT': source,
        'INPUT_2': target,
        'FIELDS_TO_COPY': [to_field],
        'DISCARD_NONMATCHING': False,
        'PREFIX': prefix,
        'NEIGHBORS': 1,
        'MAX_DISTANCE': max_distance,
        'OUTPUT': 'memory:joined'
    })
    joined = result['OUTPUT']
    joined.setName(f"{from_layer}_to_{to_layer}")
    QgsProject.instance().addMapLayer(joined)
    
    return joined


def cmd_build_path_table(premise_layer, drop_layer, dist_joint_layer, feeder_joint_layer,
                         premise_id='premise_id', drop_id='drop_id', 
                         dist_id='dist_joint_id', feeder_id='feeder_joint_id',
                         max_distance=50.0):
    """Build a complete path table: Premise → Drop → Distribution Joint → Feeder Joint
    
    Steps:
    1. Find nearest drop cable for each premise
    2. Find nearest distribution joint for each drop cable
    3. Find nearest feeder joint for each distribution joint
    4. Output combined table showing full path
    """
    print("=== Building FTTH Path Table ===")
    
    # Step 1: Premise → Drop Cable
    print("[1/3] Linking premises to drop cables...")
    result1 = processing.run("native:joinbynearest", {
        'INPUT': _get_layer(premise_layer),
        'INPUT_2': _get_layer(drop_layer),
        'FIELDS_TO_COPY': [drop_id],
        'DISCARD_NONMATCHING': False,
        'PREFIX': 'drop_',
        'NEIGHBORS': 1,
        'MAX_DISTANCE': max_distance,
        'OUTPUT': 'memory:step1'
    })
    step1 = result1['OUTPUT']
    
    # Step 2: Drop → Distribution Joint
    print("[2/3] Linking drop cables to distribution joints...")
    result2 = processing.run("native:joinbynearest", {
        'INPUT': step1,
        'INPUT_2': _get_layer(dist_joint_layer),
        'FIELDS_TO_COPY': [dist_id],
        'DISCARD_NONMATCHING': False,
        'PREFIX': 'dist_',
        'NEIGHBORS': 1,
        'MAX_DISTANCE': max_distance,
        'OUTPUT': 'memory:step2'
    })
    step2 = result2['OUTPUT']
    
    # Step 3: Distribution → Feeder Joint
    print("[3/3] Linking distribution joints to feeder joints...")
    result3 = processing.run("native:joinbynearest", {
        'INPUT': step2,
        'INPUT_2': _get_layer(feeder_joint_layer),
        'FIELDS_TO_COPY': [feeder_id],
        'DISCARD_NONMATCHING': False,
        'PREFIX': 'feeder_',
        'NEIGHBORS': 1,
        'MAX_DISTANCE': max_distance,
        'OUTPUT': 'memory:path_table'
    })
    path_table = result3['OUTPUT']
    path_table.setName("FTTH_Path_Table")
    QgsProject.instance().addMapLayer(path_table)
    
    # Print summary
    total = path_table.featureCount()
    linked = sum(1 for f in path_table.getFeatures() 
                 if f[f'drop_{drop_id}'] and f[f'dist_{dist_id}'] and f[f'feeder_{feeder_id}'])
    
    print(f"\n{'='*60}")
    print(f"FTTH PATH TABLE COMPLETE")
    print(f"{'='*60}")
    print(f"Total premises: {total}")
    print(f"Full path (all 3 hops): {linked}")
    print(f"Incomplete paths: {total - linked}")
    print(f"\nPath columns:")
    print(f"  Premise: {premise_id}")
    print(f"  → Drop: drop_{drop_id}")
    print(f"  → Dist Joint: dist_{dist_id}")
    print(f"  → Feeder Joint: feeder_{feeder_id}")
    print(f"\nSaved as layer: 'FTTH_Path_Table'")
    
    return path_table


def cmd_trace_path(premise_id_value, path_table_layer='FTTH_Path_Table',
                   premise_col='premise_id', drop_col='drop_drop_id',
                   dist_col='dist_dist_joint_id', feeder_col='feeder_feeder_joint_id'):
    """Trace the full path for a single premise ID."""
    table = _get_layer(path_table_layer)
    
    expr = f""{premise_col}" = '{premise_id_value}'"
    request = QgsFeatureRequest().setFilterExpression(expr)
    
    for f in table.getFeatures(request):
        path = {
            'Premise': f[premise_col],
            'Drop Cable': f[drop_col],
            'Distribution Joint': f[dist_col],
            'Feeder Joint': f[feeder_col]
        }
        lines = [f"=== PATH FOR PREMISE {premise_id_value} ==="]
        for hop, val in path.items():
            status = "✓" if val else "✗ MISSING"
            lines.append(f"  {hop}: {val or 'N/A'} {status}")
        return "\n".join(lines)
    
    return f"Premise '{premise_id_value}' not found in path table"


# ============================================================================
# COMMAND ROUTER v2
# ============================================================================

COMMANDS_V2 = {
    # --- TEXT EDITING ---
    ('edit column', 'regex replace', 'replace text'): 
        (cmd_edit_column_regex, 4, "edit_column_regex(layer, column, pattern, replacement)"),
    ('pad numbers', 'zero pad', 'leading zeros', '4 digit'):
        (cmd_pad_numbers_in_column, 2, "pad_numbers_in_column(layer, column, digits=4)"),
    ('extract to column', 'extract text'):
        (cmd_extract_to_column, 5, "extract_to_column(layer, source_col, target_col, pattern, group=1)"),
    
    # --- DUPLICATE NAMES ---
    ('duplicate name', 'duplicate names', 'check duplicate name'):
        (cmd_find_duplicate_names, 2, "find_duplicate_names(layer, column)"),
    ('select duplicates', 'select duplicate'):
        (cmd_select_duplicates, 2, "select_duplicates(layer, column)"),
    
    # --- MOVE DATA BETWEEN LAYERS ---
    ('copy field', 'copy by key', 'move field', 'transfer field'):
        (cmd_copy_field_by_key, 6, "copy_field_by_key(target, target_key, target_new, source, source_key, source_value)"),
    ('update from join', 'update fields', 'join fields'):
        (cmd_update_field_from_join, 5, "update_field_from_join(target, target_key, source, source_key, [fields])"),
    
    # --- SNAP CHAIN ---
    ('snap chain', 'chain snap', 'snap sequence'):
        (cmd_snap_chain, -1, "snap_chain([layer1, layer2, layer3], [tol1, tol2])"),
    ('nearest join', 'join nearest', 'closest join'):
        (cmd_nearest_join, 2, "nearest_join(from_layer, to_layer, max_distance=50)"),
    ('build path', 'path table', 'ftth path', 'full path'):
        (cmd_build_path_table, 4, "build_path_table(premise, drop, dist_joint, feeder_joint)"),
    ('trace path', 'trace premise', 'show path'):
        (cmd_trace_path, 1, "trace_path(premise_id)"),
}


def extract_quoted_args(text):
    """Extract quoted strings and numbers from input."""
    # Quoted strings
    strings = re.findall(r'"([^"]+)"', text)
    if not strings:
        strings = re.findall(r"'([^']+)'", text)
    
    # Numbers
    numbers = [float(n) for n in re.findall(r'\b(\d+\.?\d*)\b', text)]
    
    return strings, numbers


def try_command_v2(user_input):
    """Try v2 commands. Returns result string or False."""
    user_lower = user_input.lower()
    
    for keywords, (func, arg_count, desc) in COMMANDS_V2.items():
        for kw in keywords:
            if kw in user_lower:
                strings, numbers = extract_quoted_args(user_input)
                
                try:
                    # Special: snap chain takes list of layers
                    if func == cmd_snap_chain:
                        # Parse layer chain from input
                        if len(strings) >= 2:
                            tolerances = numbers if numbers else None
                            result = cmd_snap_chain(strings, tolerances)
                            return f"=== Snap chain complete: {len(result)} links ==="
                        return f"[NEED LAYERS] Usage: snap chain 'layer1' 'layer2' 'layer3' 10 15"
                    
                    # Special: build path table
                    elif func == cmd_build_path_table:
                        if len(strings) >= 4:
                            tols = numbers if numbers else [50.0]
                            result = cmd_build_path_table(
                                strings[0], strings[1], strings[2], strings[3],
                                max_distance=tols[0]
                            )
                            return f"Path table created with {result.featureCount()} rows"
                        return f"[NEED 4 LAYERS] Usage: build path 'premises' 'drop' 'dist_joints' 'feeder_joints'"
                    
                    # Special: trace path
                    elif func == cmd_trace_path:
                        if strings:
                            return cmd_trace_path(strings[0])
                        return "[NEED] Usage: trace path 'premise_id'"
                    
                    # Standard: edit column regex (4 args)
                    elif func == cmd_edit_column_regex and len(strings) >= 2:
                        # Try to extract pattern/replacement from input
                        # Format: edit column 'layer' 'col' 'pattern' 'replacement'
                        if len(strings) >= 4:
                            return func(strings[0], strings[1], strings[2], strings[3])
                        return f"[NEED] Usage: edit column 'layer' 'column' 'regex_pattern' 'replacement'"
                    
                    # Standard: pad numbers (2+ args)
                    elif func == cmd_pad_numbers_in_column and len(strings) >= 2:
                        digits = int(numbers[0]) if numbers else 4
                        return func(strings[0], strings[1], digits)
                    
                    # Standard: extract to column (5 args)
                    elif func == cmd_extract_to_column and len(strings) >= 4:
                        group = int(numbers[0]) if numbers else 1
                        return func(strings[0], strings[1], strings[2], strings[3], group)
                    
                    # Standard: duplicate names (2 args)
                    elif func in (cmd_find_duplicate_names, cmd_select_duplicates) and len(strings) >= 2:
                        return func(strings[0], strings[1])
                    
                    # Standard: copy field by key (6 args)
                    elif func == cmd_copy_field_by_key and len(strings) >= 6:
                        return func(strings[0], strings[1], strings[2], strings[3], strings[4], strings[5])
                    
                    # Standard: update from join (5 args)
                    elif func == cmd_update_field_from_join and len(strings) >= 5:
                        fields = strings[4:]
                        return func(strings[0], strings[1], strings[2], strings[3], fields)
                    
                    # Standard: nearest join (2+ args)
                    elif func == cmd_nearest_join and len(strings) >= 2:
                        max_dist = numbers[0] if numbers else 50.0
                        return func(strings[0], strings[1], max_distance=max_dist)
                    
                    else:
                        return f"[NEED ARGS] Matched '{kw}'. Usage: {desc}"
                        
                except Exception as e:
                    return f"[ERROR] {e}"
    
    return False
