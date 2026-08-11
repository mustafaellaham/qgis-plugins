# Bulk KMZ/KML Import to QGIS for FTTH Networks: Import All Layers at Once

**Direct Answer:** Install the **KML Tools plugin** (by the U.S. National Security Agency) from the QGIS Plugin Manager. Unlike QGIS's native importer — which creates a separate layer for **every folder** inside your KMZ, causing crashes with FTTH files that contain hundreds of layers — KML Tools consolidates **all points, all lines, and all polygons** into exactly **three QGIS layers**. The original folder structure is preserved in an attribute field for filtering. After import, use **Vector → KML Tools → Expand HTML Description Field** to extract your labels/popup data into proper attribute columns, then export to SHP or GPKG format. This workflow is fully compatible with **QGIS 3.44**.

---

## 1. The Problem: Why Native QGIS Import Fails for FTTH KMZ Files

Fiber-to-the-Home (FTTH) KMZ files exported from Google Earth or engineering tools are typically organized with **dozens or hundreds of nested folders** — one for each cable segment, splitter location, manhole, drop point, boundary polygon, or route. When you drag-and-drop a KMZ into QGIS natively, or use **Layer → Add Layer → Add Vector Layer**, QGIS treats **every single folder** as a separate layer. [^2^] This behavior is hardcoded into GDAL's KML driver, which QGIS relies on for KML/KMZ reading. [^41^]

The practical consequences for FTTH workflows are severe. A typical FTTH project KMZ may contain 50–200 folders across points (manholes, poles, FTUs), lines (feeder cables, drop cables, duct routes), and polygons (design areas, administrative boundaries). Importing this natively causes three problems: **QGIS becomes extremely slow** as it attempts to create and render hundreds of individual layers; **the interface clutters** with an unusable layer panel that requires manual merging afterward; and **QGIS frequently crashes** during import when the folder count exceeds approximately 100 layers, a well-documented issue in the QGIS community. [^2^] [^20^] Even if the import succeeds, you are left with the tedious task of manually merging all point layers, all line layers, and all polygon layers separately before you can perform any meaningful analysis or export to your target format.

The native importer also **does not automatically extract structured popup data** that is embedded in the KML description field. In FTTH KMZ files, critical attributes such as cable IDs, fiber counts, splitter ratios, address information, and equipment types are typically stored as HTML tables or tag-value pairs inside each feature's description balloon. Without expansion, this data remains locked in a single unstructured text field, making it impossible to query, filter, or symbolize by attribute.

---

## 2. The Recommended Solution: KML Tools Plugin

The **KML Tools** plugin, developed and maintained by the **U.S. National Security Agency** and available through the official QGIS Plugin Repository, is purpose-built to solve the exact problem described above. [^2^] [^9^] With **578+ user votes** and active maintenance through QGIS 3.44, it is the most widely tested and reliable solution for bulk KML/KMZ import. The plugin takes a fundamentally different approach: instead of creating one layer per folder, it creates **exactly one point layer, one line layer, and one polygon layer** — regardless of how many folders exist in the source KMZ. [^20^]

The plugin preserves the organizational information by adding the **nested folder structure** as a dedicated attribute field in each QGIS layer. [^2^] This means you can still filter, sort, and symbolize features by their original folder (for example, showing only "Drop Cables" or only "Manholes") using standard QGIS attribute queries. The import is also **dramatically faster** because QGIS only needs to create and render three layers instead of hundreds. [^9^]

KML Tools also includes a second critical tool for FTTH workflows: **Expand HTML Description Field**. This tool parses the HTML popup content that Google Earth displays when you click a feature, extracting structured data such as two-column tables, "tag=value" pairs, or "tag: value" pairs into proper QGIS attribute fields. [^20^] For FTTH data where placemark popups contain equipment specifications, cable parameters, or address details, this transforms unstructured description text into queryable, filterable attribute columns.

| Feature | Native QGIS Import | KML Tools Plugin |
|---|---|---|
| **Layer creation** | One layer per folder (hundreds possible) | Exactly 3 layers (points, lines, polygons) [^2^] |
| **Import speed** | Very slow or crash with >100 folders | Fast, regardless of folder count [^20^] |
| **Folder structure** | Lost in layer names | Preserved in dedicated attribute field [^2^] |
| **Popup data extraction** | Not supported | Full HTML table and tag-value expansion [^20^] |
| **KMZ export** | Not supported | Export QGIS layers back to KMZ with styling [^9^] |
| **Ground overlay extraction** | Not supported | Convert embedded images to GeoTIFF [^9^] |
| **QGIS 3.44 compatibility** | Yes | Yes (actively maintained) [^2^] |

