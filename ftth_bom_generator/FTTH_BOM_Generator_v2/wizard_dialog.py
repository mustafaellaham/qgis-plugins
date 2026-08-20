# -*- coding: utf-8 -*-
"""Wizard v2.7 — Project Code field; multi-option dropdowns; CRS-safe Tab 4."""

import re, math
from collections import defaultdict
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QTableWidget, QTableWidgetItem, QComboBox,
    QCheckBox, QHeaderView, QGroupBox, QScrollArea, QRadioButton, QButtonGroup
)
from qgis.PyQt.QtCore import Qt


class WizardDialogV2b(QDialog):
    def __init__(self, iface, generator, config):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.gen = generator
        self.config = config
        self.answers = {}
        self.setWindowTitle("BOM Wizard v2.6")
        self.setModal(True)
        self.setMinimumSize(1050, 780)
        self.setup_ui()
        self.populate_data()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()

        t1 = QWidget(); v1 = QVBoxLayout(t1)
        v1.addWidget(QLabel("<b>Project Information</b>"))
        self.proj_name = QLineEdit(); self.proj_code = QLineEdit(); self.customer = QLineEdit()
        v1.addWidget(QLabel("Project Name:")); v1.addWidget(self.proj_name)
        v1.addWidget(QLabel("Project Code:")); v1.addWidget(self.proj_code)
        v1.addWidget(QLabel("Customer:")); v1.addWidget(self.customer)
        v1.addStretch(); self.tabs.addTab(t1, "1. Project Info")

        t2 = QWidget(); self.v2 = QVBoxLayout(t2)
        self.v2.addWidget(QLabel(
            "<b>Cable Scanner — All Options per Fiber</b><br>"
            "<small>Select one option per fiber group from the full Cables Options sheet.</small>"
        ))
        self.tab2_scroll = QScrollArea(); self.tab2_scroll.setWidgetResizable(True)
        self.tab2_container = QWidget(); self.tab2_layout = QVBoxLayout(self.tab2_container)
        self.tab2_scroll.setWidget(self.tab2_container)
        self.v2.addWidget(self.tab2_scroll)
        self.tabs.addTab(t2, "2. Cable Scanner")

        t3 = QWidget(); v3 = QVBoxLayout(t3)
        v3.addWidget(QLabel("<b>Joint Type per Manhole</b><br><small>Select ONE type per MH.</small>"))
        self.tab3_scroll = QScrollArea(); self.tab3_scroll.setWidgetResizable(True)
        self.tab3_container = QWidget(); self.tab3_layout = QVBoxLayout(self.tab3_container)
        self.tab3_scroll.setWidget(self.tab3_container)
        v3.addWidget(self.tab3_scroll)
        self.tabs.addTab(t3, "3. Joint Types")

        t4 = QWidget(); v4 = QVBoxLayout(t4)
        v4.addWidget(QLabel(
            "<b>Cable-Joint Matrix</b><br>"
            "<small><b>Express</b> = OVAL PORT KIT. <b>Terminated</b> = MECH SEAL / GLAND.</small>"
        ))
        self.tab4_scroll = QScrollArea(); self.tab4_scroll.setWidgetResizable(True)
        self.tab4_container = QWidget(); self.tab4_layout = QVBoxLayout(self.tab4_container)
        self.tab4_scroll.setWidget(self.tab4_container)
        v4.addWidget(self.tab4_scroll)
        self.tabs.addTab(t4, "4. Cable-Joint Matrix")

        # Rebuild Tab 4 on every visit so it shows the CURRENT Tab 2 OD choices
        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tabs)
        btn = QHBoxLayout(); btn.addStretch()
        self.finish_btn = QPushButton("Finish"); self.finish_btn.clicked.connect(self.accept)
        btn.addWidget(self.finish_btn)
        layout.addLayout(btn)
        self.setLayout(layout)

    def _pf(self, name):
        m = re.search(r'(\d+)F', name); return m.group(1) if m else '?'

    # ════════════════════════════════════════════════════════
    #  POPULATE ALL TABS
    # ════════════════════════════════════════════════════════
    def populate_data(self):
        self._populate_tab2()
        self._populate_tab3()
        self._populate_tab4()

    # ── TAB 2: Multi-option dropdowns from _cable_options ──
    def _populate_tab2(self):
        v = self.gen.v
        cable_names = v.get('cable_names_by_fiber', {})
        cable_lengths = v.get('cable_lengths', {})
        all_opts = self.config.get('_cable_options', [])

        fibers = sorted(cable_lengths.keys(), key=lambda x: int(x) if x.isdigit() else 0)
        self.fiber_type_combos = {}
        self.fiber_option_indices = {}

        for fiber in fibers:
            total_len = cable_lengths[fiber]
            names = cable_names.get(fiber, [])

            # Get all options for this fiber
            fiber_opts = [o for o in all_opts if o['fiber'] == fiber]

            group = QGroupBox(f"{fiber}F Cables — Qty: {total_len}m ({len(names)} cables)")
            gl = QVBoxLayout(group)

            type_row = QHBoxLayout()
            type_row.addWidget(QLabel("Option:"))

            combo = QComboBox()
            if not fiber_opts:
                combo.addItem("No options in spec", -1)
            else:
                for idx, opt in enumerate(fiber_opts):
                    combo.addItem(opt['label'], idx)

            # Smart preselect: match cable name
            best_i = 0
            for i, opt in enumerate(fiber_opts):
                hits = sum(1 for n, r, l in names if opt['type'].lower() in n.lower())
                if hits > 0: best_i = i; break
            # Default: Slim for 72/96/144/288, Mini for 24/48
            if fiber in ('288','144','72','96') and not any(
                any(opt['type'].lower() in n.lower() for n, r, l in names)
                for opt in fiber_opts):
                for i, opt in enumerate(fiber_opts):
                    if opt['type'] == 'Slim': best_i = i; break
            elif fiber in ('48','24','12'):
                for i, opt in enumerate(fiber_opts):
                    if opt['type'] == 'Mini': best_i = i; break

            combo.setCurrentIndex(best_i)
            combo.setMinimumWidth(350)
            type_row.addWidget(combo); type_row.addStretch()
            gl.addLayout(type_row)
            self.fiber_type_combos[fiber] = combo

            sample_label = QLabel(f"<small>e.g. {names[0][0][:80] if names else 'N/A'}</small>")
            sample_label.setWordWrap(True); gl.addWidget(sample_label)
            self.tab2_layout.addWidget(group)
        self.tab2_layout.addStretch()

    # ── TAB 3: Radio buttons ──
    def _populate_tab3(self):
        ca_layer = self.gen._L('Core_Aggregation')
        self._mh_joint_groups = {}
        if not ca_layer: return
        for f in ca_layer.getFeatures():
            name = f['Name'] or f"MH_{f.id()}"
            g = f.geometry()
            if not g or g.isNull(): continue
            if g.type() == 2: g = g.centroid()
            group = QGroupBox(f"Manhole: {name}")
            gb = QHBoxLayout(group)
            bg = QButtonGroup(self)
            for jt in ['LMJ','MMJ','ODC FD4','ODC FD6']:
                rb = QRadioButton(jt)
                if jt == 'LMJ': rb.setChecked(True)
                bg.addButton(rb); gb.addWidget(rb)
            gb.addStretch()
            self._mh_joint_groups[name] = bg
            self.tab3_layout.addWidget(group)
        self.tab3_layout.addStretch()

    # ── TAB 4: Cable-Joint Matrix ──
    def _on_tab_changed(self, i):
        """Repopulate Tab 4 on every visit so OD labels follow the CURRENT
        Tab 2 selections. Existing Express/Terminated ticks are preserved."""
        if i != 3: return
        saved = {}
        for mh_name, checks in getattr(self, '_tab4_express', {}).items():
            saved[mh_name] = {c: ce.isChecked() for c, (ce, ct) in checks.items()}
        while self.tab4_layout.count():
            item = self.tab4_layout.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        self._populate_tab4(saved)

    def _populate_tab4(self, saved=None):
        saved = saved or {}
        ca_layer = self.gen._L('Core_Aggregation')
        if not ca_layer: return

        all_cables = []
        # Distribution included: multi-fiber (>1F) DC cables are conventional
        for role in ['core_cable','Feeder','links','Distribution']:
            l = self.gen._L(role)
            if not l: continue
            for f in l.getFeatures():
                g = f.geometry()
                if not g or g.isNull(): continue
                name = f['Name'] or ''
                fiber = self._pf(name)
                if fiber in ('1','?'): continue
                # Use the CURRENT Tab 2 combo selection for this fiber group
                combo = self.fiber_type_combos.get(fiber)
                idx = combo.currentData() if combo is not None else None
                fiber_opts = [o for o in self.config.get('_cable_options', [])
                              if o['fiber'] == fiber]
                if idx is not None and 0 <= idx < len(fiber_opts):
                    opt = fiber_opts[idx]
                else:
                    opt = self.gen._get_od_full(name, fiber)
                od = opt.get('od', 0)
                if od == 0: continue
                all_cables.append((name, fiber, opt, od, self.gen._g(l, g), role))

        self._tab4_express = {}
        DIST = 10.0  # meters (geometries are in the metric working CRS)

        mh_list = []
        for f in ca_layer.getFeatures():
            g = f.geometry()
            if not g or g.isNull(): continue
            g = self.gen._g(ca_layer, g)
            if g.type() == 2: g = g.centroid()
            mh_list.append((f['Name'] or f"MH_{f.id()}", g))

        for mh_name, mh_geom in mh_list:
            nearby = []
            for cname, fiber, opt, od, cg, role in all_cables:
                if cg.distance(mh_geom) <= DIST:
                    nearby.append((cname, fiber, opt, od, role))
            if not nearby: continue

            group = QGroupBox(f"MH: {mh_name} — {len(nearby)} cables within 10m")
            gl = QVBoxLayout(group)

            table = QTableWidget(len(nearby), 3)
            table.setHorizontalHeaderLabels(["Cable", "Express (OVAL)", "Terminated (GLAND)"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

            self._tab4_express[mh_name] = {}
            for r, (cname, fiber, opt, od, role) in enumerate(nearby):
                lbl = opt.get('label', f'{fiber}F')
                item = QTableWidgetItem(f"{cname[:60]} | {fiber}F | {lbl} | OD={od}mm")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(r, 0, item)

                chk_exp = QCheckBox()
                chk_term = QCheckBox()
                # DEFAULT: all Terminated. Restore saved ticks on rebuild.
                was_express = saved.get(mh_name, {}).get(cname)
                chk_exp.setChecked(was_express is True)
                chk_term.setChecked(was_express is not True)
                table.setCellWidget(r, 1, chk_exp)
                table.setCellWidget(r, 2, chk_term)
                self._tab4_express[mh_name][cname] = (chk_exp, chk_term)

            gl.addWidget(table)
            self.tab4_layout.addWidget(group)
        self.tab4_layout.addStretch()

    # ════════════════════════════════════════════════════════
    #  GET ANSWERS
    # ════════════════════════════════════════════════════════
    def _validate_and_accept(self):
        """Block Finish if sum(joint types) != core_aggs."""
        ca_layer = self.gen._L('Core_Aggregation')
        core_aggs = ca_layer.featureCount() if ca_layer else 0
        
        total_joints = 0
        for mh_name, bg in getattr(self, '_mh_joint_groups', {}).items():
            btn = bg.checkedButton()
            if btn:
                total_joints += 1
        
        if total_joints != core_aggs:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(self,
                "Joint Count Mismatch",
                f"Total joint assignments ({total_joints}) must equal number of manholes ({core_aggs}).\n"
                f"Please check Tab 3 — each manhole must have exactly one joint type selected."
            )
            return
        self.accept()

    def get_answers(self):
        a = {
            'project_name': self.proj_name.text(),
            'project_code': self.proj_code.text(),
            'customer': self.customer.text(),
            'cable_option_indices': {},
            'joint_type_counts': {'LMJ': 0, 'MMJ': 0, 'ODC FD4': 0, 'ODC FD6': 0},
            'express_cables': {},
        }

        # Store selected option INDEX per cable (config-driven)
        for fiber, combo in self.fiber_type_combos.items():
            idx = combo.currentData()
            if idx is not None and idx >= 0:
                for name, role, length in self.gen.v.get('cable_names_by_fiber', {}).get(fiber, []):
                    a['cable_option_indices'][f"{fiber}||{name}"] = idx

        for mh_name, bg in getattr(self, '_mh_joint_groups', {}).items():
            btn = bg.checkedButton()
            if btn: a['joint_type_counts'][btn.text()] = a['joint_type_counts'].get(btn.text(), 0) + 1

        for mh_name, checks in getattr(self, '_tab4_express', {}).items():
            for cname, (chk_exp, chk_term) in checks.items():
                if chk_exp.isChecked():
                    a['express_cables'][f"{mh_name}||{cname}"] = True

        return a
