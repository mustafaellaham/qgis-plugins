"""
FTTH Auto BOM - Drop Cable Optimizer
Counts drop cables and matches to nearest fixed precon length.
Author: Mustafa M M Elaham
"""

DROP_LENGTHS = [50, 80, 100, 120, 150, 180, 200, 250, 300, 350, 400]
DROP_CODES = {
    50: "14137938",      80: "14137938-001",  100: "14137938-002",
    120: "14137938-003", 150: "14137938-004", 180: "14137938-005",
    200: "14137938-006", 250: "14137938-007", 300: "14137938-008",
    350: "14137938-009", 400: "14137938-010",
}
DROP_DESCS = {
    50:  "Pre-terminated Drop Cable 50m SC/APC-SC/APC",
    80:  "Pre-terminated Drop Cable 80m SC/APC-SC/APC",
    100: "Pre-terminated Drop Cable 100m SC/APC-SC/APC",
    120: "Pre-terminated Drop Cable 120m SC/APC-SC/APC",
    150: "Pre-terminated Drop Cable 150m SC/APC-SC/APC",
    180: "Pre-terminated Drop Cable 180m SC/APC-SC/APC",
    200: "Pre-terminated Drop Cable 200m SC/APC-SC/APC",
    250: "Pre-terminated Drop Cable 250m SC/APC-SC/APC",
    300: "Pre-terminated Drop Cable 300m SC/APC-SC/APC",
    350: "Pre-terminated Drop Cable 350m SC/APC-SC/APC",
    400: "Pre-terminated Drop Cable 400m SC/APC-SC/APC",
}

def nearest_drop_length(actual_length):
    """Find nearest fixed drop cable length (round up)"""
    for fixed in DROP_LENGTHS:
        if actual_length <= fixed:
            return fixed
    return DROP_LENGTHS[-1]

def optimize_drops(drop_lengths_list):
    """
    Convert list of actual drop cable lengths to optimized fixed-length counts.

    drop_lengths_list: list of actual distances (e.g., [45, 62, 78, 95, 110, ...])
    Returns: dict {fixed_length: count}
    """
    counts = {length: 0 for length in DROP_LENGTHS}

    for actual in drop_lengths_list:
        fixed = nearest_drop_length(actual)
        counts[fixed] += 1

    # Remove zeros
    return {k: v for k, v in counts.items() if v > 0}

def drop_cables_from_layer(block_layer, distance_field="drop_length"):
    """
    Read drop cable lengths from block layer attribute.
    Returns optimized counts dict.
    """
    if not block_layer or not block_layer.isValid():
        return {}

    fields = [f.name() for f in block_layer.fields()]
    length_field = None
    for f_name in fields:
        if distance_field.lower() in f_name.lower():
            length_field = f_name
            break

    if not length_field:
        return {}

    lengths = []
    for feat in block_layer.getFeatures():
        val = feat.attribute(length_field)
        try:
            lengths.append(float(val))
        except (ValueError, TypeError):
            pass

    return optimize_drops(lengths)

def get_drop_bom_items(counts_dict):
    """Convert drop counts to BOM items"""
    items = []
    for length, qty in sorted(counts_dict.items()):
        code = DROP_CODES.get(length, "")
        desc = DROP_DESCS.get(length, f"Drop Cable {length}m")
        items.append((code, qty, desc))
    return items
