"""
FTTH Auto BOM - Auto Calculator
Calculates all material quantities from layer data.
Includes full cable/DE/tangent/seal mapping, MDU handling,
and all user-specified relations.
Author: Mustafa M M Elaham
"""

# ============================================================
# CABLE → DEAD END / TANGENT / SEAL COMPATIBILITY MAPS
# ============================================================

DE_MAP = [
    {"od_min": 4.8, "od_max": 6.2, "code": "01524339", "desc": "Dead End (4.8mm - 6.2mm)"},
    {"od_min": 4.8, "od_max": 6.2, "code": "01524344", "desc": "Dead End (4.8mm - 6.2mm) alt"},
    {"od_min": 5.6, "od_max": 8.0, "code": "01524342", "desc": "Dead End (5.6mm - 8.0mm)"},
    {"od_min": 12.8, "od_max": 14.1, "code": "01524343", "desc": "Dead End (12.8mm - 14.1mm)"},
    {"od_min": 14.1, "od_max": 16.0, "code": "(DE_14_16)", "desc": "Dead End 14.1-16.0mm (NOT IN LIST)"},
    {"od_min": 16.1, "od_max": 18.0, "code": "(DE_16_18)", "desc": "Dead End 16.1-18.0mm (NOT IN LIST)"},
]

TAN_MAP = [
    {"od_min": 5.6, "od_max": 8.0, "code": "152433", "desc": "Tangent (5.6mm - 8.0mm)"},
    {"od_min": 12.5, "od_max": 14.5, "code": "34543", "desc": "Tangent (12.5 - 14.5mm) Slim-line ADSS"},
    {"od_min": 12.8, "od_max": 14.1, "code": "01524337", "desc": "Tangent (12.8mm - 14.1mm)"},
    {"od_min": 15.11, "od_max": 16.0, "code": "01524341", "desc": "Tangent Support 15.11 - 16.0MM"},
]

SEAL_MAP = [
    {"od_min": 4.0, "od_max": 6.0, "code": "52345330", "desc": "MECH SEAL CIRCULAR PORT QUAD (4-6MM)"},
    {"od_min": 6.0, "od_max": 8.0, "code": "52345324", "desc": "MECH SEAL OVAL PORT KIT 7.1MM-9MM"},
    {"od_min": 8.1, "od_max": 10.0, "code": "52345271", "desc": "MECH SEAL OVAL KIT (MMJ) 9-11MM"},
    {"od_min": 10.1, "od_max": 12.0, "code": "52345274", "desc": "MECH SEAL MEDIUM OVAL KIT 11-13MM"},
    {"od_min": 12.1, "od_max": 14.0, "code": "52345326", "desc": "LMJ OVAL PORT KIT 12.1MM-14MM"},
    {"od_min": 14.1, "od_max": 16.0, "code": "(SEAL_14_16)", "desc": "Oval Port 14.1-16.0mm (NOT IN LIST)"},
    {"od_min": 16.1, "od_max": 18.0, "code": "(SEAL_16_18)", "desc": "Oval Port 16.1-18.0mm (NOT IN LIST)"},
]

def match_best(item_list, cable_od):
    """Find best match by tightest OD range"""
    best = None
    best_range = 999
    for item in item_list:
        if item["od_min"] <= cable_od <= item["od_max"]:
            rng = item["od_max"] - item["od_min"]
            if rng < best_range:
                best_range = rng
                best = item
    return best


# ============================================================
# ITEM CODE DATABASE
# ============================================================