---

## 3. Step-by-Step Installation and Usage Guide

### 3.1 Installing the KML Tools Plugin

Open QGIS 3.44 and navigate to **Plugins → Manage and Install Plugins…**. In the search box, type **"KML Tools"** and press Enter. The plugin authored by the National Security Agency should appear at the top of the results. Click the **Install Plugin** button. [^15^] Installation takes a few seconds and does not require restarting QGIS. Once installed, the plugin adds menu entries under **Vector → KML Tools** and **Raster → KML Tools**, a toolbar icon, and Processing Toolbox algorithms under the **KML Tools** category. [^20^]

### 3.2 Importing Your KMZ File (All Layers at Once)

With the plugin installed, importing your FTTH KMZ file is straightforward. Navigate to **Vector → KML Tools → Import KML/KMZ**. A dialog window will appear with the following options: [^20^]

Click the **…** button next to **Import KML/KMZ file** and browse to your FTTH KMZ file. The file extension must be **.kml**, **.txt**, or **.kmz**. The dialog will show checkboxes for **Include point layers**, **Include line layers**, and **Include polygon layers**. Ensure **all three are checked** so that your complete FTTH network — points (manholes, poles, FTUs), lines (cables, ducts), and polygons (service areas, boundaries) — is imported simultaneously. [^9^]

Click **OK** to run the import. The plugin will process the entire KMZ and create **up to three new temporary layers** in your QGIS project: one for points, one for lines, and one for polygons. If your KMZ does not contain a particular geometry type, that layer will simply not be created. [^20^] The entire process typically completes in seconds even for large FTTH projects, compared to minutes or crashes with native import.

### 3.3 Verifying the Import and Folder Structure

Open the attribute table of any imported layer by right-clicking the layer name and selecting **Open Attribute Table**. You will see that the plugin has added a field containing the **folder path** from the original KML structure. [^2^] This field allows you to filter features by their original folder — for example, to show only features from the "Feeder Cables" folder or the "Manholes" folder — using QGIS's **Select by Expression** tool or by applying a **Layer Filter**.

The plugin also preserves the **Name** and **Description** fields from the original KML placemarks. The Name field typically contains the label you see in Google Earth (such as a cable ID or manhole number), while the Description field contains the full HTML popup content. [^15^]

### 3.4 Extracting Popup Labels into Attribute Fields (Critical for FTTH Data)

This step is essential for FTTH workflows because the structured data in your KMZ popups — cable types, fiber counts, splitter ratios, addresses — needs to become queryable attribute fields. The KML Tools plugin provides the **Expand HTML Description Field** tool specifically for this purpose. [^20^] [^30^]

Before running this tool, ensure you have already imported the KMZ using the Import KML/KMZ tool described above. Then navigate to **Vector → KML Tools → Expand HTML Description Field**. The dialog will present the following configuration options: [^20^]

For **Input layer**, select one of your imported layers (points, lines, or polygons). The **Description field** will typically auto-populate with "description". Under **How to expand the description field**, select the appropriate parsing mode based on how your FTTH data is structured:

| Parsing Mode | Use When | Example Data |
|---|---|---|
| **Expand from a 2 column HTML table** | Popup shows a table with labels in column 1 and values in column 2 [^20^] | `<tr><td>Cable Type</td><td>Drop Fiber</td></tr>` |
| **Expand from "tag = value" pairs** | Popup shows bold labels followed by "=" and values [^20^] | `<b>Cable Type</b> = Drop Fiber<br/>` |
| **Expand from "tag: value" pairs** | Popup shows bold labels followed by ":" and values [^20^] | `<b>Cable Type:</b> Drop Fiber<br/>` |

If you are unsure which format your KMZ uses, open the original file in Google Earth, click any feature, and examine the popup. Most FTTH engineering tools export data using the **two-column HTML table** format. [^30^]

Click **OK**. The tool will scan all records in the layer, identify all unique tag values, and present a dialog asking which fields you want to expand. Select all relevant fields (or click **Select All**) and click **OK** again. [^20^] The tool creates a new temporary layer with the expanded attributes. Open the attribute table to verify that your FTTH labels — cable IDs, fiber counts, equipment types, addresses — now appear as separate, properly named columns.

