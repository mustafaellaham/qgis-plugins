# Import KMZ/KML with All Folders as Separate QGIS Layers — At Once

## The Honest Answer

**No existing QGIS plugin does exactly what you want.** KML Tools was deliberately designed by the NSA to do the *opposite* — merge all folders into 3 layers to avoid crashes. [^2^] The native QGIS importer *does* create separate layers per folder (which is what you want), but forces you to import them **one by one** through a dialog, and frequently **crashes** when there are many folders. [^2^]

The only way to get all 20 (or however many) folders imported as **20 separate QGIS layers in one shot** is a **PyQGIS script**. GDAL already sees each KML `<Folder>` as a separate "sublayer" — the script simply tells QGIS to load every sublayer automatically instead of manually picking them one by one.

---

## The Solution: PyQGIS Script (Copy-Paste into QGIS Python Console)

Open QGIS → **Plugins → Python Console** (or press `Ctrl+Alt+P`). Click the **Show Editor** button (icon with a pencil and paper), paste the following code, **change the `kmz_path`** to your actual file path, then click **Run Script**.

```python
"""
Import all KML/KMZ folders as separate QGIS layers at once.
Each <Folder> in the KML becomes its own QGIS layer, preserving names.
Compatible with QGIS 3.44
"""
from qgis.core import QgsVectorLayer, QgsProject, QgsDataProvider, QgsWkbTypes
from qgis.PyQt.QtWidgets import QFileDialog
import os

# ============================================================
# CHANGE THIS TO YOUR KMZ/KML FILE PATH
# Example Windows:  r"C:\FTTH\network.kmz"
# Example Linux/Mac: "/home/user/FTTH/network.kmz"
# ============================================================
kmz_path = r"C:\YOUR\PATH\HERE\file.kmz"  # <-- EDIT THIS

# If you want a file picker dialog instead, uncomment the next 2 lines:
# kmz_path, _ = QFileDialog.getOpenFileName(None, "Select KMZ/KML file", "", "KML/KMZ (*.kmz *.kml)")
# if not kmz_path: raise Exception("No file selected")

if not os.path.exists(kmz_path):
    raise FileNotFoundError(f"File not found: {kmz_path}")

# Step 1: Open the KMZ to discover all sublayers (folders)
probe_layer = QgsVectorLayer(kmz_path, "probe", "ogr")
if not probe_layer.isValid():
    raise Exception("Failed to open KMZ/KML file. Check the path and file format.")

# Step 2: Get all sublayer names — each KML <Folder> is a sublayer
sub_layers = probe_layer.dataProvider().subLayers()
if not sub_layers:
    raise Exception("No layers found in the KMZ/KML file.")

print(f"Found {len(sub_layers)} folder(s) in the KMZ. Loading all as separate layers...\n")

# Step 3: Iterate and load each folder as its own QGIS layer
loaded_count = 0
skipped_empty = 0

for sub in sub_layers:
    # subLayers() returns pipe-delimited strings; extract the layer name
    # Format example: "0" or "1|Folder Name|1|Point|EPSG:4326"
    parts = sub.split(QgsDataProvider.SUBLAYER_SEPARATOR)
    
    # The layer name is the second element (index 1) if multi-part, 
    # otherwise use the whole string (older QGIS versions)
    if len(parts) >= 2:
        layer_name = parts[1]
    else:
        layer_name = sub
    
    # Skip layers with empty names (sometimes happens with malformed KML)
    if not layer_name or layer_name.strip() == "":
        continue
    
    # Construct the OGR URI with |layername= to load a specific folder
    uri = f"{kmz_path}|layername={layer_name}"
    
    # Create and add the layer
    vlayer = QgsVectorLayer(uri, layer_name, "ogr")
    
    if vlayer.isValid() and vlayer.featureCount() > 0:
        QgsProject.instance().addMapLayer(vlayer)
        geom_type = QgsWkbTypes.displayString(vlayer.wkbType())
        print(f"  Loaded: '{layer_name}'  ({vlayer.featureCount()} features, {geom_type})")
        loaded_count += 1
    elif vlayer.isValid():
        print(f"  Skipped: '{layer_name}' (0 features)")
        skipped_empty += 1
    else:
        print(f"  FAILED:  '{layer_name}' — could not load")

print(f"\n{'='*60}")
print(f"Done! Successfully loaded: {loaded_count} layer(s)")
if skipped_empty > 0:
    print(f"Skipped (empty):         {skipped_empty} layer(s)")
print(f"{'='*60}")
```

### What This Script Does

| Step | Action | Result |
|---|---|---|
| **1. Probe** | Opens the KMZ once to query its structure | GDAL reports every `<Folder>` as a sublayer [^73^] |
| **2. Discover** | Extracts all folder (layer) names | You see a count of how many folders exist |
| **3. Iterate** | Loops through each folder name | One iteration per KML folder — your 20 folders = 20 iterations |
| **4. Load** | Constructs `filepath\|layername=FolderName` URI [^80^] | Each folder loads as a separate QGIS layer with its original name |
| **5. Add** | Calls `QgsProject.instance().addMapLayer()` [^69^] | Layer appears in QGIS Layers panel instantly |

