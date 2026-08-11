# -*- coding: utf-8 -*-
"""Layer Mapping Dialog — assign QGIS layers to BOM roles without renaming."""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QComboBox, QLabel, QPushButton, QHBoxLayout,
    QScrollArea, QFrame, QWidget
)
from qgis.core import QgsProject, QgsMapLayer


# Each tuple: (display_name, tooltip, alternative_search_keywords)
ROLE_DEFINITIONS = [
    ("Block polygons",      "Polygon: FTTH blocks",               "block polygon"),
    ("Core_Aggregation",    "Point: core manholes / CAGs",        "core aggregation"),
    ("core_cable",          "Line: core cables 144F/288F",        "core routing core cable"),
    ("Poles",               "Point: all poles",                   "pole"),
    ("Distribution",        "Line: distribution cables 1F",       "distribution drops"),
    ("Distributions joints","Point: distribution joints DJs",     "distribution joint dj"),
    ("Feeder",              "Line: feeder cables 48F/72F",        "feeder cable"),
    ("Feeder_aggregation",  "Point: feeder aggregation nodes",    "feeder joint"),
    ("Link_Aggregation",    "Point: link aggregation nodes",      "link joint"),
    ("links",               "Line: link cables 24F",              "link link cable"),
    ("Premise data",        "Point: premises / homes",            "premise premise data"),
    ("POP",                 "Point: POP / CO",                    "pop"),
    ("Aggregation_polygons","Polygon: aggregation areas",         "aggregation polygon"),
]


class LayerMappingDialog(QDialog):
    def __init__(self, iface, previous_mapping=None):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.previous_mapping = previous_mapping or {}
        self.role_combos = {}
        self.setWindowTitle("Step 0: Map Layers to BOM Roles")
        self.setModal(True)
        self.setMinimumSize(650, 550)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        layout.addWidget(QLabel(
            "<b>Assign each QGIS layer to its BOM role.</b><br>"
            "<small>No renaming needed — pick from each dropdown. "
            "Green = pre-selected by keyword match. Leave as 'skip' if not needed.</small>"
        ))

        project = QgsProject.instance()
        all_layers = []
        for lid, layer in project.mapLayers().items():
            all_layers.append((lid, layer.name(), layer.type()))

        all_layers.sort(key=lambda x: x[1].lower())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)

        for role, description, alias in ROLE_DEFINITIONS:
            frame = QFrame()
            frame.setFrameStyle(QFrame.StyledPanel)
            row_layout = QHBoxLayout(frame)

            label = QLabel(f"<b>{role}</b><br><small>{description}</small>")
            label.setMinimumWidth(220)
            row_layout.addWidget(label)

            combo = QComboBox()
            combo.addItem("-- skip --", None)

            preselected_index = 0
            preselected_score = 0
            for i, (lid, lname, ltype) in enumerate(all_layers):
                icon_hint = "[V]" if ltype == QgsMapLayer.VectorLayer else "[R]"
                combo.addItem(f"{icon_hint} {lname}", lid)

                # Match: role name keywords OR alias keywords — at least 50% must hit
                kw_role = role.lower().replace("_", " ").split()
                kw_alias = alias.lower().replace("_", " ").split()
                ln = lname.lower()
                role_hits = sum(1 for kw in kw_role if kw in ln) / max(1, len(kw_role))
                alias_hits = sum(1 for kw in kw_alias if kw in ln) / max(1, len(kw_alias))
                score = max(role_hits, alias_hits)
                # Tiebreaker: prefer exact name match (+0.1 bonus)
                if ln == role.lower():
                    score += 0.1
                if score >= 0.5 and score > preselected_score:
                    preselected_score = score
                    preselected_index = i + 1

            prev_lid = self.previous_mapping.get(role)
            if prev_lid:
                for i, (lid, lname, ltype) in enumerate(all_layers):
                    if lid == prev_lid:
                        preselected_index = i + 1
                        break

            if preselected_index > 0:
                combo.setCurrentIndex(preselected_index)

            combo.setMinimumWidth(380)
            row_layout.addWidget(combo)
            container_layout.addWidget(frame)
            self.role_combos[role] = combo

        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def get_mapping(self):
        mapping = {}
        project = QgsProject.instance()
        for role, combo in self.role_combos.items():
            lid = combo.currentData()
            mapping[role] = project.mapLayer(lid) if lid else None
        return mapping

    def get_mapping_summary(self):
        summary = {}
        for role, combo in self.role_combos.items():
            text = combo.currentText()
            summary[role] = text if text != "-- skip --" else "(skipped)"
        return summary
