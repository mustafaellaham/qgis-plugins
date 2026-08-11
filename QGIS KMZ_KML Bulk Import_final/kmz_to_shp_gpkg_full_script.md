# Complete PyQGIS Script: KMZ/KML → SHP or GPKG (All Folders as Separate Layers)

## The Fix

The previous script loaded layers into QGIS's memory only. **This version actually writes each KML folder to disk as SHP or GPKG files** using `QgsVectorFileWriter.writeAsVectorFormatV3()`. [^85^]

---

## PyQGIS Script — Copy, Edit Paths, Run

Open QGIS → **Plugins → Python Console** → click **Show Editor** (pencil icon). Paste this code, **edit the two paths**, click **Run Script**.

```python
"""
KMZ/KML Bulk Converter - Saves ALL folders as separate SHP or GPKG files
Compatible with QGIS 3.44
Each KML <Folder> becomes its own output file/layer
"""
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsDataProvider,
    QgsVectorFileWriter, QgsCoordinateTransformContext
)
from qgis.PyQt.QtWidgets import QFileDialog
import os

# ============================================================
# 1. INPUT FILE PATH (your KMZ or KML file)
# ============================================================
input_path = r"C:\YOUR\PATH\HERE\file.kmz"  # <-- EDIT THIS

# Use file picker dialog? Uncomment below:
# input_path, _ = QFileDialog.getOpenFileName(None, "Select KMZ/KML", "", "KML/KMZ (*.kml *.kmz)")
# if not input_path: raise Exception("No file selected")

if not os.path.exists(input_path):
    raise FileNotFoundError(f"File not found: {input_path}")

# ============================================================
# 2. OUTPUT SETTINGS — CHOOSE ONE FORMAT
# ============================================================
output_format = "GPKG"    # <-- "GPKG" or "SHP"
output_folder = r"C:\YOUR\OUTPUT\FOLDER"  # <-- EDIT THIS
# output_folder = QFileDialog.getExistingDirectory(None, "Select output folder")

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# GeoPackage output file (all layers in one .gpkg file)
output_gpkg = os.path.join(output_folder, "ftth_export.gpkg")

# ============================================================
# 3. DISCOVER ALL FOLDERS (Sublayers) IN THE KMZ/KML
# ============================================================
probe = QgsVectorLayer(input_path, "probe", "ogr")
if not probe.isValid():
    raise Exception("Failed to open the KML/KMZ file.")

sub_layers = probe.dataProvider().subLayers()
if not sub_layers:
    raise Exception("No layers found in the file.")

print(f"Found {len(sub_layers)} folder(s). Exporting to {output_format}...\n")

# ============================================================
# 4. EXPORT EACH FOLDER AS A SEPARATE LAYER
# ============================================================
saved_count = 0
first_gpkg_layer = True  # Track if GPKG file exists yet

for sub in sub_layers:
    # Extract folder name from sublayer string
    parts = sub.split(QgsDataProvider.SUBLAYER_SEPARATOR)
    folder_name = parts[1] if len(parts) >= 2 else sub
    
    if not folder_name or not folder_name.strip():
        continue
    
    # Load this specific folder as a temporary layer
    uri = f"{input_path}|layername={folder_name}"
    vlayer = QgsVectorLayer(uri, folder_name, "ogr")
    
    if not vlayer.isValid() or vlayer.featureCount() == 0:
        print(f"  Skipped: '{folder_name}' (empty or invalid)")
        continue
    
    # --- Configure save options ---
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.fileEncoding = "UTF-8"
    
    if output_format == "GPKG":
        # GeoPackage: all layers into ONE .gpkg file
        options.driverName = "GPKG"
        options.layerName = folder_name
        
        # First layer: create the GPKG file
        # Subsequent layers: add as new layer to existing GPKG
        if first_gpkg_layer:
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
            first_gpkg_layer = False
        else:
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        
        output_file = output_gpkg
        
    else:  # SHP
        # Shapefile: one .shp per folder
        options.driverName = "ESRI Shapefile"
        # Sanitize name for filesystem (remove special chars)
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in folder_name)
        output_file = os.path.join(output_folder, f"{safe_name}.shp")
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    
    # --- Write the layer to disk ---
    error, error_msg, new_filename, new_layer = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer=vlayer,
        fileName=output_file,
        transformContext=QgsCoordinateTransformContext(),
        options=options
    )
    
    if error == QgsVectorFileWriter.NoError:
        feat_count = vlayer.featureCount()
        geom_type = vlayer.geometryType()
        geom_name = {0: "Point", 1: "Line", 2: "Polygon"}.get(geom_type, "Unknown")
        print(f"  Saved:   '{folder_name}' ({feat_count} {geom_name}s)")
        saved_count += 1
    else:
        print(f"  FAILED:  '{folder_name}' — {error_msg}")

# ============================================================
# 5. SUMMARY
# ============================================================
print(f"\n{'='*60}")
print(f"Done! Successfully exported: {saved_count} layer(s)")
if output_format == "GPKG":
    print(f"Output file: {output_gpkg}")
else:
    print(f"Output folder: {output_folder}")
print(f"{'='*60}")
```