### The Key Mechanism: OGR Sublayer URIs

The script exploits a standard GDAL/OGR feature that QGIS already supports: **sublayer selection via URI**. When you have a multi-layer file (like GeoPackage, DXF, or KML), you can specify which internal layer to load using the `|layername=` suffix. [^73^] [^80^]

For a KMZ file containing folders named "Feeder Cables", "Drop Cables", "Manholes", and "Poles", the URIs look like:

```
C:\FTTH\network.kmz|layername=Feeder Cables
C:\FTTH\network.kmz|layername=Drop Cables
C:\FTTH\network.kmz|layername=Manholes
C:\FTTH\network.kmz|layername=Poles
```

Each URI loads only that folder's features as a standalone QGIS layer, preserving the folder name as the layer name. This is exactly how QGIS handles GeoPackage sublayers internally — the same mechanism works for KML because GDAL's KML driver exposes each `<Folder>` as a named sublayer. [^71^]

---

## Alternative: Command-Line Method (ogrinfo + ogr2ogr)

If you prefer working outside QGIS or need to **batch-process many KMZ files**, use GDAL's command-line tools. These are already installed with QGIS (accessible via the **OSGeo4W Shell** on Windows).

### Step A — See All Folders (Sublayers) in Your KMZ

```bash
ogrinfo your_file.kmz
```

Output example:
```
1: Feeder Cables (Line String)
2: Drop Cables (Line String)
3: Manholes (Point)
4: Poles (Point)
5: Service Area (Polygon)
```

Each numbered entry is a KML folder that GDAL recognizes as a separate layer. [^71^]

### Step B — Extract All Folders to GeoPackage (Preserves Separate Layers)

```bash
# Single command — converts KMZ to GPKG, each folder becomes its own table
ogr2ogr -f GPKG output_ftth.gpkg input_ftth.kmz
```

Then open the `.gpkg` in QGIS. Each folder will appear as a separate selectable layer in the **Data Source Manager** (Layer → Add Layer → Add Vector Layer → select the `.gpkg`). [^65^]

### Step C — Batch Convert Multiple KMZ Files

**Windows (Command Prompt or OSGeo4W Shell):**
```batch
for %f in (*.kmz) do ogr2ogr -f GPKG "%~nf.gpkg" "%f"
```

**Linux/Mac (Terminal):**
```bash
for f in *.kmz; do ogr2ogr -f GPKG "${f%.kmz}.gpkg" "$f"; done
```

---

## Comparison: Which Method to Use?

| Requirement | PyQGIS Script | ogr2ogr Command-Line |
|---|---|---|
| **Keep folders as separate QGIS layers** | Yes — each folder = one layer | Yes — each folder = one GPKG table |
| **Import directly into current QGIS project** | Yes — layers appear instantly | No — must open GPKG after conversion |
| **Popup/label data preserved** | Yes — raw HTML in Description field | Yes — raw HTML in Description field |
| **Expand popup HTML into attributes** | Requires manual KML Tools step after | Requires manual KML Tools step after |
| **Batch process 10+ KMZ files** | Needs script modification | Built-in wildcard/loop support |
| **Export to SHP format** | Save each layer individually | Add `-f "ESRI Shapefile"` per layer |
| **Speed** | Fast (< 5 seconds for 20 folders) | Very fast (GDAL native) |

---

## Important Note About Popup Labels (FTTH Data)

Both the PyQGIS script and the ogr2ogr method load the **raw HTML description** from each KML placemark into a single `description` field. [^9^] Your FTTH labels (cable IDs, fiber counts, splitter info, addresses) are still there — but embedded as HTML.

To extract this structured data into proper QGIS attribute columns, run the **KML Tools → Expand HTML Description Field** tool (yes, KML Tools is still useful here) on each imported layer: [^20^]

1. Select the layer in the Layers panel
2. Go to **Vector → KML Tools → Expand HTML Description Field**
3. Choose the parsing mode matching your KMZ popup format (2-column table, tag=value, or tag: value)
4. Select which fields to expand → OK

This gives you the best of both worlds: **all folders as separate layers** (via the script) **AND** **popup data as queryable attributes** (via KML Tools expansion).

---

## Quick Reference: File Paths by Operating System

In the PyQGIS script, set `kmz_path` using these formats:

| OS | Example Path | Notes |
|---|---|---|
| **Windows** | `r"C:\Projects\FTTH\network.kmz"` | Use raw string `r"..."` to avoid escape issues |
| **Windows** | `"C:/Projects/FTTH/network.kmz"` | Forward slashes also work in QGIS |
| **Linux** | `"/home/user/projects/ftth/network.kmz"` | Standard Unix path |
| **macOS** | `"/Users/user/Projects/FTTH/network.kmz"` | Standard macOS path |

If you prefer not to type the path manually, **uncomment** the `QFileDialog` lines in the script (lines 14–15) to get a file picker dialog when you run it.