Repeat this process for each geometry type (points, lines, polygons) if they contain description data that needs expansion. [^15^]

### 3.5 Exporting to SHP or GPKG Format

Once your layers are imported and attributes expanded, you need to make them permanent by saving to your target format. Right-click on any temporary layer in the Layers panel and select **Export → Save Features As…**. [^51^]

In the **Save Vector Layer as…** dialog, configure the following: [^51^]

- **Format**: Select **GeoPackage** for a modern, single-file format that supports multiple layers and preserves all field names without the 10-character limit of Shapefiles. Select **ESRI Shapefile** only if your downstream workflow specifically requires it.
- **File name**: Browse to your desired output location and enter a filename.
- **Layer name**: If using GeoPackage, enter a meaningful layer name such as "ftth_points", "ftth_lines", or "ftth_polygons".
- **CRS**: The default **EPSG:4326 (WGS 84)** is appropriate for most FTTH data since KML/KMZ uses this coordinate system by default. If your project requires a different CRS (such as a UTM zone or national grid), click the CRS selector and choose accordingly.
- **Geometry type**: Set to **Automatic** to preserve the original geometry type.
- **Fields**: Ensure all expanded attribute fields are checked for export.

Click **OK** to save. Repeat for each of the three geometry types. If using GeoPackage, you can save all three layers (points, lines, polygons) into a single **.gpkg** file by specifying the same filename each time and using different layer names — GeoPackage supports multiple layers within one container file. [^65^]

---

## 4. Alternative Method: Command-Line Batch Conversion with ogr2ogr

For users who need to process **multiple KMZ files in batch** or prefer a scriptable approach, the **ogr2ogr** command-line tool (included with every QGIS installation via GDAL/OGR) offers a powerful alternative. [^19^] [^59^] This method converts KMZ directly to GeoPackage without opening QGIS, making it suitable for automated workflows or processing large file collections.

### 4.1 Single File Conversion

Open the **OSGeo4W Shell** (installed with QGIS on Windows) or any terminal (Linux/Mac) and navigate to the folder containing your KMZ file. Run the following command: [^29^] [^65^]

```bash
ogr2ogr -f GPKG output_ftth.gpkg input_ftth.kmz
```

This command reads all layers from the KMZ and writes them into a single GeoPackage file. Each folder in the original KML becomes a separate table within the GeoPackage. The **-f GPKG** flag specifies the output format, and the input filename can use either **.kmz** or **.kml** extension.

### 4.2 Batch Converting Multiple KMZ Files

To process an entire folder of FTTH KMZ files, use the following approach. First, create a single GeoPackage from all files in a directory: [^29^]

```bash
ogr2ogr -f GPKG combined_ftth.gpkg ./path/to/kmz_files/
```

Or, to convert all KMZ files matching a wildcard pattern: [^29^]

```bash
ogr2ogr -f GPKG combined_ftth.gpkg ./path/to/kmz_files/*.kmz
```

For **Windows users**, a batch loop can process all KMZ files in a folder and convert each to a separate GeoPackage:

```batch
for %f in (*.kmz) do ogr2ogr -f GPKG "%~nf.gpkg" "%f"
```

For **Linux/Mac users**, the equivalent shell loop is:

```bash
for f in *.kmz; do ogr2ogr -f GPKG "${f%.kmz}.gpkg" "$f"; done
```

### 4.3 Filtering by Geometry Type

If your downstream workflow requires separating geometry types (similar to what KML Tools does automatically), use the **-where** clause with OGR's geometry filter: [^29^]

```bash
# Extract only points
ogr2ogr -f GPKG ftth_points.gpkg input.kmz -where "OGR_GEOMETRY='Point'" -nlt POINT

# Extract only lines
ogr2ogr -f GPKG ftth_lines.gpkg input.kmz -where "OGR_GEOMETRY='LineString'" -nlt LINESTRING

# Extract only polygons
ogr2ogr -f GPKG ftth_polygons.gpkg input.kmz -where "OGR_GEOMETRY='Polygon'" -nlt POLYGON
```

### 4.4 Limitations of the ogr2ogr Approach

While ogr2ogr is powerful for format conversion, it has important limitations compared to the KML Tools plugin for FTTH workflows. The ogr2ogr command **does not expand HTML description fields** — the popup data remains embedded as raw HTML in a single description column. [^19^] Extracting structured attributes from this HTML requires additional post-processing, either through QGIS's Field Calculator with regular expressions, a Python script using BeautifulSoup, or manual extraction. Additionally, ogr2ogr creates **one output table per KML folder**, so you may still end up with dozens of tables in your GeoPackage rather than the consolidated three-layer structure that KML Tools provides. [^41^]

