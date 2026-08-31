"""
ui/asset_browser.py
Left-panel game-asset browser for RCRA Forge.

Shows plainly labelled, searchable Rift Apart assets and model groups. Emits
signals when the user selects an asset to preview or export.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QPushButton, QLabel, QComboBox, QFrame, QSizePolicy,
    QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, QObject, QEvent
from PyQt6.QtGui import QIcon, QColor, QFont

from core.archive import AssetEntry, ASSET_TYPE_NAMES
from core.grouping import build_groups, build_model_families, filter_groups, AssetGroup


# Type → accent color (hex) for the tree
TYPE_COLORS = {
    'MESH': '#5dade2',
    'TXTR': '#a9cce3',
    'LEVL': '#a8d8a8',
    'INST': '#c9b8e8',
    'MATL': '#f7dc6f',
    'ANIM': '#f0a500',
    'SKEL': '#e8907a',
    'COLL': '#95a5a6',
}

MODEL_CATEGORY_ORDER = (
    "Planets & locations",
    "Enemies",
    "Heroes & playable characters",
    "Weapons & gadgets",
    "NPCs & civilians",
    "Vehicles",
    "Props & gameplay objects",
    "Visual effects",
    "Cinematics & UI",
    "Other models",
)

PLANET_LOCATION_ORDER = (
    "Corson V · Nefarious City",
    "Sargasso",
    "Scarstu Debris Field · Zurkie's",
    "Savali",
    "Blizar Prime",
    "Torren IV",
    "Cordelion",
    "Ardolis",
    "Viceron · Zordoom Prison",
    "Shared environments",
)


def _classify_model_path(path: str) -> tuple[str, str | None]:
    """Map a game model path to a user-facing semantic category."""
    path = (path or "").replace('\\', '/').casefold()
    filename = path.rsplit('/', 1)[-1]

    # Source domain wins over filename prefixes. A mesh named after Ratchet in
    # a visual-effect or cinematic path is an effect/scene piece, not a playable
    # character model.
    if path.startswith(("visualeffect/", "visualeffects/")) or path.startswith("objects/fx/"):
        return "Visual effects", None
    if path.startswith(("cinematics/", "ui/")) or path.startswith("models/ui/"):
        return "Cinematics & UI", None

    if path.startswith("characters/enemy/") or filename.startswith("enm_"):
        return "Enemies", None
    if path.startswith("characters/hero/") or filename.startswith("hero_"):
        return "Heroes & playable characters", None
    if (
        path.startswith("characters/weapon/")
        or path.startswith("characters/gadgets/")
        or path.startswith("equipment/")
        or "/weapon/" in path
        or filename.startswith(("wpn_", "weapon_"))
    ):
        return "Weapons & gadgets", None
    if path.startswith(("characters/npc/", "characters/civilians/", "characters/ambient/")):
        return "NPCs & civilians", None
    if path.startswith("vehicle/") or "/vehicle/" in path or filename.startswith("veh_"):
        return "Vehicles", None
    environment_roots = (
        "environment/", "levels/", "procedural/", "prefabs/", "atmosphere/",
        "atmospheres/", "instance/",
    )
    if path.startswith(environment_roots):
        location_rules = (
            (("sargasso",), "Sargasso"),
            (("savali",), "Savali"),
            (("ardolis",), "Ardolis"),
            (("blizar",), "Blizar Prime"),
            (("cordelion", "underwaterbase"), "Cordelion"),
            (("molonoth", "torren"), "Torren IV"),
            (("zordoom", "viceron"), "Viceron · Zordoom Prison"),
            (("zurkonpub", "zurkons", "scarstu"), "Scarstu Debris Field · Zurkie's"),
            (("i20_city", "megalopolis", "neonefarious", "corson"), "Corson V · Nefarious City"),
        )
        for tokens, label in location_rules:
            if any(token in path for token in tokens):
                return "Planets & locations", label
        return "Planets & locations", "Shared environments"

    if path.startswith(("objects/", "characters/prop/", "models/manmade", "models/design/")):
        return "Props & gameplay objects", None
    return "Other models", None


class SearchWorker(QObject):
    """Runs asset name scanning on a background thread."""
    results_ready = pyqtSignal(int, list, str)   # (generation, matched_indices, ext_flt)
    error         = pyqtSignal(int, str)

    def __init__(self, entries, lookup, tokens, raw_text: str, ext_flt, generation: int):
        super().__init__()
        self.entries  = entries
        self.lookup   = lookup
        self.tokens   = tokens
        self.raw_text = raw_text
        self.ext_flt  = ext_flt
        self.generation = generation

    def run(self):
        try:
            import numpy as np
            from core.archive import _LazyEntryList

            entries  = self.entries
            lookup   = self.lookup
            tokens   = self.tokens
            raw_text = self.raw_text
            ext_flt  = self.ext_flt

            matched_indices = []

            if raw_text:
                # 1. Exact hex ID match
                hex_matched = False
                if len(tokens) == 1:
                    try:
                        search_id = int(raw_text, 16)
                        ids_arr   = entries._ids[:len(entries)]
                        hits = np.where(ids_arr == search_id)[0].tolist()
                        if hits:
                            matched_indices = hits
                            hex_matched = True
                    except (ValueError, AttributeError):
                        pass

                if not hex_matched:
                    # Multi-token AND match: every token must appear in the path.
                    # Tokens are already correctly built by _apply_filter.
                    ids_arr = entries._ids[:len(entries)] if isinstance(entries, _LazyEntryList) else None

                    n = len(entries)
                    for i in range(n):
                        if i % 4096 == 0 and QThread.currentThread().isInterruptionRequested():
                            return
                        aid = int(ids_arr[i]) if ids_arr is not None else entries[i].asset_id
                        path = lookup.full_path(aid)
                        if all(tok in path for tok in tokens):
                            matched_indices.append(i)

            else:
                matched_indices = list(range(len(entries)))

            # Extension filter
            if ext_flt:
                previewable = {'.model', '.texture', '.actor', '.zone', '.level'}
                ids_arr = entries._ids[:len(entries)] if isinstance(entries, _LazyEntryList) else None
                filtered_indices = []
                for offset, i in enumerate(matched_indices):
                    if offset % 4096 == 0 and QThread.currentThread().isInterruptionRequested():
                        return
                    asset_id = int(ids_arr[i]) if ids_arr is not None else entries[i].asset_id
                    path = lookup.full_path(asset_id)
                    if (
                        (ext_flt == 'Visuals' and any(path.endswith(ext) for ext in previewable))
                        or path.endswith(ext_flt)
                    ):
                        filtered_indices.append(i)
                matched_indices = filtered_indices

            self.results_ready.emit(self.generation, matched_indices, ext_flt or '')
        except Exception as ex:
            import traceback
            self.error.emit(self.generation, f"{ex}\n{traceback.format_exc()}")


class AssetBrowser(QWidget):
    # Emitted when user double-clicks an asset
    asset_activated = pyqtSignal(object)   # AssetEntry
    # Emitted when user double-clicks a group (for batch export)
    group_activated = pyqtSignal(object)   # AssetGroup
    # Emitted from right-click context menu
    quick_export_requested  = pyqtSignal(object, str)  # (AssetEntry, fmt)
    add_to_list_requested   = pyqtSignal(object)       # AssetEntry
    remove_from_list_requested = pyqtSignal(object)    # AssetEntry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[AssetEntry] = []
        self._lookup  = None
        self._groups: list[AssetGroup] = []
        self._ungrouped: list = []
        self._groups_mode: bool = False
        self._search_thread: QThread = None
        self._search_worker = None
        self._search_generation = 0
        self._pending_click_entry = None
        self._column_fit_pending = False
        self._fitting_table_columns = False
        # Debounce timer — fires 200 ms after the user stops typing
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._apply_filter)
        # A short delay makes single-click preview feel immediate while still
        # allowing rapid keyboard/tree navigation without loading every row.
        self._preview_delay = QTimer(self)
        self._preview_delay.setSingleShot(True)
        self._preview_delay.setInterval(260)
        self._preview_delay.timeout.connect(self._emit_pending_preview)
        self._export_list_ids: set = set()  # asset_ids currently in export list
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("BrowserHeader")
        header.setFixedHeight(62)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(12, 8, 10, 8)
        hlayout.setSpacing(4)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        lbl = QLabel("Game assets")
        lbl.setObjectName("PanelTitle")
        sub = QLabel("Rift Apart · Steam installation")
        sub.setObjectName("PanelSubtitle")
        title_col.addWidget(lbl)
        title_col.addWidget(sub)
        hlayout.addLayout(title_col)
        hlayout.addStretch()

        self._btn_groups = QPushButton("Group related models")
        self._btn_groups.setObjectName("GroupsToggleBtn")
        self._btn_groups.setCheckable(True)
        self._btn_groups.setChecked(False)
        self._btn_groups.setFixedHeight(24)
        self._btn_groups.setToolTip(
            "Group model files that belong to the same character, prop, or object."
        )
        self._btn_groups.toggled.connect(self._on_groups_toggled)
        hlayout.addWidget(self._btn_groups)

        layout.addWidget(header)

        # ── Filter bar ────────────────────────────────────────────────────────
        filter_frame = QFrame()
        filter_frame.setObjectName("FilterBar")
        flayout = QVBoxLayout(filter_frame)
        flayout.setContentsMargins(6, 6, 6, 6)
        flayout.setSpacing(4)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by asset name or hexadecimal ID")
        self._search.setObjectName("SearchBox")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(34)
        self._search.textChanged.connect(lambda: self._debounce.start())
        search_row.addWidget(self._search)

        self._type_filter = QComboBox()
        self._type_filter.setObjectName("TypeFilter")
        for label, value in (
            ("All assets", "All Types"),
            ("Visual files", "Visuals"),
            ("3D models (.model)", ".model"),
            ("Textures (.texture)", ".texture"),
            ("Actors (.actor)", ".actor"),
            ("Scenes (.zone)", ".zone"),
            ("Levels (.level)", ".level"),
            ("Animation clips (.animclip)", ".animclip"),
            ("Materials (.material)", ".material"),
            ("Configuration (.config)", ".config"),
            ("Visual effects (.visualeffect)", ".visualeffect"),
            ("Audio banks (.soundbank)", ".soundbank"),
        ):
            self._type_filter.addItem(label, value)
        self._type_filter.setFixedWidth(175)
        self._type_filter.setFixedHeight(34)
        self._type_filter.currentTextChanged.connect(lambda: self._debounce.start())
        search_row.addWidget(self._type_filter)
        flayout.addLayout(search_row)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(5)
        for label, ext in (("Visual files", "Visuals"), ("3D models", ".model"),
                           ("Textures", ".texture"), ("All assets", "All Types")):
            btn = QPushButton(label)
            btn.setObjectName("QuickFilterBtn")
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _=False, value=ext: self.set_type_filter(value))
            quick_row.addWidget(btn)
        flayout.addLayout(quick_row)

        guidance = QLabel(
            "Click a gold model group or file to preview it. Drag column borders to resize."
        )
        guidance.setObjectName("BrowserGuidance")
        guidance.setWordWrap(True)
        flayout.addWidget(guidance)

        layout.addWidget(filter_frame)

        # ── Tree ──────────────────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setObjectName("AssetTree")
        self._tree.setHeaderHidden(False)
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Asset name", "File type", "Preview", "File size"])
        header_view = self._tree.header()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_view.setSectionsMovable(True)
        header_view.setStretchLastSection(False)
        header_view.setMinimumSectionSize(55)
        header_view.setHighlightSections(False)
        header_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header_view.customContextMenuRequested.connect(self._show_header_menu)
        header_view.sectionResized.connect(self._on_header_section_resized)
        self._reset_column_widths()
        header_item = self._tree.headerItem()
        for column, tip in enumerate((
            "Asset or model-group name. Drag the column border to resize.",
            "Game file format or group type.",
            "What opens when you click this row.",
            "Uncompressed asset size in the game archive.",
        )):
            header_item.setToolTip(column, tip)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemClicked.connect(self._on_single_click)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.viewport().installEventFilter(self)
        layout.addWidget(self._tree)
        self._schedule_table_width_fit()

        # ── Status bar ────────────────────────────────────────────────────────
        self._status = QLabel("No game data loaded")
        self._status.setObjectName("StatusLabel")
        self._status.setContentsMargins(8, 4, 8, 4)
        self._status.setFixedHeight(24)
        layout.addWidget(self._status)

    def _reset_column_widths(self):
        """Restore a readable default layout while keeping every section interactive."""
        for column, width in enumerate((210, 85, 105, 80)):
            self._tree.header().resizeSection(column, width)
        self._schedule_table_width_fit()

    def eventFilter(self, watched, event):
        """Keep the table filled when its viewport changes size."""
        if watched is self._tree.viewport() and event.type() == QEvent.Type.Resize:
            self._schedule_table_width_fit()
        return super().eventFilter(watched, event)

    def _on_header_section_resized(self, logical_index, _old_size, _new_size):
        """Let metadata columns stay user-sized while the name column fills the balance."""
        if not self._fitting_table_columns and logical_index != 0:
            self._schedule_table_width_fit()

    def _schedule_table_width_fit(self):
        if self._column_fit_pending:
            return
        self._column_fit_pending = True
        QTimer.singleShot(0, self._fit_table_width)

    def _fit_table_width(self):
        """Expand the asset-name column to consume otherwise unused table width."""
        self._column_fit_pending = False
        viewport_width = self._tree.viewport().width()
        if viewport_width <= 0:
            return

        header = self._tree.header()
        metadata_width = sum(header.sectionSize(column) for column in range(1, 4))
        target_width = max(160, viewport_width - metadata_width - 2)
        if header.sectionSize(0) == target_width:
            return

        self._fitting_table_columns = True
        try:
            header.resizeSection(0, target_width)
        finally:
            self._fitting_table_columns = False

    def _show_header_menu(self, pos):
        """Offer obvious recovery after a user rearranges or resizes columns."""
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        reset_action = menu.addAction("Reset column widths and order")
        if menu.exec(self._tree.header().mapToGlobal(pos)) == reset_action:
            header = self._tree.header()
            for logical_index in range(header.count()):
                visual_index = header.visualIndex(logical_index)
                if visual_index != logical_index:
                    header.moveSection(visual_index, logical_index)
            self._reset_column_widths()

    def current_type_filter(self) -> str:
        """Return the internal filter value behind the friendly combo-box label."""
        value = self._type_filter.currentData()
        return value if value is not None else self._type_filter.currentText()

    def set_search(self, text: str, extension: str | None = None):
        """Set a user-visible search and run it immediately."""
        self._debounce.stop()
        self._search.blockSignals(True)
        self._type_filter.blockSignals(True)
        self._search.setText(text)
        if extension:
            idx = self._type_filter.findData(extension)
            self._type_filter.setCurrentIndex(max(0, idx))
        self._search.blockSignals(False)
        self._type_filter.blockSignals(False)
        self._apply_filter()

    def set_type_filter(self, extension: str):
        idx = self._type_filter.findData(extension)
        if idx >= 0:
            self._type_filter.setCurrentIndex(idx)

    def focus_search(self):
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    def load_entries(self, entries):
        self._entries = entries
        self._rebuild_tree(entries)
        self._status.setText(f"{len(entries):,} game assets")

    def load_entries_grouped(self, entries, groups: list, lookup=None):
        """Fast path: groups already computed on background thread."""
        import time
        t0 = time.perf_counter()
        self._entries = entries
        self._lookup  = lookup
        self._tree.clear()
        t1 = time.perf_counter()
        self._tree.setUpdatesEnabled(False)
        for arc_idx, idx_arr in groups:
            self._add_group_item(arc_idx, idx_arr, entries)
        t2 = time.perf_counter()
        self._tree.setUpdatesEnabled(True)
        t3 = time.perf_counter()
        try:
            self._tree.itemExpanded.disconnect(self._on_group_expanded)
        except Exception:
            pass
        self._tree.itemExpanded.connect(self._on_group_expanded)
        n_named = len(lookup) if lookup and lookup.is_loaded() else 0
        suffix = f"  ·  {n_named:,} named" if n_named else ""
        elapsed = time.perf_counter() - t0
        print(f"[browser] clear:{t1-t0:.3f}s  add_groups:{t2-t1:.3f}s  "
              f"enable:{t3-t2:.3f}s  total:{elapsed:.3f}s  groups:{len(groups)}")
        self._status.setText(
            f"{len(entries):,} game assets{suffix}  "
            f"[browser:{elapsed:.2f}s]"
        )

    def set_lookup(self, lookup):
        """Update the hash lookup and refresh visible tree items."""
        self._lookup = lookup
        # Preserve filters chosen while names were still loading. Building a
        # filtered tree without names can create hundreds of thousands of
        # useless "unknown" rows and make the app appear frozen.
        if self._entries and (
            self._search.text().strip()
            or self.current_type_filter() != "All Types"
        ):
            self._apply_filter()
            return
        # Rebuild groups now that we have names
        if self._groups_mode and self._entries:
            self._rebuild_groups_tree()
            return
        # Refresh already-expanded groups
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            if group.childCount() > 0:
                first_child = group.child(0)
                if first_child.text(0) != "  Loading…":
                    # Already expanded — refresh names
                    for j in range(group.childCount()):
                        child = group.child(j)
                        entry = child.data(0, Qt.ItemDataRole.UserRole)
                        if entry:
                            name = lookup.name(entry.asset_id)
                            child.setText(0, name)

    def clear(self):
        self._debounce.stop()
        self._search_generation += 1
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.requestInterruption()
            self._search_thread.quit()
        self._entries = []
        self._tree.clear()
        self._status.setText("No game data loaded")

    # ── Groups mode ───────────────────────────────────────────────────────────

    def _on_groups_toggled(self, checked: bool):
        self._groups_mode = checked
        if checked:
            self._btn_groups.setText("Grouped models: on")
            # If there's an active search, re-run it in groups mode
            if self._search.text().strip() or self.current_type_filter() != "All Types":
                self._apply_filter()
            else:
                self._rebuild_groups_tree()
        else:
            self._btn_groups.setText("Group related models")
            # If there's an active search, keep showing search results (just ungrouped)
            if self._search.text().strip() or self.current_type_filter() != "All Types":
                self._apply_filter()
            else:
                self._rebuild_tree(self._entries)
                self._status.setText(f"{len(self._entries):,} game assets")

    def _rebuild_groups_tree(self):
        """Build the name-prefix group tree. Requires a loaded lookup."""
        if not self._lookup or not self._lookup.is_loaded():
            self._status.setText("Open the Rift Apart game folder before grouping models")
            return

        self._groups, self._ungrouped = build_groups(self._entries, self._lookup)

        self._tree.clear()
        self._tree.setUpdatesEnabled(False)

        # ── Grouped section ───────────────────────────────────────────────
        for group in self._groups:
            self._add_named_group_item(group)

        # ── Ungrouped (singleton) assets ──────────────────────────────────
        if self._ungrouped:
            solo_item = QTreeWidgetItem(self._tree)
            solo_item.setText(0, f"Individual assets ({len(self._ungrouped):,})")
            solo_item.setForeground(0, QColor('#95a5a6'))
            f = solo_item.font(0)
            f.setWeight(QFont.Weight.DemiBold)
            f.setPointSize(10)
            solo_item.setFont(0, f)
            solo_item.setFlags(solo_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            # Lazy-load children
            solo_item.setData(0, Qt.ItemDataRole.UserRole + 2, self._ungrouped)
            QTreeWidgetItem(solo_item).setText(0, "  Loading…")

        self._tree.setUpdatesEnabled(True)

        try:
            self._tree.itemExpanded.disconnect(self._on_group_expanded)
        except Exception:
            pass
        try:
            self._tree.itemExpanded.disconnect(self._on_named_group_expanded)
        except Exception:
            pass
        self._tree.itemExpanded.connect(self._on_named_group_expanded)

        n_groups = len(self._groups)
        self._status.setText(
            f"{len(self._entries):,} assets · {n_groups} related groups · "
            f"{len(self._ungrouped)} individual files"
        )

    def _add_named_group_item(self, group: AssetGroup, parent=None):
        """Add a collapsible group row for one AssetGroup."""
        item = QTreeWidgetItem(parent if parent is not None else self._tree)
        # Icon + label
        noun = "model" if group.count == 1 else "models"
        item.setText(0, f"{group.display_name} ({group.count} {noun})")
        item.setText(1, "Asset family" if group.is_family else "Model group")
        item.setText(2, "Click to preview")
        item.setText(3, "—")
        item.setForeground(0, QColor('#f0a500'))   # amber — distinct from archive rows
        f = item.font(0)
        f.setWeight(QFont.Weight.DemiBold)
        f.setPointSize(10)
        item.setFont(0, f)
        item.setToolTip(0,
            f"{'Asset family' if group.is_family else 'Model group'}: {group.display_name}\n"
            f"Models: {group.count}\n"
            + (f"Game path: {group.directory}\n" if group.directory else "") + "\n"
            "Click to preview the representative model.\n"
            "Use the arrow to show every file. Double-click to export the whole group."
        )
        # Store the group object for expand + double-click
        item.setData(0, Qt.ItemDataRole.UserRole + 3, group)
        # Placeholder child so the expand arrow shows
        QTreeWidgetItem(item).setText(0, "  Loading…")

    def _add_category_item(self, label: str, entries=None, children=None, parent=None):
        """Add a lazy semantic category row above model groups and files."""
        entries = list(entries or [])
        children = list(children or [])
        count = len(entries) if entries else sum(len(child_entries) for _, child_entries in children)
        item = QTreeWidgetItem(parent if parent is not None else self._tree)
        item.setText(0, f"{label} ({count:,} models)")
        item.setText(1, "Category")
        item.setText(2, "Expand to browse")
        item.setText(3, "—")
        item.setForeground(0, QColor('#7fb9ff'))
        font = item.font(0)
        font.setWeight(QFont.Weight.Bold)
        font.setPointSize(10)
        item.setFont(0, font)
        item.setToolTip(0, f"{label}\n{count:,} installed model files")
        item.setData(
            0,
            Qt.ItemDataRole.UserRole + 5,
            {"entries": entries, "children": children, "loaded": False},
        )
        QTreeWidgetItem(item).setText(0, "Loading category…")
        return item

    def _on_category_expanded(self, item: QTreeWidgetItem):
        """Populate one semantic category only when the user opens it."""
        payload = item.data(0, Qt.ItemDataRole.UserRole + 5)
        if not payload or payload.get("loaded"):
            return

        item.takeChildren()
        payload["loaded"] = True
        item.setData(0, Qt.ItemDataRole.UserRole + 5, payload)
        self._tree.setUpdatesEnabled(False)

        if payload["children"]:
            for label, entries in payload["children"]:
                self._add_category_item(label, entries=entries, parent=item)
        else:
            groups, ungrouped = build_groups(payload["entries"], self._lookup)
            for group in groups:
                self._add_named_group_item(group, parent=item)
            for family in build_model_families(ungrouped, self._lookup):
                self._add_named_group_item(family, parent=item)

        self._tree.setUpdatesEnabled(True)

    def _build_model_category_tree(self, entries: list):
        """Organize installed models by purpose, then by planet/location or model group."""
        category_entries = {label: [] for label in MODEL_CATEGORY_ORDER}
        planet_entries = {label: [] for label in PLANET_LOCATION_ORDER}

        for entry in entries:
            path = self._lookup.full_path(entry.asset_id)
            category, location = _classify_model_path(path)
            if category == "Planets & locations":
                planet_entries[location or "Shared environments"].append(entry)
            else:
                category_entries[category].append(entry)

        self._tree.clear()
        self._tree.setUpdatesEnabled(False)
        for category in MODEL_CATEGORY_ORDER:
            if category == "Planets & locations":
                children = [
                    (location, planet_entries[location])
                    for location in PLANET_LOCATION_ORDER
                    if planet_entries[location]
                ]
                if children:
                    self._add_category_item(category, children=children)
            elif category_entries[category]:
                self._add_category_item(category, entries=category_entries[category])

        for handler in (
            self._on_group_expanded,
            self._on_named_group_expanded,
            self._on_category_expanded,
        ):
            try:
                self._tree.itemExpanded.disconnect(handler)
            except Exception:
                pass
        self._tree.itemExpanded.connect(self._on_category_expanded)
        self._tree.itemExpanded.connect(self._on_named_group_expanded)

        self._tree.setUpdatesEnabled(True)
        if self._tree.topLevelItemCount():
            self._tree.topLevelItem(0).setExpanded(True)

    def _on_named_group_expanded(self, item: QTreeWidgetItem):
        """Lazy-populate children of a named group or the 'Ungrouped' bucket."""
        # Named group
        group: AssetGroup = item.data(0, Qt.ItemDataRole.UserRole + 3)
        if group is not None:
            item.takeChildren()
            self._tree.setUpdatesEnabled(False)
            for entry in group.entries:
                child = QTreeWidgetItem(item)
                display = self._lookup.name(entry.asset_id) if self._lookup and self._lookup.is_loaded() else f"{entry.asset_id:016X}"
                full    = self._lookup.full_path(entry.asset_id) if self._lookup and self._lookup.is_loaded() else display
                self._decorate_asset_item(child, entry, display, full)
            self._tree.setUpdatesEnabled(True)
            item.setData(0, Qt.ItemDataRole.UserRole + 3, None)
            # Keep the group reference in a different role for double-click
            item.setData(0, Qt.ItemDataRole.UserRole + 4, group)
            return

        # Ungrouped bucket
        solo_entries = item.data(0, Qt.ItemDataRole.UserRole + 2)
        if solo_entries is not None:
            item.takeChildren()
            self._tree.setUpdatesEnabled(False)
            for entry in solo_entries:
                child = QTreeWidgetItem(item)
                display = self._lookup.name(entry.asset_id) if self._lookup and self._lookup.is_loaded() else f"{entry.asset_id:016X}"
                full    = self._lookup.full_path(entry.asset_id) if self._lookup and self._lookup.is_loaded() else display
                self._decorate_asset_item(child, entry, display, full)
            self._tree.setUpdatesEnabled(True)
            item.setData(0, Qt.ItemDataRole.UserRole + 2, None)

    # ── Private ───────────────────────────────────────────────────────────────

    def _rebuild_tree(self, entries):
        self._tree.clear()
        self._tree.setUpdatesEnabled(False)

        from core.archive import _LazyEntryList
        import numpy as np

        if isinstance(entries, _LazyEntryList) and len(entries) > 0:
            # Single-pass O(n) grouping using numpy argsort
            arc_col  = entries._sizes['archive'][:len(entries)].astype(np.int32)
            sort_idx = np.argsort(arc_col, kind='stable')
            sorted_arcs = arc_col[sort_idx]
            # Find boundaries between archive groups
            boundaries = np.where(np.diff(sorted_arcs))[0] + 1
            starts = np.concatenate([[0], boundaries])
            ends   = np.concatenate([boundaries, [len(sort_idx)]])

            for start, end in zip(starts, ends):
                arc_idx  = int(sorted_arcs[start])
                idx_list = sort_idx[start:end].tolist()
                self._add_group_item(arc_idx, idx_list, entries)
        else:
            # Fallback for plain lists
            groups: dict[int, list] = {}
            for i, e in enumerate(entries):
                groups.setdefault(e.archive, []).append(i)
            for arc_idx in sorted(groups.keys()):
                self._add_group_item(arc_idx, groups[arc_idx], entries)

        self._tree.setUpdatesEnabled(True)
        try:
            self._tree.itemExpanded.disconnect(self._on_group_expanded)
        except Exception:
            pass
        self._tree.itemExpanded.connect(self._on_group_expanded)

    def _add_group_item(self, arc_idx: int, idx_list: list, entries):
        group_item = QTreeWidgetItem(self._tree)
        group_item.setText(0, f"Game archive {arc_idx:03d} ({len(idx_list):,} files)")
        group_item.setText(1, "Archive")
        group_item.setText(2, "Expand to browse")
        group_item.setText(3, "—")
        group_item.setForeground(0, QColor('#5dade2'))
        f = group_item.font(0)
        f.setWeight(QFont.Weight.DemiBold)
        f.setPointSize(10)
        group_item.setFont(0, f)
        group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        group_item.setData(0, Qt.ItemDataRole.UserRole + 1, (entries, idx_list))
        QTreeWidgetItem(group_item).setText(0, "  Loading…")

    def _on_group_expanded(self, group_item: QTreeWidgetItem):
        """Populate children on first expand — lazy loading."""
        payload = group_item.data(0, Qt.ItemDataRole.UserRole + 1)
        if payload is None:
            return
        entries, idx_arr = payload
        group_item.takeChildren()
        self._tree.setUpdatesEnabled(False)
        # idx_arr may be a numpy array or a plain list
        for idx in idx_arr:
            entry = entries[int(idx)]
            child = QTreeWidgetItem(group_item)

            if self._lookup and self._lookup.is_loaded():
                display = self._lookup.name(entry.asset_id)
                full    = self._lookup.full_path(entry.asset_id)
            else:
                display = f"{entry.asset_id:016X}"
                full    = display

            self._decorate_asset_item(child, entry, display, full)
        self._tree.setUpdatesEnabled(True)
        group_item.setData(0, Qt.ItemDataRole.UserRole + 1, None)

    def _apply_filter(self):
        import re as _re
        self._search_generation += 1
        generation = self._search_generation
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.requestInterruption()
            self._search_thread.quit()
            self._search_thread.wait(150)

        raw_text = self._search.text().lower().strip()
        ext_flt  = self.current_type_filter()
        if ext_flt == "All Types":
            ext_flt = None

        from core.archive import _LazyEntryList

        # Reset to full view when nothing typed
        if not raw_text and not ext_flt:
            if isinstance(self._entries, _LazyEntryList):
                self.load_entries_grouped(
                    self._entries,
                    self._compute_groups(self._entries),
                    self._lookup
                )
            else:
                self._rebuild_tree(self._entries)
            self._status.setText(f"{len(self._entries):,} game assets")
            return

        if not self._lookup or not self._lookup.is_loaded():
            if ext_flt:
                self._status.setText("Names loading — this filter will apply automatically")
                return
            # No names loaded — fall back to hex filter only
            filtered = [e for e in self._entries
                        if not raw_text or raw_text in f"{e.asset_id:016x}"]
            self._build_filtered_tree(filtered, ext_flt=ext_flt)
            self._status.setText(f"{len(filtered):,} of {len(self._entries):,} assets")
            return

        # Tokenise: split on whitespace OR underscore, keep tokens >= 2 chars.
        # The raw_text itself is always kept as an extra token so that a word
        # like "sargasso" is matched even if it contains underscores internally.
        tokens = list({t for t in _re.split(r'[\s_]+', raw_text) if len(t) >= 2})
        if not tokens:
            tokens = [raw_text]
        # Only add raw_text as an extra token when it's a single word with no
        # spaces or underscores — this covers prefix searches like "sar" → "sargasso"
        # but does NOT add "enm_chunk" as a literal token (which would never match
        # since paths use underscores as separators, not as part of adjacent words).
        if '_' not in raw_text and ' ' not in raw_text and raw_text not in tokens:
            tokens.append(raw_text)

        # Show immediate feedback
        self._status.setText("Searching…")

        self._search_thread = QThread(self)
        self._search_worker = SearchWorker(
            self._entries, self._lookup, tokens, raw_text, ext_flt, generation
        )
        self._search_worker.moveToThread(self._search_thread)
        self._search_thread.started.connect(self._search_worker.run)
        self._search_worker.results_ready.connect(self._on_search_done)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.results_ready.connect(self._search_thread.quit)
        self._search_worker.error.connect(self._search_thread.quit)
        self._search_thread.start()

    def _on_search_error(self, generation: int, message: str):
        if generation == self._search_generation:
            self._status.setText(f"Search error: {message[:80]}")

    def _on_search_done(self, generation: int, matched_indices: list, ext_flt: str):
        """Called on the main thread when the background search finishes."""
        if generation != self._search_generation:
            return
        ext_flt  = ext_flt or None
        filtered = [self._entries[i] for i in matched_indices]
        self._build_filtered_tree(filtered, ext_flt=ext_flt)
        if ext_flt == ".model":
            self._status.setText(
                f"{len(filtered):,} models organized into "
                f"{self._tree.topLevelItemCount()} categories"
            )
            return
        from core.grouping import build_groups as _bg
        if ext_flt and filtered:
            grps, ungrp = _bg(filtered, self._lookup)
            if grps:
                self._status.setText(
                    f"{len(filtered):,} results  ·  {len(grps)} groups  ·  {len(ungrp)} other"
                )
                return
        self._status.setText(f"{len(filtered):,} of {len(self._entries):,} assets")

    def _compute_groups(self, entries):
        """Re-compute archive groups for the given entries."""
        from core.archive import _LazyEntryList
        import numpy as np
        if isinstance(entries, _LazyEntryList):
            arc_col     = entries._sizes['archive'][:len(entries)].astype(np.int32)
            sort_idx    = np.argsort(arc_col, kind='stable')
            sorted_arcs = arc_col[sort_idx]
            if len(sorted_arcs) == 0:
                return []
            boundaries  = np.where(np.diff(sorted_arcs))[0] + 1
            starts = np.concatenate([[0], boundaries])
            ends   = np.concatenate([boundaries, [len(sort_idx)]])
            return [(int(sorted_arcs[s]), sort_idx[s:e].tolist())
                    for s, e in zip(starts, ends)]
        else:
            groups = {}
            for i, e in enumerate(entries):
                groups.setdefault(e.archive, []).append(i)
            return sorted(groups.items())

    def _build_filtered_tree(self, entries: list, ext_flt: str = None):
        """
        Build the filtered-results tree.

        Slug grouping is only applied when a specific file format is selected
        (ext_flt is set) OR Groups mode is explicitly ON — this prevents
        irrelevant file types from appearing inside groups when searching
        across all asset types.
        """
        has_lookup = self._lookup and self._lookup.is_loaded()
        if has_lookup and entries and ext_flt == ".model":
            self._build_model_category_tree(entries)
            return

        self._tree.clear()
        self._tree.setUpdatesEnabled(False)

        allow_grouping = self._groups_mode or bool(ext_flt)

        # ── Attempt slug-based grouping ───────────────────────────────────────
        if has_lookup and entries and allow_grouping:
            groups, ungrouped = build_groups(entries, self._lookup)
        else:
            groups, ungrouped = [], list(entries)

        use_slug_groups = allow_grouping and len(groups) > 0

        if use_slug_groups:
            # ── Slug-grouped display ──────────────────────────────────────────
            for group in groups:
                self._add_named_group_item(group)

            # Singletons shown flat underneath
            if ungrouped:
                if groups:
                    # Separate header for ungrouped results
                    solo_hdr = QTreeWidgetItem(self._tree)
                    solo_hdr.setText(0, f"Individual models ({len(ungrouped):,})")
                    solo_hdr.setForeground(0, QColor('#95a5a6'))
                    f = solo_hdr.font(0)
                    f.setWeight(QFont.Weight.DemiBold)
                    f.setPointSize(10)
                    solo_hdr.setFont(0, f)
                    solo_hdr.setFlags(solo_hdr.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    solo_hdr.setExpanded(True)
                    parent = solo_hdr
                else:
                    parent = self._tree   # no groups at all — use root

                for entry in ungrouped:
                    child = QTreeWidgetItem(parent)
                    display = self._lookup.name(entry.asset_id) if has_lookup else f"{entry.asset_id:016X}"
                    full    = self._lookup.full_path(entry.asset_id) if has_lookup else display
                    self._decorate_asset_item(child, entry, display, full)

            # Wire expand handler for the named group rows
            try:
                self._tree.itemExpanded.disconnect(self._on_group_expanded)
            except Exception:
                pass
            try:
                self._tree.itemExpanded.disconnect(self._on_named_group_expanded)
            except Exception:
                pass
            self._tree.itemExpanded.connect(self._on_named_group_expanded)
            # Put real, clickable assets on screen immediately. Leaving every
            # model set collapsed made the populated browser feel empty.
            if self._tree.topLevelItemCount():
                first = self._tree.topLevelItem(0)
                if first.data(0, Qt.ItemDataRole.UserRole + 3) is not None:
                    first.setExpanded(True)

        else:
            # ── Flat extension-bucket fallback (no groups found) ──────────────
            ext_buckets: dict[str, list] = {}
            for e in entries:
                if has_lookup:
                    path = self._lookup.full_path(e.asset_id)
                    ext  = '.' + path.rsplit('.', 1)[-1] if '.' in path else 'unknown'
                else:
                    ext = 'unknown'
                ext_buckets.setdefault(ext, []).append(e)

            for ext in sorted(ext_buckets.keys()):
                items = ext_buckets[ext]
                bucket_item = QTreeWidgetItem(self._tree)
                bucket_item.setText(0, f"{ext} files ({len(items):,})")
                bucket_item.setText(1, "File group")
                bucket_item.setText(2, "Expand to browse")
                bucket_item.setText(3, "—")
                bucket_item.setForeground(0, QColor('#5dade2'))
                f = bucket_item.font(0)
                f.setWeight(QFont.Weight.DemiBold)
                f.setPointSize(10)
                bucket_item.setFont(0, f)
                bucket_item.setFlags(bucket_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                bucket_item.setExpanded(True)

                for entry in items:
                    child = QTreeWidgetItem(bucket_item)
                    display = self._lookup.name(entry.asset_id) if has_lookup else f"{entry.asset_id:016X}"
                    full    = self._lookup.full_path(entry.asset_id) if has_lookup else display
                    self._decorate_asset_item(child, entry, display, full)

        self._tree.setUpdatesEnabled(True)

    @staticmethod
    def _format_bytes(size: int) -> str:
        value = float(size)
        for suffix in ("B", "KB", "MB", "GB"):
            if value < 1024.0 or suffix == "GB":
                return f"{value:.0f} {suffix}" if suffix == "B" else f"{value:.1f} {suffix}"
            value /= 1024.0
        return f"{size:,} B"

    def _decorate_asset_item(self, item: QTreeWidgetItem, entry, display: str, full: str):
        ext = full.rsplit('.', 1)[-1].upper() if '.' in full else "RAW"
        file_type = {
            "MODEL": "3D model",
            "TEXTURE": "Texture",
            "ACTOR": "Actor",
            "ZONE": "Scene zone",
            "LEVEL": "Level",
            "MATERIAL": "Material",
            "MATERIALGRAPH": "Material graph",
        }.get(ext, f".{ext.lower()}" if ext != "RAW" else "Unknown")
        preview = {
            "MODEL": "3D model",
            "TEXTURE": "Image",
            "ACTOR": "Linked model",
            "ZONE": "Scene",
            "LEVEL": "Scene",
            "MATERIAL": "Details",
            "MATERIALGRAPH": "Details",
        }.get(ext, "Raw data")
        item.setText(0, display)
        item.setText(1, file_type)
        item.setText(2, preview)
        item.setText(3, self._format_bytes(entry.size))
        # Keep asset rows compact while remaining readable at normal desktop DPI.
        for column in range(4):
            font = item.font(column)
            font.setPointSize(10)
            item.setFont(column, font)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setForeground(2, QColor('#7dffb2') if preview in {"3D model", "Image", "Scene"}
                           else QColor('#ffb066') if preview == "Linked model"
                           else QColor('#7187ad'))
        item.setData(0, Qt.ItemDataRole.UserRole, entry)
        item.setToolTip(0, (
            f"ID:      {entry.asset_id:#018x}\n"
            f"Path:    {full}\n"
            f"Archive: {entry.archive}\n"
            f"Offset:  {entry.offset:#010x}\n"
            f"Size:    {entry.size:,} bytes"
        ))

    def _on_single_click(self, item: QTreeWidgetItem, col: int):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry:
            self._pending_click_entry = entry
            self._preview_delay.start()
            return
        category = item.data(0, Qt.ItemDataRole.UserRole + 5)
        if category is not None:
            item.setExpanded(not item.isExpanded())
            return
        group = item.data(0, Qt.ItemDataRole.UserRole + 3) or \
            item.data(0, Qt.ItemDataRole.UserRole + 4)
        ungrouped = item.data(0, Qt.ItemDataRole.UserRole + 2)
        if group is not None:
        # Group rows are labelled "Click to preview". Honour that contract by
            # opening the representative model as well as revealing its parts.
            if not item.isExpanded():
                item.setExpanded(True)
            if group.entries:
                self._pending_click_entry = group.entries[0]
                self._preview_delay.start()
            return
        if ungrouped is not None:
            item.setExpanded(not item.isExpanded())

    def _emit_pending_preview(self):
        if self._pending_click_entry is not None:
            entry = self._pending_click_entry
            self._pending_click_entry = None
            self.asset_activated.emit(entry)

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry:
            self._preview_delay.stop()
            self._pending_click_entry = None
            self.asset_activated.emit(entry)
            return
        # Double-click on a named group header → batch export
        group = item.data(0, Qt.ItemDataRole.UserRole + 4)
        if group:
            self._preview_delay.stop()
            self._pending_click_entry = None
            self.group_activated.emit(group)

    def _on_context_menu(self, pos):
        """Show right-click context menu for asset items."""
        from PyQt6.QtWidgets import QMenu
        item = self._tree.itemAt(pos)
        if item is None:
            return
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry is None:
            return

        name = item.text(0)
        in_list = entry.asset_id in self._export_list_ids

        menu = QMenu(self)
        menu.setObjectName("ContextMenu")

        # ── Quick Export ──────────────────────────────────────────────────────
        menu.addSection("Export selected asset")
        act_glb = menu.addAction("Export as GLB…")
        act_fbx = menu.addAction("Export as FBX…")
        act_obj = menu.addAction("Export as OBJ…")

        menu.addSeparator()

        # ── Export List ───────────────────────────────────────────────────────
        menu.addSection("Queued exports")
        if in_list:
            act_list = menu.addAction("Remove from export queue")
        else:
            act_list = menu.addAction("Add to export queue")

        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action is None:
            return

        if action == act_glb:
            self.quick_export_requested.emit(entry, 'glb')
        elif action == act_fbx:
            self.quick_export_requested.emit(entry, 'fbx')
        elif action == act_obj:
            self.quick_export_requested.emit(entry, 'obj')
        elif action == act_list:
            if in_list:
                self._export_list_ids.discard(entry.asset_id)
                self.remove_from_list_requested.emit(entry)
            else:
                self._export_list_ids.add(entry.asset_id)
                self.add_to_list_requested.emit(entry)

    def mark_export_list(self, asset_ids: set):
        """Update the tracked export list IDs (called from main window)."""
        self._export_list_ids = set(asset_ids)
