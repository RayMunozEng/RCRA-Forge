"""
ui/scene_panel.py
Scene / level info panel for RCRA Forge.

Shows scene nodes (placed actor instances) from the currently loaded
zone asset, including world-space position and asset ID per node.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem,
    QLabel, QFrame, QTextEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont


class ScenePanel(QWidget):
    instance_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._zone = None

    # ── Public API ────────────────────────────────────────────────────────────

    def load_zone(self, zone):
        """Display scene nodes from a core.zone.ZoneDef object."""
        self._zone = zone
        self._tree.clear()
        self._info.clear()

        # Root node — zone name
        root = QTreeWidgetItem(self._tree)
        short_name = zone.name.split('/')[-1] if '/' in zone.name else zone.name
        root.setText(0, f"Scene: {short_name}")
        root.setText(1, f"{zone.entry_count} nodes")
        f = root.font(0)
        f.setPointSize(10)
        f.setWeight(QFont.Weight.Bold)
        root.setFont(0, f)
        root.setFont(1, f)
        root.setForeground(0, QColor('#5dade2'))
        root.setExpanded(True)

        for entry in zone.entries:
            item = QTreeWidgetItem(root)

            # Display name: use actor stem from path, or asset_id if blank
            display = entry.name.split('\\')[-1].replace('.actor', '') if entry.name else \
                      f'actor_{entry.asset_id:#018x}'
            item.setText(0, f"  {display}")
            item.setText(1, f"({entry.x:.1f}, {entry.y:.1f}, {entry.z:.1f})")
            row_font = item.font(0)
            row_font.setPointSize(10)
            item.setFont(0, row_font)
            item.setFont(1, row_font)
            item.setForeground(1, QColor('#aaaaaa'))
            item.setData(0, Qt.ItemDataRole.UserRole, entry)

        self._tree.resizeColumnToContents(0)
        self._status.setText(
            f"{zone.entry_count} scene node(s)  —  {short_name}"
        )

        # Info box — show asset IDs
        lines = [f"Zone: {zone.name}", f"Nodes: {zone.entry_count}", ""]
        for e in zone.entries:
            name = e.name.split('\\')[-1] if e.name else '(unnamed)'
            lines.append(f"[{e.index}] {name}")
            lines.append(f"     ID:  {e.asset_id:#018x}")
            lines.append(f"     Pos: ({e.x:.2f}, {e.y:.2f}, {e.z:.2f})")
            lines.append("")
        self._info.setPlainText('\n'.join(lines))

    def load_level(self, level_info):
        """Display info from a core.level.LevelInfo object."""
        self._tree.clear()
        root = QTreeWidgetItem(self._tree)
        root.setText(0, f"📦  {level_info.asset_type}")
        f = root.font(0)
        f.setPointSize(10)
        f.setWeight(QFont.Weight.Bold)
        root.setFont(0, f)
        root.setFont(1, f)
        root.setForeground(0, QColor('#5dade2'))
        root.setExpanded(True)
        self._info.setPlainText(level_info.description)
        self._status.setText(f"Asset type: {level_info.asset_type}")

    def load_instances(self, inst_table):
        """Stub — instance tables not yet decoded."""
        pass

    def clear(self):
        self._tree.clear()
        self._info.clear()
        self._status.setText("No zone loaded")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("BrowserHeader")
        hdr.setFixedHeight(36)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 4, 8, 4)
        title = QLabel("SCENE / ZONE")
        title.setObjectName("PanelTitle")
        hl.addWidget(title)
        layout.addWidget(hdr)

        # Tree — zone root + scene node children
        self._tree = QTreeWidget()
        self._tree.setObjectName("AssetTree")
        self._tree.setHeaderLabels(["Node", "Position"])
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setDefaultSectionSize(160)
        self._tree.setMaximumHeight(200)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

        # Info text box — shows detailed node list
        info_lbl = QLabel("  Scene nodes")
        info_lbl.setObjectName("SubPanelLabel")
        info_lbl.setFixedHeight(24)
        layout.addWidget(info_lbl)

        self._info = QTextEdit()
        self._info.setObjectName("LogBox")
        self._info.setReadOnly(True)
        self._info.setPlaceholderText(
            "Click a .zone asset in the browser to see its scene nodes.\n\n"
            "Tile zones (tile_*_gp.zone) contain placed actor instances\n"
            "with world-space positions and rotation matrices."
        )
        layout.addWidget(self._info, 1)

        # Status
        self._status = QLabel("No zone loaded")
        self._status.setObjectName("StatusLabel")
        self._status.setContentsMargins(8, 3, 8, 3)
        self._status.setFixedHeight(26)
        layout.addWidget(self._status)

    def _on_item_clicked(self, item, column):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry is not None:
            self.instance_selected.emit(entry)