| Method | Best For | Pros | Cons |
|---|---|---|---|
| **KML Tools Plugin** | Interactive FTTH workflows, attribute extraction | GUI-based, expands HTML popups, consolidates to 3 layers, preserves folder structure as field [^2^] | Requires QGIS GUI, processes one file at a time |
| **ogr2ogr** | Batch processing, scripted workflows, automation | Command-line, no QGIS needed, processes folders/wildcards [^19^] | No HTML popup expansion, creates many tables, requires post-processing for attributes |
| **Native QGIS Drag-Drop** | Quick preview of small KML files | Simplest method, no plugin needed | Crashes with many folders, no attribute expansion, creates hundreds of layers [^2^] |

---

## 5. Method Comparison and Recommendations for FTTH Workflows

Based on extensive testing and community feedback, the following decision framework will help you choose the right approach for your specific FTTH workflow: [^15^] [^30^]

For **single KMZ files with rich popup data** (the most common FTTH scenario), the **KML Tools plugin is the clear winner**. It handles the complete workflow — import all geometry types simultaneously, preserve folder structure, extract HTML popup attributes, and export to SHP/GPKG — entirely within QGIS with no additional tools. The folder structure field allows you to reconstruct logical groupings (such as "Feeder Cables" vs. "Drop Cables") using QGIS's built-in filtering and symbology tools.

For **batch processing of multiple KMZ files** (for example, processing monthly survey updates from field teams), a **hybrid approach** works best. Use **ogr2ogr** to convert all KMZ files to GeoPackage format overnight or via a scheduled script, then open the resulting GeoPackage(s) in QGIS and use the KML Tools **Expand HTML Description Field** tool on each layer to extract the popup data. This combines the automation of command-line processing with the attribute extraction power of the plugin.

For **FTTH projects using the FiberQ plugin** (a dedicated FTTH network design plugin for QGIS), note that FiberQ supports importing existing points and lines directly into its structured project layers. [^27^] If your end goal is FTTH network design rather than simple data conversion, consider using FiberQ's native import capabilities after converting your KMZ to GeoPackage format. FiberQ uses GeoPackage as its native project format, so the output from either KML Tools or ogr2ogr integrates directly.

---

## 6. Troubleshooting Common Issues

| Issue | Cause | Solution |
|---|---|---|
| **QGIS crashes during KMZ import** | Native importer creating too many layers [^2^] | Use KML Tools plugin instead of drag-and-drop |
| **Description field shows raw HTML** | Popup data not expanded | Run Vector → KML Tools → Expand HTML Description Field [^20^] |
| **Only one geometry type imported** | Unchecked geometry type checkboxes | Re-import with all three geometry types checked [^9^] |
| **Field names truncated in SHP** | Shapefile 10-character field name limit | Use GeoPackage format instead [^65^] |
| **KML Tools not found in Plugin Manager** | Repository not refreshed | Click "Reload Repository" in Plugin Manager settings |
| **Expanded fields have "_1" suffix** | Name collision with existing field | The plugin auto-renames; manually rename in layer properties if needed [^20^] |
| **Missing attributes after expansion** | Unsupported HTML format | Check your KMZ popup format in Google Earth; contact plugin authors if needed [^20^] |
| **Slow export to Shapefile** | Large number of features | Use GeoPackage with spatial indexing; add `-lco SPATIAL_INDEX=YES` for ogr2ogr [^65^] |

---

## 7. Key Takeaways

The **KML Tools plugin** is the most reliable, tested, and FTTH-appropriate solution for importing complex KMZ files into QGIS 3.44. Its ability to consolidate all folders into three geometry layers while preserving folder structure as an attribute field solves the core performance and usability problem that plagues native QGIS import. The **Expand HTML Description Field** tool is equally critical for FTTH workflows, transforming embedded popup data into queryable attributes. For batch processing, **ogr2ogr** provides a command-line complement that integrates well with automated workflows, though it requires additional steps for attribute extraction. Regardless of the method chosen, **GeoPackage is the recommended output format** for FTTH data due to its single-file portability, multi-layer support, full field name preservation, and native compatibility with both QGIS and the FiberQ FTTH design plugin. [^27^] [^65^]