ITEMS = {
    # OLT
    "52345310": {"desc": "PLC 1 x 2 SPLITTER WITH LCAPC (PRE-CONNECTED)", "tier": "OLT"},
    "52345311": {"desc": "Quad flanged mid couplers LC/APC", "tier": "OLT"},
    "52345308": {"desc": "LC/APC to LC/APC patch cord 3m", "tier": "OLT"},
    "52345309": {"desc": "LC/APC to SC/UPC patch cord 3m", "tier": "OLT"},
    "52345312": {"desc": "PANEL MFPS-IXD P-SILD-288-(ZAV2) Right", "tier": "OLT"},
    "52345313": {"desc": "MK2 Fibre Tray 1u patch panel 24 slots", "tier": "OLT"},
    "52345328": {"desc": "VUMA - MID COUPLER LC/APC", "tier": "OLT"},
    # LMJ
    "52345289": {"desc": "DOME JOINT LMJ SHORT Cap + 24XSE2.2MM 12F TRAYS", "tier": "LMJ"},
    "52345291": {"desc": "LMJ SPLITTER TRAY (GREEN TRAYS)", "tier": "LMJ"},
    "52345294": {"desc": "SPLITTER BARE FIBRE 2 WAY", "tier": "LMJ"},
    "01524335": {"desc": "RHI-NODE 1000 MD-STD GLAM (VUMA)", "tier": "Manhole"},
    # HUB
    "52343655": {"desc": "FastConnect Closure SSC2802-TM-8", "tier": "HUB"},
    "14137562": {"desc": "Pigtail SC/APC 0.9mm 1.5m w/ 2.0mm tube", "tier": "HUB"},
    # Block
    "14261299": {"desc": "FAT 8-core 1:8 Mechanical Sealing", "tier": "Block"},
    "14261298": {"desc": "FAT 9-core 1:9 Uneven Splitter", "tier": "Block"},
    # MDU
    "52345276": {"desc": "M8 MICROLOOP 24F JOINT (Entry 6-9mm)", "tier": "MDU"},
    "01524346": {"desc": "AERIAL SLACK STORAGE BRACKET (BLK)", "tier": "MDU"},
    "21157590": {"desc": "COMPACT JOINT POLE FIXING KIT (M8/M16 UNIVERSAL BRACKET)", "tier": "MDU"},
    "01524345": {"desc": "V SHAPE SLACK BRACKET", "tier": "MDU"},
    # Pole
    "21157582": {"desc": "Trans Gum Pole 6M (100/120) CCA", "tier": "Pole"},
    "52235407": {"desc": "Trans Gum Pole 7M (120/140) CCA", "tier": "Pole"},
    "21157583": {"desc": "Trans Gum Pole 9M (120/140) CCA", "tier": "Pole"},
    "21150804": {"desc": "HUAWEI Pole mounting assembly 114~381mm", "tier": "Pole"},
    "01524338": {"desc": "3-Way Hook/Bracket", "tier": "Pole"},
    "52590888": {"desc": "Plastic Wedge Clamp Tool ITC3102", "tier": "Pole"},
    "52590160": {"desc": "Plum Ring Hook ITC3301-P1", "tier": "Pole"},
    "21123886": {"desc": "BANDIT S/STEEL STRAP 19mm (30M)", "tier": "Pole"},
    "21123884": {"desc": "BANDIT S/STEEL BUCKLES 19mm", "tier": "Pole"},
    "14261388": {"desc": "Plastic Cable Storing Assembly ITC2102", "tier": "Pole"},
}


# ============================================================
# DROP CABLE FIXED LENGTHS
# ============================================================
DROP_LENGTHS = [50, 80, 100, 120, 150, 180, 200, 250, 300, 350, 400]
DROP_CODES = {
    50: "14137938", 80: "14137938-001", 100: "14137938-002",
    120: "14137938-003", 150: "14137938-004", 180: "14137938-005",
    200: "14137938-006", 250: "14137938-007", 300: "14137938-008",
    350: "14137938-009", 400: "14137938-010",
}

def nearest_drop_length(actual_length):
    """Find nearest fixed drop cable length, rounding down for cost efficiency"""
    for i, fixed in enumerate(DROP_LENGTHS):
        if actual_length <= fixed:
            return fixed
    return DROP_LENGTHS[-1]