---

## What to Edit

| Line | Variable | What to Change | Example |
|---|---|---|---|
| 16 | `input_path` | Path to your KMZ or KML file | `r"D:\FTTH\network.kmz"` |
| 26 | `output_format` | Choose `"GPKG"` or `"SHP"` | `"GPKG"` (recommended) |
| 27 | `output_folder` | Folder where output files go | `r"D:\FTTH\Output"` |

---

## Output: GPKG vs SHP

| Format | Result | Best For |
|---|---|---|
| **GPKG** | One `.gpkg` file containing ALL your folders as separate tables/layers [^86^] | FTTH workflows — single file, full field names, supports all geometry types in one container |
| **SHP** | One `.shp` file **per folder** (20 folders = 20 .shp + 20 .dbf + 20 .shx + …) | Legacy systems that require Shapefile format |

**Recommendation: Use GPKG.** GeoPackage stores all 20 layers in a single file, preserves full attribute field names (no 10-character SHP limit), and is natively supported by QGIS, FiberQ, and most modern GIS tools. [^65^]

---

## How the Script Works (Step by Step)

| Step | Code Action | Explanation |
|---|---|---|
| **1. Probe** | `QgsVectorLayer(input_path, "probe", "ogr")` | Opens KMZ once via GDAL to list all `<Folder>` elements as sublayers [^73^] |
| **2. Discover** | `probe.dataProvider().subLayers()` | Returns all folder names (e.g., `"Feeder Cables"`, `"Manholes"`, `"Drop Cables"`) [^71^] |
| **3. Iterate** | `for sub in sub_layers:` | Loops through every folder — no manual picking |
| **4. Load** | `QgsVectorLayer(uri, folder_name, "ogr")` | Loads ONE folder using `\|layername=` URI syntax [^80^] |
| **5. Save** | `QgsVectorFileWriter.writeAsVectorFormatV3()` | Writes that folder to disk as SHP or as a GPKG table [^85^] |
| **6. Repeat** | Next folder | Continues until all folders are exported |

### The Critical `writeAsVectorFormatV3` Call

This is the PyQGIS method that actually writes vector data to disk. [^85^] It takes four parameters:

- **`layer`** — the `QgsVectorLayer` to save (your loaded KML folder)
- **`fileName`** — output path (`.gpkg` or `.shp`)
- **`transformContext`** — coordinate transformation settings (empty = keep original CRS)
- **`options`** — a `SaveVectorOptions` object controlling format, layer name, and overwrite behavior

The `options.actionOnExistingFile` flag is the key to GeoPackage multi-layer support: [^86^]

| Flag Value | Behavior | When to Use |
|---|---|---|
| `CreateOrOverwriteFile` | Creates a new file, or overwrites existing | First layer being saved to GPKG |
| `CreateOrOverwriteLayer` | Adds a new layer to existing file, or overwrites layer with same name | Second, third, … layers to same GPKG |

---

## Does It Work for KML Too?

**Yes — identical code.** Just change the file extension in `input_path`:

```python
input_path = r"D:\FTTH\network.kml"   # .kml works the same way
```

GDAL's KML driver handles both `.kml` and `.kmz` through the same code path. The only internal difference is that KMZ is a ZIP-compressed KML — GDAL extracts it automatically. [^73^] All sublayer discovery, URI syntax, and export behavior is identical.

---

## After Export: What You Get

### If you chose GPKG

A single file `ftth_export.gpkg` containing all your original KML folders as named layers. Open it in QGIS via **Layer → Add Layer → Add Vector Layer** and select the `.gpkg` file — QGIS will show a dialog listing all internal layers (your original folder names) for you to pick. [^65^]

Each layer retains:
- Original folder name as the layer name
- All features with original geometry (Point, LineString, Polygon)
- The `Name` field (placemark labels visible in Google Earth)
- The `Description` field (raw HTML popup content)
- Any other KML-extended data fields

### If you chose SHP

A folder full of `.shp` files, one per KML folder. Each filename is derived from the folder name (special characters sanitized to underscores). You'll also get companion files: `.dbf` (attributes), `.shx` (spatial index), `.prj` (CRS). Note that Shapefile has a **10-character field name limit** — long attribute names will be truncated. [^65^]

---

## Extracting Popup Labels After Export (FTTH Data)

Whether you exported to GPKG or SHP, the FTTH labels and popup data from your KML are stored in the `description` field as raw HTML. To turn this into queryable attribute columns, use the **KML Tools plugin** on your exported layers: [^20^]

1. Load the exported GPKG or SHP into QGIS
2. Select a layer → **Vector → KML Tools → Expand HTML Description Field**
3. Choose parsing mode (2-column table, tag=value, or tag: value)
4. Select fields to expand → OK

This creates a new layer with extracted attributes. Save that layer again to overwrite or create a final version with proper columns.
