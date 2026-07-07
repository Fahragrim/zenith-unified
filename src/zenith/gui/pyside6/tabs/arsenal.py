"""Arsenal tab — searchable DEEP_ATLAS knowledge base."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ArsenalTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup()
        self._load()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Knowledge Arsenal", objectName="title"))
        layout.addWidget(QLabel("Browse DEEP_ATLAS: SoCs, protocols, playbooks, tools, secret codes.",
                                property="class"))

        # Search
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search: qualcomm, bootloop, edl, secret codes...")
        self.search_input.returnPressed.connect(self._search)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        # Stats
        self.stats_lbl = QLabel()
        layout.addWidget(self.stats_lbl)

        # Tree + detail tabs
        grp = QGroupBox("Knowledge Base")
        gl = QVBoxLayout(grp)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Name", "Details"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 250)
        self.tree.itemClicked.connect(self._on_item_clicked)
        gl.addWidget(self.tree, 3)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(200)
        gl.addWidget(self.detail)
        layout.addWidget(grp, 1)

    def _load(self) -> None:
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            d = kb.data
            self.stats_lbl.setText(f"SoCs: {len(d.socs)}  Protocols: {len(d.protocols)}  "
                                   f"Playbooks: {len(d.playbooks)}  Tools: {len(d.tools)}  "
                                   f"Secret codes: {sum(len(v) for v in d.secret_codes.values())}")
            self.tree.clear()

            socs_item = QTreeWidgetItem(["SoCs"])
            for k, v in sorted(d.socs.items()):
                QTreeWidgetItem(socs_item, [k, v.name, v.manufacturer])
            self.tree.addTopLevelItem(socs_item)

            proto_item = QTreeWidgetItem(["Protocols"])
            for k, v in sorted(d.protocols.items()):
                QTreeWidgetItem(proto_item, [k, v.name, f"risk: {v.risk_level} | {len(v.commands)} commands"])
            self.tree.addTopLevelItem(proto_item)

            pb_item = QTreeWidgetItem(["Playbooks"])
            for k, v in sorted(d.playbooks.items()):
                QTreeWidgetItem(pb_item, [k, v.title, f"risk: {v.risk_level} | symptom: {v.symptom}"])
            self.tree.addTopLevelItem(pb_item)

            tools_item = QTreeWidgetItem(["Tools"])
            for k, v in sorted(d.tools.items()):
                QTreeWidgetItem(tools_item, [k, v.name, v.function or v.category])
            self.tree.addTopLevelItem(tools_item)

            codes_item = QTreeWidgetItem(["Secret Codes"])
            for manufacturer, codes in sorted(d.secret_codes.items()):
                man_item = QTreeWidgetItem(codes_item, [manufacturer, "", ""])
                for code, func in codes.items():
                    QTreeWidgetItem(man_item, ["", code, func])
            self.tree.addTopLevelItem(codes_item)

            self.tree.expandAll()
        except Exception as e:
            self.tree.clear()
            self.tree.addTopLevelItem(QTreeWidgetItem([f"Error loading arsenal: {e}"]))

    def _search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self._load()
            return
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            result = kb.search(query)
            lines = []
            for category, items in result.items():
                if items:
                    lines.append(f"\n[{category.upper()}]")
                    for item in items:
                        lines.append(f"  {item}")
            self.detail.setText("\n".join(lines) if lines else f"No results for '{query}'")
        except Exception as e:
            self.detail.setText(f"Search error: {e}")

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int) -> None:
        if item.childCount() > 0:
            return
        parent = item.parent()
        if parent is None:
            return
        category = parent.text(0)
        name = item.text(0) or item.text(1)
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            if category == "SoCs":
                soc = kb.get_soc(name)
                if soc:
                    lines = [f"=== {soc.name} ({soc.manufacturer}) ===", "",
                             f"Boot chain: {' → '.join(soc.boot_chain) if soc.boot_chain else 'N/A'}",
                             f"Recovery modes: {', '.join(soc.recovery_modes) if soc.recovery_modes else 'N/A'}",
                             f"Tools: {', '.join(soc.tools) if soc.tools else 'N/A'}",
                             f"Security: {', '.join(soc.security_features) if soc.security_features else 'N/A'}"]
                    self.detail.setText("\n".join(lines))
            elif category == "Protocols":
                proto = kb.get_protocol(name)
                if proto:
                    lines = [f"=== {proto.name} ===", "", proto.description,
                             f"SOC families: {', '.join(proto.soc_families)}",
                             f"USB: {proto.usb_vid or 'N/A'}:{proto.usb_pid or 'N/A'}",
                             f"Risk: {proto.risk_level}", "",
                             "Commands:"] + [f"  {c}" for c in proto.commands]
                    self.detail.setText("\n".join(lines))
            elif category == "Playbooks":
                pb = kb.get_playbook(name)
                if pb:
                    lines = [f"=== {pb.title} ===", "", f"Symptom: {pb.symptom} | SOC: {pb.soc or 'any'} | Risk: {pb.risk_level}"]
                    for s in pb.steps:
                        lines.append(f"  {s.get('step', s.get('step_number', '?'))}. {s.get('description', s.get('desc', ''))}")
                    self.detail.setText("\n".join(lines))
        except Exception as e:
            self.detail.setText(f"Detail error: {e}")
