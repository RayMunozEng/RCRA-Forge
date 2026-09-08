"""
ui/properties_panel.py
Right-side properties and export panel for RCRA Forge.

Shows info about the currently selected asset and provides one-click
export to .glb, .gltf, .obj, or .dds.
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QFileDialog, QFrame, QProgressBar,
    QComboBox, QCheckBox, QSizePolicy, QTextEdit, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QFont, QColor

from core.archive import AssetEntry


class ExportWorker(QObject):
    """Run export on a background thread."""
    finished = pyqtSignal(str)      # output path on success
    error    = pyqtSignal(str)      # error message

    def __init__(self, mesh_asset, path: str, fmt: str, lod: int = 0):
        super().__init__()
        self.mesh  = mesh_asset
        self.path  = path
        self.fmt   = fmt
        self.lod   = lod

    def run(self):
        try:
            from exporters.gltf_exporter import GltfExporter, ObjExporter
            name = os.path.splitext(os.path.basename(self.path))[0]
            if self.fmt == 'glb':
                GltfExporter(self.mesh, name, lod=self.lod).export_glb(self.path)
            elif self.fmt == 'gltf':
                GltfExporter(self.mesh, name, lod=self.lod).export_gltf(self.path)
            elif self.fmt == 'obj':
                ObjExporter(self.mesh, name, lod=self.lod).export(self.path)
            elif self.fmt == 'ascii':
                from exporters.ascii_exporter import export_ascii
                export_ascii(self.mesh, self.path, lod=self.lod)
            self.finished.emit(self.path)
        except Exception as ex:
            import traceback
            self.error.emit(f"{ex}\n{traceback.format_exc()}")


class GroupExportWorker(QObject):
    """
    Load every asset in a group, then combine them into one GLB.
    Runs on a background thread — emits progress per part.
    """
    progress = pyqtSignal(str)    # status message
    finished = pyqtSignal(str)    # output path on success
    error    = pyqtSignal(str)    # error message

    def __init__(self, group, toc_parser, path: str):
        """
        Parameters
        ----------
        group      : AssetGroup  (from core.grouping)
        toc_parser : TocParser   already-parsed TOC (shared, do not re-parse)
        path       : str         output .glb path
        """
        super().__init__()
        self.group      = group
        self.toc_parser = toc_parser
        self.path       = path

    def run(self):
        try:
            from exporters.group_exporter import GroupExporter
            from core.mesh import ModelParser

            exporter = GroupExporter(slug=self.group.slug.rsplit('/', 1)[-1])
            n = len(self.group.entries)

            for i, entry in enumerate(self.group.entries):
                # Derive part name from the asset id / path
                try:
                    from core.hashes import get_lookup
                    lk = get_lookup()
                    if lk and lk.is_loaded():
                        full = lk.full_path(entry.asset_id)
                        part_name = full.rsplit('/', 1)[-1].rsplit('.', 1)[0]
                    else:
                        part_name = f"part_{i:03d}"
                except Exception:
                    part_name = f"part_{i:03d}"

                self.progress.emit(f"Loading part {i+1}/{n}: {part_name}…")

                try:
                    raw = self.toc_parser.extract_asset(entry)
                    model = ModelParser(raw).parse()
                    exporter.add_model(model, part_name)
                except Exception as ex:
                    self.progress.emit(f"  ⚠ Skipped {part_name}: {ex}")
                    continue

            self.progress.emit(f"Writing GLB ({n} parts)…")
            exporter.export_glb(self.path)
            self.finished.emit(self.path)

        except Exception as ex:
            import traceback
            self.error.emit(f"{ex}\n{traceback.format_exc()}")



class PropertiesPanel(QWidget):
    request_export = pyqtSignal(str, str)   # (output_path, format_string)
    lod_changed    = pyqtSignal(int)        # emitted when user picks a different LOD

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entry:      AssetEntry  = None
        self._asset_name: str        = None
        self._mesh_asset             = None
        self._group                  = None   # AssetGroup for batch export
        self._archive_path: str      = None   # path to game 'toc' file
        self._toc_parser             = None   # shared TocParser (set after TOC load)
        self._export_thread: QThread = None
        self._export_worker          = None   # keeps ExportWorker alive during thread run
        self._build_ui()
        self.setMinimumHeight(480)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header (fixed) ──────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("BrowserHeader")
        hdr.setFixedHeight(36)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel("Selected asset")
        lbl.setObjectName("PanelTitle")
        hl.addWidget(lbl)
        outer.addWidget(hdr)

        # ── Scrollable body ─────────────────────────────────────────────────
        # Use a QScrollArea child of self so stylesheet inheritance works.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_widget = QWidget()
        # Give the inner widget the same object name so it inherits bg
        self._scroll_widget.setObjectName("PropertiesPanelInner")
        layout = QVBoxLayout(self._scroll_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._scroll.setWidget(self._scroll_widget)
        outer.addWidget(self._scroll)
        # Explicitly propagate stylesheet to scroll inner widget so QGroupBox
        # and other widgets render correctly (QScrollArea breaks CSS cascade).
        self._scroll_widget.setStyleSheet(self.styleSheet())

        # ── Info group ─────────────────────────────────────────────────────
        info_group = QGroupBox("File information")
        info_group.setObjectName("PropsGroup")
        form = QFormLayout(info_group)
        form.setSpacing(4)
        form.setContentsMargins(8, 12, 8, 8)

        self._lbl_name = self._field_label()
        self._lbl_id   = self._field_label()
        self._lbl_type = self._field_label()
        self._lbl_size = self._field_label()
        self._lbl_wad  = self._field_label()
        self._lbl_off  = self._field_label()

        form.addRow("Name:",           self._lbl_name)
        form.addRow("File type:",      self._lbl_type)
        form.addRow("File size:",      self._lbl_size)
        form.addRow("Game archive:",   self._lbl_wad)
        form.addRow("Archive offset:", self._lbl_off)
        form.addRow("Asset ID:",       self._lbl_id)

        layout.addWidget(info_group)
        layout.addSpacing(4)

        # ── Mesh stats ─────────────────────────────────────────────────────
        self._mesh_group = QGroupBox("Model geometry")
        self._mesh_group.setObjectName("PropsGroup")
        mform = QFormLayout(self._mesh_group)
        mform.setSpacing(4)
        mform.setContentsMargins(8, 12, 8, 8)

        self._lbl_verts  = self._field_label()
        self._lbl_tris   = self._field_label()
        self._lbl_submsh = self._field_label()
        self._lbl_lods   = self._field_label()
        self._lbl_bones  = self._field_label()

        mform.addRow("Vertices:",   self._lbl_verts)
        mform.addRow("Triangles:",  self._lbl_tris)
        mform.addRow("Sub-meshes:", self._lbl_submsh)
        mform.addRow("LOD levels:", self._lbl_lods)
        mform.addRow("Bones:",      self._lbl_bones)

        self._mesh_group.setVisible(False)
        layout.addWidget(self._mesh_group)
        layout.addSpacing(4)

        # ── Export group ────────────────────────────────────────────────────
        exp_group = QGroupBox("Export")
        exp_group.setObjectName("PropsGroup")
        elayout = QVBoxLayout(exp_group)
        elayout.setContentsMargins(8, 12, 8, 8)
        elayout.setSpacing(6)

        # Format selector
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.setObjectName("FmtCombo")
        self._fmt_combo.addItems([
            "GLB (Blender/glTF binary)",
            "GLTF (text + .bin)",
            "OBJ (Wavefront)",
            "FBX (Binary, Maya/3ds Max/Blender)",
            "ASCII (ALERT re-import format)",
        ])
        fmt_row.addWidget(self._fmt_combo)
        elayout.addLayout(fmt_row)

        # Texture export controls
        tex_row = QHBoxLayout()
        self._export_tex_chk = QCheckBox("Export textures")
        self._export_tex_chk.setChecked(True)
        self._export_tex_chk.setToolTip(
            "Export PBR textures alongside the model\n"
            "(albedo, normal, AO/emission, specular IOR)"
        )
        self._export_tex_chk.toggled.connect(self._on_tex_export_toggled)
        tex_row.addWidget(self._export_tex_chk)

        self._tex_fmt_combo = QComboBox()
        self._tex_fmt_combo.addItems(["PNG", "DDS", "PNG + DDS"])
        self._tex_fmt_combo.setToolTip("PNG = universal; DDS = BCn compressed (smaller)")
        tex_row.addWidget(self._tex_fmt_combo)

        self._embed_tex_chk = QCheckBox("Embed in GLB")
        self._embed_tex_chk.setChecked(False)
        self._embed_tex_chk.setToolTip(
            "Embed textures inside the GLB file (self-contained)\n"
            "If unchecked, textures are written to a textures/ subfolder"
        )
        tex_row.addWidget(self._embed_tex_chk)
        tex_row.addStretch()
        elayout.addLayout(tex_row)

        # LOD selector
        lod_row = QHBoxLayout()
        lod_row.addWidget(QLabel("Detail level:"))
        self._lod_combo = QComboBox()
        self._lod_combo.setObjectName("FmtCombo")
        self._lod_combo.addItem("LOD 0  (highest)")
        self._lod_combo.setEnabled(False)
        self._lod_combo.setToolTip("Select which Level of Detail to view and export")
        self._lod_combo.currentIndexChanged.connect(self._on_lod_changed)
        lod_row.addWidget(self._lod_combo)
        elayout.addLayout(lod_row)

        # Export button
        self._btn_export = QPushButton("Export selected asset…")
        self._btn_export.setObjectName("ExportBtn")
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._do_export)
        elayout.addWidget(self._btn_export)

        # ── Group export ─────────────────────────────────────────────────────
        from PyQt6.QtWidgets import QFrame as _QFrame
        sep = _QFrame()
        sep.setFrameShape(_QFrame.Shape.HLine)
        sep.setFrameShadow(_QFrame.Shadow.Sunken)
        elayout.addWidget(sep)

        self._group_info = QLabel("No group selected")
        self._group_info.setObjectName("FieldValue")
        self._group_info.setWordWrap(True)
        elayout.addWidget(self._group_info)

        self._btn_export_group = QPushButton("Export selected model group…")
        self._btn_export_group.setObjectName("ExportBtn")
        self._btn_export_group.setEnabled(False)
        self._btn_export_group.setToolTip(
            "Export all parts of the selected group into a single GLB.\n"
            "Each part becomes a separate named mesh node in Blender."
        )
        self._btn_export_group.clicked.connect(self._do_export_group)
        elayout.addWidget(self._btn_export_group)

        self._btn_export_zone = QPushButton("Export selected scene zone…")
        self._btn_export_zone.setObjectName("ExportBtn")
        self._btn_export_zone.setEnabled(False)
        self._btn_export_zone.setToolTip(
            "Resolve all zone scene nodes to models and export as a single GLB\n"
            "with correct world-space transforms. Load a .zone asset first."
        )
        self._btn_export_zone.clicked.connect(self._do_export_zone)
        elayout.addWidget(self._btn_export_zone)

        self._btn_dump_zone = QPushButton("Inspect scene-zone records")
        self._btn_dump_zone.setObjectName("ExportBtn")
        self._btn_dump_zone.setEnabled(False)
        self._btn_dump_zone.setToolTip(
            "Print raw field values for the first 5 zone entries to the log.\n"
            "Used to verify position/rotation field offsets."
        )
        self._btn_dump_zone.clicked.connect(self._do_dump_zone)
        elayout.addWidget(self._btn_dump_zone)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setVisible(False)
        elayout.addWidget(self._progress)

        # Status
        self._export_status = QLabel("")
        self._export_status.setObjectName("ExportStatus")
        self._export_status.setWordWrap(True)
        elayout.addWidget(self._export_status)

        layout.addWidget(exp_group)

        # ── Export List ────────────────────────────────────────────────────────
        list_group = QGroupBox("Queued exports")
        list_group.setObjectName("PropsGroup")
        llayout = QVBoxLayout(list_group)
        llayout.setContentsMargins(8, 12, 8, 8)
        llayout.setSpacing(4)

        list_hint = QLabel("Right-click an asset in Game assets to add it here.")
        list_hint.setObjectName("FieldValue")
        list_hint.setWordWrap(True)
        llayout.addWidget(list_hint)

        from PyQt6.QtWidgets import QListWidget
        self._export_list_widget = QListWidget()
        self._export_list_widget.setObjectName("ExportListWidget")
        self._export_list_widget.setMaximumHeight(120)
        self._export_list_widget.setToolTip("Assets queued for combined GLB export.\nRight-click an asset in the browser to add or remove.")
        llayout.addWidget(self._export_list_widget)

        list_btn_row = QHBoxLayout()
        self._btn_clear_list = QPushButton("Clear queue")
        self._btn_clear_list.setObjectName("SmallBtn")
        self._btn_clear_list.setEnabled(False)
        self._btn_clear_list.clicked.connect(self._do_clear_export_list)
        list_btn_row.addWidget(self._btn_clear_list)
        list_btn_row.addStretch()
        llayout.addLayout(list_btn_row)

        self._btn_export_list = QPushButton("Export queued assets…")
        self._btn_export_list.setObjectName("ExportBtn")
        self._btn_export_list.setEnabled(False)
        self._btn_export_list.setToolTip(
            "Export all queued assets into a single GLB.\n"
            "Each asset becomes a named node under a shared root."
        )
        self._btn_export_list.clicked.connect(self._do_export_list)
        llayout.addWidget(self._btn_export_list)

        self._list_status = QLabel("")
        self._list_status.setObjectName("ExportStatus")
        self._list_status.setWordWrap(True)
        llayout.addWidget(self._list_status)

        layout.addWidget(list_group)
        layout.addStretch()

        # ── Log / notes ────────────────────────────────────────────────────
        self._log = QTextEdit()
        self._log.setObjectName("LogBox")
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(90)
        self._log.setPlaceholderText("Export log…")
        layout.addWidget(self._log)

    def changeEvent(self, event):
        """Re-propagate stylesheet changes into the scroll area inner widget."""
        super().changeEvent(event)
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.StyleChange:
            if hasattr(self, '_scroll_widget'):
                self._scroll_widget.setStyleSheet(self.styleSheet())

    # ── Public API ────────────────────────────────────────────────────────────

    def set_entry(self, entry: AssetEntry, name: str = None):
        self._entry = entry
        self._asset_name = name  # display name from lookup (e.g. 'hero_ratchet')
        display_name = name or f"{entry.asset_id:016X}"
        extension = display_name.rsplit('.', 1)[-1].casefold() if '.' in display_name else ""
        type_names = {
            "model": "3D model (.model)",
            "texture": "Texture (.texture)",
            "actor": "Actor definition (.actor)",
            "zone": "Scene zone (.zone)",
            "level": "Level data (.level)",
            "material": "Material (.material)",
            "animclip": "Animation clip (.animclip)",
        }
        self._lbl_name.setText(display_name)
        self._lbl_id.setText(f"{entry.asset_id:016X}")
        self._lbl_type.setText(type_names.get(extension, f".{extension}" if extension else "Unknown"))
        self._lbl_size.setText(f"{entry.size:,} bytes")
        self._lbl_wad.setText(f"Archive {entry.archive:03d}")
        self._lbl_off.setText(f"{entry.offset:#010x}")
        self._mesh_group.setVisible(False)
        self._btn_export.setEnabled(False)

    def set_mesh_asset(self, model_asset):
        self._mesh_asset = model_asset
        if model_asset is None:
            self._mesh_group.setVisible(False)
            self._btn_export.setEnabled(False)
            return

        from core.mesh import mesh_to_numpy
        total_verts = 0
        total_tris  = 0
        for mesh in model_asset.meshes:
            pos, _, _, idx = mesh_to_numpy(model_asset, mesh)
            if pos is not None:
                total_verts += len(pos)
            if idx is not None:
                total_tris += len(idx) // 3

        self._lbl_verts.setText(f"{total_verts:,}")
        self._lbl_tris.setText(f"{total_tris:,}")
        self._lbl_submsh.setText(str(len(model_asset.meshes)))
        self._lbl_lods.setText(str(getattr(model_asset, 'lod_count', 1)))
        self._lbl_bones.setText(str(len(model_asset.joints)))
        self._mesh_group.setVisible(True)
        self._btn_export.setEnabled(True)

        # Populate LOD selector
        self._lod_combo.blockSignals(True)
        self._lod_combo.clear()
        lod_count = getattr(model_asset, 'lod_count', 1)
        for i in range(lod_count):
            label = "highest detail" if i == 0 else f"lower detail"
            self._lod_combo.addItem(f"LOD {i}  ({label})")
        self._lod_combo.setCurrentIndex(0)
        self._lod_combo.setEnabled(lod_count > 1)
        self._lod_combo.blockSignals(False)

    def set_archive_path(self, path: str):
        """Store the loaded toc path (kept for legacy callers)."""
        self._archive_path = path

    def set_toc_parser(self, parser, path: str):
        """Store the shared TocParser and toc path after TOC load."""
        self._toc_parser   = parser
        self._archive_path = path

    def add_to_export_list(self, entry, name: str = None):
        """Add an asset entry to the export list panel."""
        # Check for duplicates
        for i in range(self._export_list_widget.count()):
            item = self._export_list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole).asset_id == entry.asset_id:
                return  # already in list
        from PyQt6.QtWidgets import QListWidgetItem
        display = name or f"{entry.asset_id:016X}"
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, entry)
        item.setToolTip(f"ID: {entry.asset_id:#018x}")
        self._export_list_widget.addItem(item)
        self._btn_clear_list.setEnabled(True)
        self._btn_export_list.setEnabled(True)
        self._list_status.setText(f"{self._export_list_widget.count()} asset(s) queued")

    def remove_from_export_list(self, entry):
        """Remove an asset entry from the export list panel."""
        for i in range(self._export_list_widget.count()):
            item = self._export_list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole).asset_id == entry.asset_id:
                self._export_list_widget.takeItem(i)
                break
        count = self._export_list_widget.count()
        self._btn_clear_list.setEnabled(count > 0)
        self._btn_export_list.setEnabled(count > 0)
        self._list_status.setText(f"{count} asset(s) queued" if count > 0 else "")

    def get_export_list_entries(self):
        """Return all AssetEntry objects currently in the export list."""
        return [
            self._export_list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._export_list_widget.count())
        ]

    def clear_export_list(self):
        """Clear the export list programmatically."""
        self._export_list_widget.clear()
        self._btn_clear_list.setEnabled(False)
        self._btn_export_list.setEnabled(False)
        self._list_status.setText("")

    def set_group(self, group):
        """Populate the group export section with *group* info."""
        self._group = group
        name = group.slug.rsplit('/', 1)[-1]
        self._group_info.setText(
            f"<b>{name}</b><br>"
            f"<span style='color:#95a5a6'>{group.count} parts · {group.directory or 'root'}</span>"
        )
        self._group_info.setTextFormat(Qt.TextFormat.RichText)
        self._btn_export_group.setEnabled(True)
        self._btn_export_group.setText(f"Export model group ({group.count} files)…")

    def log(self, msg: str):
        self._log.append(msg)

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_tex_export_toggled(self, checked: bool):
        """Show/hide texture format and embed controls based on checkbox state."""
        self._tex_fmt_combo.setEnabled(checked)
        self._embed_tex_chk.setEnabled(checked and
            self._fmt_combo.currentIndex() in (0, 1))  # only GLB/GLTF can embed

    def _on_lod_changed(self, index: int):
        self.lod_changed.emit(index)

    def _do_clear_export_list(self):
        self.clear_export_list()

    def set_zone(self, zone):
        """Called when a zone asset is loaded — enables zone export and debug buttons."""
        self._current_zone = zone
        self._btn_export_zone.setEnabled(zone is not None)
        self._btn_dump_zone.setEnabled(zone is not None)

    def _do_export_zone(self):
        """Triggered by Export Zone as GLB button."""
        zone = getattr(self, '_current_zone', None)
        if zone is None:
            return
        # Delegate to main window handler via signal
        self._export_zone_fn(zone)

    def set_export_zone_fn(self, fn):
        """Inject the export function from main_window to avoid circular imports."""
        self._export_zone_fn = fn

    def _do_dump_zone(self):
        """Report the same indexed entries used by scene display and export."""
        zone = getattr(self, '_current_zone', None)
        if zone is None:
            return
        lines = [f'[DUMP] Zone: {zone.name}',
                 f'[DUMP] {zone.entry_count} indexed nodes; matrices are zone-local']
        for entry in zone.entries[:5]:
            lines.extend([
                f'  [{entry.index}] {entry.name}',
                f'  Scene offset {entry.scene_offset:#x}, type {entry.node_type}, {len(entry.raw)} bytes',
                f'  Instance {entry.instance_id:016X}',
                f'  Actor {entry.asset_id:016X}, model {entry.model_id:016X}',
                f'  Renderer instance {entry.renderer_instance_id:016X}',
            ])
            for row in range(4):
                lines.append('  ' + ', '.join(f'{v:.6g}' for v in entry.matrix[row*4:row*4+4]))
            for component in entry.components:
                lines.append(f'  Component {component.name or "(unnamed)"}: '
                             f'type {component.type_id:08X}, {len(component.data)} bytes')
        self.log('\n'.join(lines))

    def _do_export_list(self):
        entries = self.get_export_list_entries()
        if not entries:
            return
        if self._toc_parser is None:
            self._list_status.setText("No game data loaded — open the Rift Apart folder first")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export List as GLB", "export_list.glb",
            "GLB Files (*.glb);;All Files (*.*)"
        )
        if not path:
            return

        self._btn_export_list.setEnabled(False)
        self._btn_clear_list.setEnabled(False)
        self._list_status.setText("Exporting…")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from core.mesh import ModelParser
            from exporters.group_exporter import GroupExporter

            exporter = GroupExporter()
            for entry in entries:
                try:
                    raw = self._toc_parser.extract_asset(entry)
                    model = ModelParser(raw).parse()
                    name = f"asset_{entry.asset_id:016X}"
                    # Try to get a display name from the list widget
                    for i in range(self._export_list_widget.count()):
                        item = self._export_list_widget.item(i)
                        if item.data(Qt.ItemDataRole.UserRole).asset_id == entry.asset_id:
                            name = item.text().rsplit('.', 1)[0]
                            break
                    exporter.add_model(model, name)
                except Exception as ex:
                    self._list_status.setText(f"Export failed on {entry.asset_id:#018x}: {ex}")
                    self._btn_export_list.setEnabled(True)
                    self._btn_clear_list.setEnabled(True)
                    return

            exporter.export_glb(path)
            import os
            self._list_status.setText(f"Exported {os.path.basename(path)}")
            self.log(f"[LIST OK] {path}")

        except Exception as ex:
            import traceback
            self._list_status.setText(f"Export failed: {ex}")
            self.log(f"[LIST ERROR] {ex}\n{traceback.format_exc()}")
        finally:
            self._btn_export_list.setEnabled(True)
            self._btn_clear_list.setEnabled(self._export_list_widget.count() > 0)

    def _do_export_group(self):
        if not self._group:
            return
        if self._toc_parser is None:
            self._export_status.setText("No game data loaded — open the Rift Apart folder first")
            return

        name = self._group.slug.rsplit('/', 1)[-1]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Group as GLB", name + ".glb", "GLB Files (*.glb);;All Files (*.*)"
        )
        if not path:
            return

        self._btn_export_group.setEnabled(False)
        self._btn_export.setEnabled(False)
        self._progress.setVisible(True)
        self._export_status.setText("Starting group export…")

        self._export_thread = QThread(self)
        worker = GroupExportWorker(self._group, self._toc_parser, path)
        worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(worker.run)
        worker.progress.connect(self._export_status.setText)
        worker.finished.connect(self._on_group_export_done)
        worker.error.connect(self._on_export_error)
        worker.finished.connect(self._export_thread.quit)
        worker.error.connect(self._export_thread.quit)
        self._export_thread.start()

    def _on_group_export_done(self, path: str):
        self._progress.setVisible(False)
        self._btn_export_group.setEnabled(True)
        self._btn_export.setEnabled(self._mesh_asset is not None)
        self._export_status.setText(f"Exported model group to {os.path.basename(path)}")
        self.log(f"[GROUP OK] {path}")

    def _do_export(self):
        if self._mesh_asset is None:
            return

        fmt_map = {0: 'glb', 1: 'gltf', 2: 'obj', 3: 'fbx', 4: 'ascii'}
        fmt = fmt_map[self._fmt_combo.currentIndex()]
        ext = {
            'glb':   '.glb',
            'gltf':  '.gltf',
            'obj':   '.obj',
            'fbx':   '.fbx',
            'ascii': '.ascii',
        }[fmt]

        # Use asset name from browser if available, fall back to hex ID
        if self._asset_name:
            name = os.path.splitext(self._asset_name)[0]
        elif self._entry:
            name = f"{self._entry.asset_id:016X}"
        else:
            name = "export"

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Asset", name + ext,
            f"3D Files (*{ext});;All Files (*.*)"
        )
        if not path:
            return

        self._btn_export.setEnabled(False)
        self._progress.setVisible(True)
        self._export_status.setText("Exporting…")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from exporters.gltf_exporter import GltfExporter, ObjExporter
            lod    = self._lod_combo.currentIndex()
            stem   = os.path.splitext(os.path.basename(path))[0]
            outdir = os.path.dirname(path)

            if fmt == 'glb':
                GltfExporter(self._mesh_asset, stem, lod=lod).export_glb(path)
            elif fmt == 'gltf':
                GltfExporter(self._mesh_asset, stem, lod=lod).export_gltf(path)
            elif fmt == 'obj':
                ObjExporter(self._mesh_asset, stem, lod=lod).export(path)
            elif fmt == 'fbx':
                from exporters.fbx_exporter import FbxExporter
                FbxExporter(self._mesh_asset, stem, lod=lod).export(path)
            elif fmt == 'ascii':
                from exporters.ascii_exporter import export_ascii
                export_ascii(self._mesh_asset, path, lod=lod)

            # ── Texture export ────────────────────────────────────────────────
            tex_data = getattr(self, '_cached_tex_data', None)
            if (self._export_tex_chk.isChecked()
                    and tex_data
                    and fmt in ('glb', 'gltf', 'fbx', 'obj')):
                try:
                    from exporters.texture_exporter import TextureExporter
                    tex_fmt_map = {0: 'png', 1: 'dds', 2: 'both'}
                    tex_fmt = tex_fmt_map[self._tex_fmt_combo.currentIndex()]

                    mat_names = getattr(self, '_mat_names', {})
                    exporter = TextureExporter(tex_data, mat_names, outdir, stem)
                    exported = exporter.export(fmt=tex_fmt)

                    n_tex = sum(len(r) for r in exported.values())
                    print(f"[texexport] exported {n_tex} texture(s) to {outdir}/textures/")
                except Exception as tex_ex:
                    import traceback
                    print(f"[texexport] texture export failed: {tex_ex}\n{traceback.format_exc()}")

            self._on_export_done(path)
        except Exception as ex:
            import traceback
            self._on_export_error(f"{ex}\n{traceback.format_exc()}")

    def _on_export_done(self, path: str):
        self._progress.setVisible(False)
        self._btn_export.setEnabled(True)
        self._export_status.setText(f"Exported to {os.path.basename(path)}")
        self.log(f"[OK] {path}")

    def _on_export_error(self, msg: str):
        self._progress.setVisible(False)
        self._btn_export.setEnabled(True)
        self._export_status.setText(f"Export error: {msg}")
        self.log(f"[ERR] {msg}")

    @staticmethod
    def _field_label() -> QLabel:
        lbl = QLabel("—")
        lbl.setObjectName("FieldValue")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return lbl
