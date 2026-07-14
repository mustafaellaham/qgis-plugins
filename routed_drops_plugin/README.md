# Huawei / Vumatel QODN FTTH Network Labeler

**Author:** Mustafa M M Ellaham  
**Contact:** Mustafaellaham@gmail.com  
**QGIS Version:** 3.16+  
**Plugin Version:** v8.6.20 FINAL

---

## Table of Contents

1. [Overview](#overview)
2. [What's Included](#whats-included)
3. [Installation](#installation)
4. [Required Layers & Preparation](#required-layers--preparation)
5. [Layer Naming Standards](#layer-naming-standards)
6. [Pre-Processing Checklist](#pre-processing-checklist)
7. [Tool 1: Pre-Flight Validation](#tool-1-pre-flight-validation)
8. [Tool 2: Auto Network Labeler](#tool-2-auto-network-labeler)
9. [Tool 3: Splicing Plan Generator](#tool-3-splicing-plan-generator)
10. [Routed Drop Lines Plugin (v3.0)](#routed-drop-lines-plugin-v30)
11. [Troubleshooting](#troubleshooting)
12. [Version History](#version-history)

---

## Overview

This QGIS plugin automates FTTH (Fiber to the Home) network labeling for **Huawei / Vumatel QuickODN** designs. It replaces **5-6 working days** of manual labeling with **~40 seconds** of automated processing, and generates splicing plans from **3 days of manual Excel work** to **1 click**.

**Before:** Manually type every AG, Block, FJ, DJ, DC, FC, Pole label into QGIS attribute tables. Inconsistent naming, late QA catches, complete redo on any AG/Block number change.

**After:** Select layers, enter Area Code, click Run. All labels generated automatically with 100% consistency.

---

## What's Included

| Tool | Purpose | Time Saved |
|------|---------|------------|
| **Pre-Flight Validation** | Checks all layers, columns, CRS, geometry before running | Prevents runtime errors |
| **Auto Network Labeler** | Generates AG, Block, FJ, LJ, DJ, DC, FC, Pole labels | 5-6 days → ~40 sec |
| **Splicing Plan Generator** | One-click Excel output with formatted splicing data | 3 days → 1 click |

**Additional Plugin:**
| Tool | Purpose |
|------|---------|
| **Routed Drop Lines Generator v3.0** | Reroutes premises through closest pole on DC cable, preserving original DJ connections |

---

## Installation

### Method 1: Install from ZIP (Recommended)

1. Open QGIS
2. Go to **Plugins → Manage and Install Plugins → Install from ZIP**
3. Select `ftth_labeler_v8.6.20_FINAL.zip`
4. Restart QGIS
5. The plugin appears in **Processing Toolbox → FTTH Tools**

### Method 2: Manual Install

```bash
# Copy plugin folder to QGIS plugins directory
# Windows:
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\

# Mac:
~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/

# Linux:
~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```

### For Routed Drop Lines Plugin

Install `routed_drops_plugin.zip` using the same ZIP install method. It appears as a separate tool in **Processing Toolbox → FTTH Tools → Routed Drop Lines Generator**.

---

## Required Layers & Preparation

### CRITICAL: All layers must be properly prepared BEFORE running the plugin.

### Required Input Layers

| # | Layer | Geometry | Required? | Description |
|---|-------|----------|-----------|-------------|
| 1 | **Aggregation_polygons** | Polygon | Yes | AG boundaries (1-24 per design) |
| 2 | **Block_polygons** | Polygon | Yes | Block boundaries (2-5 per AG) |
| 3 | **Feeder_aggregation** | Point | Yes | Feeder Joint (FJ) locations (1 per AG) |
| 4 | **Distributions joints** | Point/Polygon | Yes | Distribution Joint (DJ) locations |
| 5 | **Distribution** | LineString | Yes | Distribution Cable (DC) segments |
| 6 | **core_cable** | LineString | Optional | Feeder Cable (FC) lines |
| 7 | **New Gum poles** / **customized_poles** | Point | Optional | Pole locations (6m/7m/9m) |

### For Routed Drop Lines Plugin (Additional)

| # | Layer | Geometry | Required? | Description |
|---|-------|----------|-----------|-------------|
| 8 | **Drops** | LineString | Yes | Existing drop lines (premise→DJ connections) |
| 9 | **Distribution** | LineString | Yes | DC cable lines (for pole ordering) |

---

## Layer Naming Standards

The plugin recognizes layers by **exact name** (case-insensitive). Use these standard names:

### Primary Layers

| Standard Name | Alternative Names | Content |
|---------------|-------------------|---------|
| `Aggregation_polygons` | `AG`, `Aggregation` | AG boundary polygons |
| `Block_polygons` | `Block`, `Blocks` | Block boundary polygons |
| `Feeder_aggregation` | `FJ`, `Feeder_Joint` | FJ point locations |
| `Distributions joints` | `DJ`, `Distribution_Joints` | DJ points/polygons |
| `Distribution` | `DC`, `Distribution_Cable` | DC line segments |
| `core_cable` | `FC`, `Feeder_Cable` | FC line segments |
| `New Gum poles` | `customized_poles`, `Poles` | Pole point locations |
| `Premise data` | `Premises`, `Houses` | Premise point locations |
| `Drops` | `Drop_Cables` | Existing drop line segments |

---

## Pre-Processing Checklist

### ALL items must be completed before running the plugin.

#### 1. Snapping (CRITICAL)

All features must be **topologically connected**. Snapping ensures the geometric trace algorithm can follow the network.

| Snap This | To This | Tolerance | Priority |
|-----------|---------|-----------|----------|
| **Drop cables** | **Premise points** | 1-2 meters | 1 |
| **DJ points** | **Pole points** | 1-2 meters | 2 |
| **Drop cables** | **DJ points** | 1-2 meters | 3 |
| **DC cables** | **DJ points** | 1-2 meters | 4 |
| **DC cables** | **Pole points** | 1-2 meters | 5 |

**How to snap in QGIS:**
1. Enable snapping: **Project → Snapping Options**
2. Set snapping mode to **Vertex** or **Vertex and Segment**
3. Set tolerance to **1-2 meters** (or 5-10 pixels)
4. Snap each layer to its target

#### 2. CRS (Coordinate Reference System)

| Requirement | Detail |
|-------------|--------|
| All layers must use the **same CRS** | Check: Layer → Properties → Source |
| Recommended CRS | Project-local UTM zone (e.g., UTM 35S for South Africa) |
| Avoid | Mixing WGS84 (EPSG:4326) with projected CRS |

#### 3. Required Columns

Each layer needs specific columns. The plugin checks for these during Pre-Flight Validation.

**AG Polygons:**
| Column | Type | Description |
|--------|------|-------------|
| `ID` or `name` | Integer/String | AG number (1, 2, 3...) |

**Block Polygons:**
| Column | Type | Description |
|--------|------|-------------|
| `ID` or `name` | Integer/String | Block number (1, 2, 3...) |

**Poles:**
| Column | Type | Description |
|--------|------|-------------|
| `name` | String | Pole name (e.g., `MGR_Z01_P0891`) |

**DJs:**
| Column | Type | Description |
|--------|------|-------------|
| `name` | String | DJ name (e.g., `DJ284_1:9`) |

**FC Cables (if used):**
| Column | Type | Description |
|--------|------|-------------|
| `size` | Integer | Fiber count (144, 288) |
| `type` | String | Cable type (`CC0X`, `FC`, `LC`) |
| `ID` or `name` | String | Cable identifier |

#### 4. Geometry Validation

| Check | How To |
|-------|--------|
| No empty geometries | **Vector → Geometry Tools → Check Validity** |
| No duplicate vertices | **Vector → Geometry Tools → Simplify** |
| Lines are properly connected | Visually inspect at high zoom |
| Polygons are closed | **Vector → Geometry Tools → Fix Geometries** |

#### 5. DJ-to-Pole Assignment (For Routed Drop Lines)

For the **Routed Drop Lines** plugin, you must have:
- DJs **snapped to** or **located very near** their poles
- Existing **drop lines** connecting each premise to its DJ
- These drop lines define which premise belongs to which DJ (PRESERVED, not changed)

---

## Tool 1: Pre-Flight Validation

**Purpose:** Checks all inputs before processing to catch errors early.

**What it checks:**
- All required layers exist and are loaded
- Layer geometry types are correct (polygons for AG/Block, points for FJ/DJ/Poles, lines for DC/FC)
- Required columns exist (ID, name fields)
- CRS is consistent across layers
- No empty layers
- No empty geometries
- Minimum feature counts (e.g., at least 1 AG, at least 1 FJ)

**How to run:**
1. Select all required layers in the dialog
2. Click **Run**
3. Review the validation report
4. Fix any errors before running the Labeler

---

## Tool 2: Auto Network Labeler

**Purpose:** Generates all network element labels automatically.

### Dialog Inputs

| Field | What to Enter | Example |
|-------|--------------|---------|
| Premises Layer | Select premises point layer | `Premise data` |
| AG Polygons Layer | Select AG polygon layer | `Aggregation_polygons` |
| AG ID Field | Column with AG numbers | `ID` |
| Block Polygons Layer | Select Block polygon layer | `Block_polygons` |
| Block ID Field | Column with Block numbers | `ID` |
| FJ Layer | Select FJ point layer | `Feeder_aggregation` |
| DJ Layer | Select DJ point/polygon layer | `Distributions joints` |
| DC Layer | Select DC line layer | `Distribution` |
| FC Layer (optional) | Select FC line layer | `core_cable` |
| Poles Layer (optional) | Select poles point layer | `New Gum poles` |
| Area Code | Your project area code | `VTN_HHS_GMG` |
| Zone Code (optional) | Zone identifier | `Z02` |

### What Gets Generated

| Element | Naming Convention | Example |
|---------|-------------------|---------|
| AG | `{AreaCode}_AG{NN:02d}` | `VTN_HHS_GMG_AG01` |
| Block | `{AreaCode}_AG{NN}_B{N}` | `VTN_HHS_GMG_AG01_B1` |
| FJ | `{AreaCode}_FJ{NN:02d}` | `VTN_HHS_GMG_FJ01` |
| DJ | `{AreaCode}_DJ{NNN:03d}_{ratio}` | `VTN_HHS_GMG_DJ001_1:9` |
| DC | `DC{block}.{seq}` | `DC1.1`, `DC1.2` |
| FC | `{AreaCode}_{AG1-AG2}_FC{NN}_{size}F` | `VTN_HHS_GMG_AG01-AG02_FC01_144F` |
| Pole | `{AreaCode}_P{NNNN}` | `VTN_HHS_GMG_P0001` |

### DJ Splitter Logic (Huawei QuickODN)

| DJ Position | Splitter Type | Ratio |
|-------------|--------------|-------|
| 1st in chain | Position 1 | 1:9 |
| 2nd in chain | Position 2 | 1:9 |
| 3rd in chain | Position 3 | 1:9 |
| 4th (last) | Position 4 | **1:8** |

Chain: **1:9 → 1:9 → 1:9 → 1:8** (4 DJs max per chain)

---

## Tool 3: Splicing Plan Generator

**Purpose:** Generates a formatted Excel splicing plan from labeled data.

### Prerequisites

- Run the **Auto Network Labeler** first (labels must exist)
- All labels must be written to layer attributes

### What It Generates

| Sheet | Content |
|-------|---------|
| Splicing Plan | One row per house with: House ID, Drop cable, DJ name, Splitter position, Port number, DC segments |
| Professional Formatting | Yellow highlights on splitter rows, alternating colors, merged title cells, auto column widths, freeze panes |

### How to Run

1. Complete labeling with the Auto Network Labeler
2. The splicing plan generates automatically after labeling
3. Or run it separately from the Processing Toolbox
4. Output: `.xlsx` file ready for submission

---

## Routed Drop Lines Plugin (v3.0)

**Purpose:** Reroutes premises through the closest intermediate pole on the DC cable route, while **preserving the original DJ connection**.

### CRITICAL RULE: DJ Connections Are Preserved

The plugin reads your **existing drop lines** to know which DJ each premise currently connects to. It **never changes** this assignment. It only changes the **physical path** (which pole the cable passes through).

### Required Layers (5)

| # | Layer | Geometry | Purpose |
|---|-------|----------|---------|
| 1 | Premises | Point | House locations |
| 2 | Distribution Joints | Point | DJ locations |
| 3 | Poles | Point | All poles with names |
| 4 | **Existing Drop Lines** | Line | **Defines premise→DJ connections (PRESERVED)** |
| 5 | Distribution Cables | Line | DC cable routes for pole ordering |

### How It Works

```
Step 1: Read existing drop lines
        Premise ──────→ DJ  (current connection)
        
Step 2: Extract FROM→TO from each drop line
        Start = premise side, End = DJ side
        
Step 3: Match to find premise→DJ mapping (PRESERVED)

Step 4: Match each DJ to its nearest pole (destination)

Step 5: On the DC cable route, find all poles ordered along the line

Step 6: For each premise, measure distance to:
        - Previous pole on DC cable
        - Current (closest) pole on DC cable  
        - Next pole on DC cable
        → Choose SHORTEST
        
Step 7: Draw ONE polyline: Premise → Chosen Pole → DJ's Pole
```

### Output

One continuous LineString per premise with fields:

| Field | Description |
|-------|-------------|
| `premise_name` | House identifier |
| `dj_name` | Original DJ (preserved) |
| `dj_pole` | Pole where DJ is mounted (destination) |
| `via_pole` | Closest intermediate pole on DC cable |
| `total_length_m` | Full cable length |
| `seg1_to_via_m` | Premise → via_pole |
| `seg2_via_to_dj_m` | via_pole → DJ pole |
| `original_kept` | "YES" — confirms DJ was preserved |

---

## Troubleshooting

### Plugin crashes with "C++ access violation"

**Cause:** QGIS edit buffer issue.  
**Fix:** The plugin uses `dataProvider().changeAttributeValues()` batch writes (v8.6.13+). If you still see crashes, try:
1. Save your project first
2. Close other heavy layers
3. Run on smaller subset first

### "Main pole 'P2' not found" (Routed Drops v1.x/v2.x)

**Cause:** Pole names don't match (e.g., `MGR_Z01_P0891` vs `P2`).  
**Fix:** Use **v3.0+** which auto-finds the DJ's pole from spatial matching. No manual pole name needed.

### DJ numbering has gaps

**Cause:** Old file-order sorting.  
**Fix:** The plugin uses **Block-ID-driven DJ numbering** (v8.6.8+). DJs are sorted by (AG, Block_ID) then numbered sequentially.

### All DC numbers show as DC2.x

**Cause:** Wrong regex pattern.  
**Fix:** Fixed in v8.6.6+ — regex changed from `r"(\d+)"` to `r"B(\d+)"` to correctly extract block numbers.

### Labels not written to QGIS

**Check:**
1. Is the target layer in edit mode? (Plugin handles this automatically)
2. Does the target layer have the label field? (Pre-flight checks this)
3. Are there special characters in names? (Use alphanumeric only)

### CRS mismatch errors

**Fix:** Ensure ALL layers use the same CRS:
1. **Vector → Data Management Tools → Reproject Layer**
2. Or set project CRS to match your data: **Project → Properties → CRS**

---

## Version History

| Version | Key Changes |
|---------|------------|
| v1.0-v5.x | Foundation: Basic labeling engine |
| v6.0-v7.4 | Enhanced: Multi-AG, FC labeling, BFS tracing |
| v8.0-v8.5 | Splicing Plan: Direct Excel output, dynamic columns |
| v8.6.0 | BOM Generator: 5-sheet Excel BOM |
| v8.6.8 | **Critical Fix:** Block-ID-driven DJ numbering (no gaps) |
| v8.6.13 | **Crash Fix:** dataProvider batch writes |
| v8.6.15 | FC naming: Per-type numbering (CC0x/FC/LC) from layer columns |
| v8.6.19 | **FJ Fix:** Point-in-polygon assignment (not centroid distance) |
| v8.6.20 | Metadata update, documentation |

**Routed Drop Lines:**
| Version | Key Changes |
|---------|------------|
| v1.0 | Basic: Premise + Pole + Main Pole |
| v2.0 | Added DC cable layer for route-based pole ordering |
| v3.0 | **Critical:** Preserves original DJ connections via existing drop lines |

---

## License

All rights reserved. Built and owned by Mustafa M M Ellaham.

For questions or feature requests: Mustafaellaham@gmail.com