# ============================================================
# MAIN CALCULATOR
# ============================================================

def calculate_auto_bom(layer_data, params):
    """
    Calculate complete BOM from layer data.

    layer_data dict:
        - cables: list of cable dicts from layer_reader
        - hubs: int count
        - blocks: int count
        - mdus: int count
        - poles: dict {total, 6m, 7m, 9m}
        - dir_changes: int total

    params dict:
        - project_name, zone_code
        - is_olt_termination, is_core_mh, is_lmj_existing
        - core_cable_fibers
    """
    cables = layer_data.get("cables", [])
    num_hubs = layer_data.get("hubs", 0)
    num_blocks = layer_data.get("blocks", 0)
    num_mdus = layer_data.get("mdus", 0)
    poles = layer_data.get("poles", {"total": 0, "6m": 0, "7m": 0, "9m": 0})
    total_dir_changes = layer_data.get("dir_changes", 0)

    is_olt = params.get("is_olt_termination", True)
    is_core = params.get("is_core_mh", True)
    lmj_existing = params.get("is_lmj_existing", False)
    num_manholes = params.get("num_manholes", 1)

    # Core calculation: blocks served
    total_units = num_blocks + num_mdus  # Total customer points

    # Splitter counts
    olt_splitters = max(1, (total_units + 3) // 4) if is_olt else 0
    lmj_splitters = max(1, (total_units + 1) // 2)
    bare_fibre = (olt_splitters * 2) if is_olt else lmj_splitters

    bom = []

    # ===== OLT TIER =====
    if is_olt:
        bom.append(("52345310", olt_splitters, "PLC 1x2: 1 per 4 blocks"))
        bom.append(("52345311", olt_splitters, "Quad Coupler: 1 per PLC 1x2"))
        bom.append(("52345308", olt_splitters * 2, "LC/APC patch: 2 per PLC 1x2"))
        bom.append(("52345309", olt_splitters * 2, "LC/SC patch: 2 per PLC 1x2"))
        bom.append(("52345312", 1, "Panel MFPS-IXD 288F: 1 per zone"))
        bom.append(("52345313", 1, "MK2 Fibre Tray 24 slots"))
        bom.append(("52345328", olt_splitters, "Mid Coupler LC/APC: 1 per PLC 1x2"))

    # ===== LMJ TIER =====
    if is_core and not lmj_existing:
        bom.append(("52345289", num_manholes, "LMJ Dome Joint: 1 per new manhole"))
    if is_core:
        bom.append(("52345291", lmj_splitters, "Splitter Tray (Green): 1 per 1:2 splitter"))
        bom.append(("01524335", num_manholes, "RHI-NODE 1000: 1 per core MH"))

    # ===== BARE FIBRE + SPLICE PROTECTORS =====
    bom.append(("52345294", bare_fibre, "Bare Fibre 2-Way: 2x per OLT splitter"))
    bom.append(("SP_1.3MM", bare_fibre * 3, "SP 1.3mm: 3x per bare fibre (3 splices)"))
    bom.append(("SP_2.2MM", bare_fibre * 2, "SP 2.2mm: 2x per bare fibre"))

    # ===== CABLE-SPECIFIC: DE, TANGENT, SEAL per cable =====
    for cable in cables:
        od = cable["od"]
        de_qty = cable.get("dead_end_qty", 0)
        tan_qty = cable.get("tangent_qty", 0)

        # Dead end
        de = match_best(DE_MAP, od)
        if de and de_qty > 0:
            bom.append((de["code"], de_qty, f"DE for {cable['name']} ({cable['type']} {cable['fibers']}F, OD {od}mm)"))

        # Tangent
        tan = match_best(TAN_MAP, od)
        if tan and tan_qty > 0:
            bom.append((tan["code"], tan_qty, f"Tangent for {cable['name']} ({cable['type']} {cable['fibers']}F, OD {od}mm)"))

        # Seal (per manhole)
        seal = match_best(SEAL_MAP, od)
        if seal:
            seal_qty = num_manholes * 2
            bom.append((seal["code"], seal_qty, f"Seal for {cable['name']} ({cable['type']} {cable['fibers']}F, OD {od}mm)"))

    # ===== HUB TIER =====
    # V-Shape Slack Bracket = 1 per hub with MDUs
    if num_mdus > 0:
        bom.append(("01524345", num_hubs, "V-Shape Slack Bracket: 1 per hub (has MDUs)"))

    # Closures: 1 per hub (each hub gets 1 closure)
    bom.append(("52343655", num_hubs, "SSC2802 Closure: 1 per hub"))

    # Pigtails: ONLY for standalone blocks (NOT MDUs)
    if num_blocks > 0:
        bom.append(("14137562", num_blocks, f"Pigtail: 1 per standalone block ({num_blocks} blocks)"))

    # ===== BLOCK TIER (FATs) - ONLY for standalone blocks =====
    if num_blocks > 0:
        fat8 = max(1, int(num_blocks * 0.4))
        fat9 = max(1, num_blocks - fat8)
        bom.append(("14261299", fat8, "FAT 8-core 1:8: ~40% of blocks"))
        bom.append(("14261298", fat9, "FAT 9-core 1:9: ~60% of blocks"))

    # ===== MDU TIER =====
    if num_mdus > 0:
        bom.append(("52345276", num_mdus, "M8 MICROLOOP 24F: 1 per MDU (spliced on feeder, no pigtail)"))
        bom.append(("01524346", num_mdus, "AERIAL SLACK STORAGE BRACKET: 1 per MDU"))
        bom.append(("21157590", num_mdus, "M8/M16 UNIVERSAL BRACKET: 1 per MDU"))

    # ===== POLE TIER =====
    p = poles
    if p["total"] > 0:
        bom.append(("21157582", p.get("6m", 0), "Pole 6M: from pole layer"))
        bom.append(("52235407", p.get("7m", 0), "Pole 7M: from pole layer"))
        bom.append(("21157583", p.get("9m", 0), "Pole 9M: from pole layer"))

    # === USER CONFIRMED RELATIONS ===
    # 1. Huawei Pole Mount = Plum Ring Hook (no metal hoop) = Trans Gum Pole 6M (1:1:1)
    num_6m = p.get("6m", 0)
    if num_6m > 0:
        bom.append(("21150804", num_6m, "Huawei Pole Mount: = Pole 6M count"))
        bom.append(("52590160", num_6m, "Plum Ring Hook (no metal hoop): = Pole 6M count"))

    # 2. Wedge Clamp = 2 x Trans Gum Pole 6M
    if num_6m > 0:
        bom.append(("52590888", num_6m * 2, "Wedge Clamp: 2x Pole 6M count"))

    # 3. Aerial Slack Storage Bracket = FAT 8 + FAT 9
    # (already counted per MDU above, but also relates to FATs)
    # This is a validation rule, not additional qty

    # 4. V-Shape Slack Bracket = SSC2802 Closure
    # Already handled: V-Shape = num_hubs when MDUs exist

    # 3-Way Hook = direction changes
    if total_dir_changes > 0:
        bom.append(("01524338", total_dir_changes, "3-Way Hook: 1 per direction change (>30 deg)"))

    # Bandit straps
    total_poles = p.get("total", 0)
    if total_poles > 0:
        straps = max(1, total_poles // 20)
        bom.append(("21123886", straps, "Bandit Strap: 1 per 20 poles"))
        bom.append(("21123884", straps * 2, "Bandit Buckles: 2 per strap"))

    # Cable storing assembly (1 per hub)
    if num_hubs > 0:
        bom.append(("14261388", num_hubs, "Cable Storing Assembly ITC2102: 1 per hub"))

    return bom
