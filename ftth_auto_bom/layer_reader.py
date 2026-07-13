"""
FTTH Auto BOM - Layer Reader
Reads QGIS layers from labeler output and extracts:
- Cable paths, pole intersections, direction changes
- Hub/block/MDU counts
Author: Mustafa M M Elaham
"""
import math
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsGeometry, QgsFeatureRequest,
    QgsPointXY, QgsSpatialIndex
)


class LayerReader:
    """Reads FTTH layers and extracts topology data for BOM calculation"""

    def __init__(self):
        self.project = QgsProject.instance()
        self.cable_layer = None
        self.pole_layer = None
        self.hub_layer = None
        self.block_layer = None
        self.mdu_layer = None

    def find_layer(self, name_pattern):
        """Find a layer by name pattern (case-insensitive partial match)"""
        for layer in self.project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                lname = layer.name().lower()
                if name_pattern.lower() in lname:
                    return layer
        return None

    def load_layers(self, cable_name="cable", pole_name="pole",
                    hub_name="hub", block_name="block", mdu_name="mdu"):
        """Auto-detect and load all required layers"""
        self.cable_layer = self.find_layer(cable_name)
        self.pole_layer = self.find_layer(pole_name)
        self.hub_layer = self.find_layer(hub_name)
        self.block_layer = self.find_layer(block_name)
        self.mdu_layer = self.find_layer(mdu_name)

        results = {
            "cable": self.cable_layer.name() if self.cable_layer else None,
            "pole": self.pole_layer.name() if self.pole_layer else None,
            "hub": self.hub_layer.name() if self.hub_layer else None,
            "block": self.block_layer.name() if self.block_layer else None,
            "mdu": self.mdu_layer.name() if self.mdu_layer else None,
        }
        return results

    def count_direction_changes(self, geometry, angle_threshold=30):
        """
        Count direction changes in a cable geometry where angle > threshold.
        Uses the QGIS expression logic:
        array_sum(array_foreach(generate_series(1, num_points-2),
            abs(degrees(azimuth(p[i],p[i+1]) - azimuth(p[i+1],p[i+2]))) > threshold))
        """
        if geometry.isMultipart():
            parts = geometry.asMultiPolyline()
        else:
            parts = [geometry.asPolyline()]

        total_changes = 0
        for part in parts:
            if len(part) < 3:
                continue
            for i in range(len(part) - 2):
                # Azimuth from point i to i+1
                az1 = math.degrees(math.atan2(part[i+1].x() - part[i].x(),
                                              part[i+1].y() - part[i].y()))
                # Azimuth from point i+1 to i+2
                az2 = math.degrees(math.atan2(part[i+2].x() - part[i+1].x(),
                                              part[i+2].y() - part[i+1].y()))
                # Angle difference
                angle_diff = abs(az1 - az2)
                if angle_diff > 180:
                    angle_diff = 360 - angle_diff
                if angle_diff > angle_threshold:
                    total_changes += 1
        return total_changes

    def count_poles_along_cable(self, cable_geom, tolerance=5.0):
        """Count how many poles a cable passes near (within tolerance meters)"""
        if not self.pole_layer or not self.pole_layer.isValid():
            return 0

        count = 0
        pole_features = self.pole_layer.getFeatures()
        for pole_feat in pole_features:
            pole_geom = pole_feat.geometry()
            if pole_geom and cable_geom.distance(pole_geom) <= tolerance:
                count += 1
        return count

    def analyze_cables(self):
        """
        Analyze all cables and return list of cable data dicts:
        {
            'feature_id', 'name', 'type', 'fibers', 'od', 'length_m',
            'poles_count', 'direction_changes', 'hub_from', 'hub_to',
            'dead_end_qty', 'tangent_qty'
        }
        """
        if not self.cable_layer or not self.cable_layer.isValid():
            return []

        cables = []
        for feat in self.cable_layer.getFeatures():
            geom = feat.geometry()
            if geom.isEmpty():
                continue

            # Get attributes - try common field names
            attrs = feat.attributes()
            fields = [f.name() for f in self.cable_layer.fields()]

            def get_attr(name, default=""):
                if name in fields:
                    return attrs[fields.index(name)]
                return default

            # Parse cable type and fiber count from name or fields
            cable_name = get_attr("name", get_attr("label", get_attr("cable", "")))
            fiber_count = self._parse_fiber_count(cable_name)
            cable_type = self._parse_cable_type(cable_name)
            cable_od = self._get_cable_od(cable_type, fiber_count)

            # Count poles and direction changes
            poles_count = self.count_poles_along_cable(geom)
            dir_changes = self.count_direction_changes(geom)
            length_m = geom.length()

            # Dead-ends = poles at cable ends (typically 2 per cable run)
            # Full pole count = all poles the cable passes
            de_qty = min(2, poles_count) if poles_count > 0 else 0
            tan_qty = poles_count if poles_count > 0 else 0

            cables.append({
                "feature_id": feat.id(),
                "name": cable_name,
                "type": cable_type,
                "fibers": fiber_count,
                "od": cable_od,
                "length_m": round(length_m, 1),
                "poles_count": poles_count,
                "direction_changes": dir_changes,
                "dead_end_qty": de_qty,
                "tangent_qty": tan_qty,
            })

        return cables

    def count_hubs(self):
        """Count total HUBs / AGs"""
        if not self.hub_layer or not self.hub_layer.isValid():
            return 0
        return self.hub_layer.featureCount()

    def count_blocks(self):
        """Count total blocks (excluding MDUs if separate layer exists)"""
        if not self.block_layer or not self.block_layer.isValid():
            return 0
        if self.mdu_layer and self.mdu_layer.isValid():
            # Blocks that are NOT MDUs
            count = 0
            for feat in self.block_layer.getFeatures():
                is_mdu = feat.attribute("is_mdu") if "is_mdu" in [f.name() for f in self.block_layer.fields()] else False
                if not is_mdu:
                    count += 1
            return count
        return self.block_layer.featureCount()

    def count_mdus(self):
        """Count total MDUs"""
        if self.mdu_layer and self.mdu_layer.isValid():
            return self.mdu_layer.featureCount()

        # If no separate MDU layer, check block layer for MDU flag
        if self.block_layer and self.block_layer.isValid():
            count = 0
            for feat in self.block_layer.getFeatures():
                is_mdu = feat.attribute("is_mdu") if "is_mdu" in [f.name() for f in self.block_layer.fields()] else False
                if is_mdu:
                    count += 1
            return count
        return 0

    def count_poles_by_type(self):
        """Count poles by type (6M, 7M, 9M) from pole layer attributes"""
        if not self.pole_layer or not self.pole_layer.isValid():
            return {"total": 0, "6m": 0, "7m": 0, "9m": 0}

        counts = {"total": 0, "6m": 0, "7m": 0, "9m": 0}
        fields = [f.name() for f in self.pole_layer.fields()]

        for feat in self.pole_layer.getFeatures():
            counts["total"] += 1

            # Try to get pole type from attributes
            pole_type = None
            for f_name in ["type", "pole_type", "height", "size", "class"]:
                if f_name in fields:
                    val = str(feat.attribute(f_name)).lower()
                    if "9" in val or "nine" in val:
                        pole_type = "9m"
                    elif "7" in val or "seven" in val:
                        pole_type = "7m"
                    elif "6" in val or "six" in val:
                        pole_type = "6m"
                    break

            if pole_type:
                counts[pole_type] += 1
            else:
                # Default: 65% 6M, 30% 7M, 5% 9M
                counts["6m"] += 1

        # If no type info, apply defaults
        if counts["6m"] == counts["total"] and counts["7m"] == 0:
            total = counts["total"]
            counts["6m"] = int(total * 0.65)
            counts["7m"] = int(total * 0.30)
            counts["9m"] = total - counts["6m"] - counts["7m"]

        return counts

    def count_total_3way_hooks(self, cables_data):
        """Total 3-way hooks = sum of direction changes across all cables"""
        return sum(c["direction_changes"] for c in cables_data)

    # === Helper methods ===

    @staticmethod
    def _parse_fiber_count(name):
        """Extract fiber count from cable name like '48F', '144F'"""
        import re
        match = re.search(r'(\d+)F', name, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 48  # default

    @staticmethod
    def _parse_cable_type(name):
        """Extract cable type from name like 'Mini ADSS', 'Slimline ADSS'"""
        name_lower = name.lower()
        if "mini" in name_lower:
            return "Mini ADSS"
        elif "slim" in name_lower:
            return "Slimline ADSS"
        elif "standard" in name_lower or "std" in name_lower:
            return "Standard ADSS"
        return "Standard ADSS"  # default

    @staticmethod
    def _get_cable_od(cable_type, fiber_count):
        """Get cable OD from database"""
        od_map = {
            ("Mini ADSS", 12): 6.3, ("Mini ADSS", 24): 6.3, ("Mini ADSS", 48): 6.3,
            ("Slimline ADSS", 12): 8.0, ("Slimline ADSS", 24): 8.0,
            ("Slimline ADSS", 48): 8.0, ("Slimline ADSS", 72): 8.0,
            ("Slimline ADSS", 144): 12.2, ("Slimline ADSS", 288): 13.6,
            ("Standard ADSS", 12): 9.6, ("Standard ADSS", 24): 9.6,
            ("Standard ADSS", 48): 10.4, ("Standard ADSS", 72): 11.2,
            ("Standard ADSS", 96): 12.8, ("Standard ADSS", 144): 15.8,
            ("Standard ADSS", 288): 18.0,
        }
        return od_map.get((cable_type, fiber_count), 9.6)
