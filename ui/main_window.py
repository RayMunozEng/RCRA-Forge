"""
ui/main_window.py
RCRA Forge — Main Application Window
"""

import os
from core.theme import theme_manager
from ui.preferences_dialog import PreferencesDialog
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QMenuBar, QMenu, QToolBar, QStatusBar, QFileDialog,
    QMessageBox, QApplication, QLabel, QFrame, QTabWidget, QPushButton
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QFont, QColor

from ui.asset_browser import AssetBrowser
from ui.properties_panel import PropertiesPanel
from ui.viewport import Viewport3D
from ui.model_preview import SoftwareModelPreview
from ui.texture_viewer import TextureViewer
from ui.controls_dialog import ControlsDialog
from ui.scene_panel import ScenePanel
from ui.hex_inspector import HexInspector
from ui.skeleton_viewer import SkeletonViewer
from ui.asset_overview import AssetOverview
from core.archive import TocParser, AssetEntry, ASSET_TYPE_NAMES


def _is_effect_role(role: str) -> bool:
    return (
        role == 'emissive'
        or role.startswith('emissive_')
        or role == 'retail_lava_color_a'
    )


# ── Background loader ──────────────────────────────────────────────────────────

class TocLoader(QObject):
    finished      = pyqtSignal(object, object, str, list)  # parser, entries, timing, groups
    hashes_ready  = pyqtSignal(object)                     # lookup (after background load)
    progress      = pyqtSignal(str)
    error         = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        """
        Qt threading adapter — delegates all TOC parsing to core/archive.py.
        No parse logic lives here; this method only wires signals and timing.
        """
        import time
        import threading
        print(f"[TocLoader] run() started, path={self.path}")
        try:
            t0 = time.time()

            from core.archive import TocParser
            from core.hashes import get_lookup, try_load_from_game_root

            parser = TocParser(self.path)

            # parse_with_progress owns all read/decompress/index steps
            steps: list[tuple[float, str]] = []
            def _on_progress(msg: str):
                steps.append((time.time(), msg))
                self.progress.emit(msg)

            parser.parse_with_progress(_on_progress)
            entries = parser.entries

            self.progress.emit("Grouping assets by archive\u2026")
            print("[TocLoader] grouping...")
            groups = parser.group_by_archive()
            print(f"[TocLoader] grouped into {len(groups)} archives")

            # Load hashes.txt on a daemon thread; emit hashes_ready when done
            self.progress.emit("TOC ready \u2014 loading asset names in background\u2026")
            game_root = os.path.dirname(self.path)
            lookup    = get_lookup()
            print(f"[TocLoader] starting hashes thread, game_root={game_root}")

            def _load_hashes():
                print("[hashes thread] starting...")
                try_load_from_game_root(game_root)
                print(f"[hashes thread] done, {len(lookup)} entries")
                self.hashes_ready.emit(lookup)

            threading.Thread(target=_load_hashes, daemon=True).start()

            # Build timing string from progress step timestamps
            t_total = time.time() - t0
            if len(steps) >= 3:
                t_disk  = steps[1][0] - steps[0][0]
                t_dat1  = steps[2][0] - steps[1][0]
                t_index = time.time() - steps[2][0]
                timing  = (f"disk:{t_disk:.2f}s  dat1:{t_dat1:.2f}s  "
                           f"index:{t_index:.2f}s  total:{t_total:.2f}s")
            else:
                timing = f"total:{t_total:.2f}s"

            print(f"[TocLoader] emitting finished signal, {len(entries):,} entries")
            self.progress.emit(f"Done \u2014 {len(entries):,} assets  (names loading\u2026)")
            self.finished.emit(parser, entries, timing, groups)
        except Exception as ex:
            import traceback
            self.error.emit(f"{ex}\n{traceback.format_exc()}")
class AssetLoader(QObject):
    """
    Qt threading adapter — runs core.asset_loader on a background thread
    and fans out results as typed signals.

    All dispatch and parse logic lives in core/asset_loader.py.
    This class is a thin signal bridge: no parsing happens here.
    """
    mesh_ready      = pyqtSignal(object)        # ModelAsset
    texture_ready   = pyqtSignal(object)        # TextureAsset
    materials_ready = pyqtSignal(dict)          # {mat_idx: {role: (rgba, w, h, tex_name)}}
    materials_finished = pyqtSignal(dict)       # complete decoded material map
    fur_environment_ready = pyqtSignal(object, bytes, object)
    skel_ready      = pyqtSignal(object)        # Skeleton
    zone_ready      = pyqtSignal(object)        # ZoneDef
    level_ready     = pyqtSignal(object, object)
    raw_ready       = pyqtSignal(bytes, str)    # raw bytes, label
    result_ready    = pyqtSignal(object)        # core.asset_loader.AssetResult
    error           = pyqtSignal(str)
    completed       = pyqtSignal()

    def __init__(self, entry, toc_parser, lookup=None):
        super().__init__()
        self.entry      = entry
        self.toc_parser = toc_parser
        self.lookup     = lookup

    def _emit_fur_environment(self, tex_data: dict) -> None:
        """Load recovered Hair defaults only for models that actually use fur."""
        has_fur = any(
            isinstance(slots, dict) and 'fur_control' in slots
            for slots in (tex_data or {}).values()
        )
        if not has_fur:
            return
        from core.fur_resources import default_hair_brdf_rg_half
        from core.texture import TextureParser

        # Captured g_EnvProbeDefault at the verified retail Hair dispatch.
        probe_entry = self.toc_parser.find_entry(0x8F083136CEB5FB07)
        if probe_entry is None:
            print("[AssetLoader] recovered Hair environment is absent from TOC")
            return
        probe = TextureParser(
            self.toc_parser.extract_asset(probe_entry)
        ).parse()
        cube_mips = probe.decoded_cube_mips_rgb_half()
        if not cube_mips:
            print("[AssetLoader] recovered Hair environment failed BC6 decode")
            return
        self.fur_environment_ready.emit(
            cube_mips, default_hair_brdf_rg_half(), (64, 64),
        )

    def run(self):
        try:
            from core.asset_loader import load_asset, load_model_textures
            from core.hashes import get_lookup

            result = load_asset(self.entry, self.toc_parser, self.lookup)

            # Raw bytes always emitted first (feeds hex inspector)
            self.raw_ready.emit(result.raw, result.label)
            self.result_ready.emit(result)

            if result.error and not any([result.model, result.texture,
                                         result.actor, result.zone, result.level]):
                self.error.emit(result.error)
                return

            if result.actor is not None:
                actor = result.actor
                if not actor.model_asset_id:
                    return
                model_entry = self.toc_parser.find_entry(actor.model_asset_id)
                if model_entry is None:
                    return
                model_result = load_asset(model_entry, self.toc_parser, self.lookup)
                if model_result.model is None:
                    self.error.emit(model_result.error or "Linked actor model could not be parsed")
                    return
                self.mesh_ready.emit(model_result.model)
                if model_result.skeleton is not None:
                    self.skel_ready.emit(model_result.skeleton)
                lookup = self.lookup or get_lookup()
                tex_data = load_model_textures(
                    model_result.model, model_entry, self.toc_parser, lookup,
                )
                if tex_data:
                    self.materials_ready.emit(tex_data)
                    self._emit_fur_environment(tex_data)
                self.materials_finished.emit(tex_data)
                return

            if result.model is not None:
                self.mesh_ready.emit(result.model)
                if result.skeleton is not None:
                    self.skel_ready.emit(result.skeleton)
                lookup = self.lookup or get_lookup()
                tex_data = load_model_textures(
                    result.model, self.entry, self.toc_parser, lookup,
                )
                if tex_data:
                    self.materials_ready.emit(tex_data)
                    self._emit_fur_environment(tex_data)
                self.materials_finished.emit(tex_data)

            elif result.texture is not None:
                texture = result.texture
                if texture.hd_len > 0 and texture.hd_width > 0:
                    candidates = [
                        candidate
                        for candidate in self.toc_parser.find_all_entries(self.entry.asset_id)
                        if candidate.size > self.entry.size
                    ]
                    if candidates:
                        try:
                            hd_entry = max(candidates, key=lambda candidate: candidate.size)
                            texture.hd_pixel_data = bytes(
                                self.toc_parser.extract_asset(hd_entry)
                            )
                        except Exception as ex:
                            print(f"[AssetLoader] HD texture load failed: {ex}")
                self.texture_ready.emit(result.texture)

            elif result.zone is not None:
                self.zone_ready.emit(result.zone)

            elif result.level is not None:
                self.level_ready.emit(result.level, None)

            # Unknown/unhandled types: raw already emitted, nothing more to do.

        except Exception as ex:
            import traceback
            self.error.emit(f"{ex}\n{traceback.format_exc()}")
        finally:
            self.completed.emit()


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RCRA Forge — Rift Apart Asset Browser")
        self.resize(1440, 900)
        self._load_thread:   QThread    = None
        self._asset_thread:  QThread    = None
        self._toc_parser:    TocParser  = None
        self._toc_path:      str        = None   # path to loaded 'toc' file
        self._loader        = None   # keeps TocLoader alive during thread run
        self._asset_loader  = None   # keeps AssetLoader alive during thread run
        self._queued_entry  = None
        self._current_actor = None
        self._ready_library_presented = False
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._apply_theme()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Clear source and library summary.
        hero = QFrame()
        hero.setObjectName("AppHero")
        hero.setFixedHeight(92)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 12, 18, 12)
        hero_layout.setSpacing(18)

        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = QLabel("RCRA Forge")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Ratchet & Clank: Rift Apart · Game asset browser")
        subtitle.setObjectName("AppSubtitle")
        self._active_asset_lbl = QLabel("Connecting to the Steam archive…")
        self._active_asset_lbl.setObjectName("ActiveAssetLabel")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        brand.addWidget(self._active_asset_lbl)
        hero_layout.addLayout(brand, 1)

        for key, value_attr, initial in (
            ("TOTAL ASSETS", "_hero_assets", "—"),
            ("GAME ARCHIVES", "_hero_archives", "—"),
            ("KNOWN NAMES", "_hero_named", "—"),
        ):
            card = QFrame()
            card.setObjectName("StatCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 7, 12, 7)
            card_layout.setSpacing(0)
            value = QLabel(initial)
            value.setObjectName("StatValue")
            label = QLabel(key)
            label.setObjectName("StatKey")
            card_layout.addWidget(value, alignment=Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)
            setattr(self, value_attr, value)
            hero_layout.addWidget(card)

        live_chip = QLabel("Steam game data")
        live_chip.setObjectName("LiveChip")
        live_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        live_chip.setFixedSize(108, 34)
        hero_layout.addWidget(live_chip)
        root.addWidget(hero)

        # ── Outer horizontal split: [Asset Browser | Main Area] ──────────────
        outer = QSplitter(Qt.Orientation.Horizontal)
        outer.setChildrenCollapsible(False)
        root.addWidget(outer, 1)

        # Left: Asset browser
        self._browser = AssetBrowser()
        self._browser.setMinimumWidth(320)
        self._browser.asset_activated.connect(self._on_asset_activated)
        self._browser.group_activated.connect(self._on_group_activated)
        self._browser.quick_export_requested.connect(self._on_quick_export)
        self._browser.add_to_list_requested.connect(self._on_add_to_export_list)
        self._browser.remove_from_list_requested.connect(self._on_remove_from_export_list)
        outer.addWidget(self._browser)

        # ── Right side: vertical split [Viewport top | Tabs bottom] ──────────
        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.setChildrenCollapsible(False)
        outer.addWidget(self._right_splitter)
        outer.setStretchFactor(0, 1)
        outer.setStretchFactor(1, 2)

        # ── Top: horizontal split [3D Viewport | Properties] ─────────────────
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_splitter.setChildrenCollapsible(False)
        self._right_splitter.addWidget(self._top_splitter)

        self._model_views = QTabWidget()
        self._model_views.setObjectName("ModelViewTabs")
        self._software_preview = SoftwareModelPreview()
        self._viewport = Viewport3D()
        self._viewport.setMinimumHeight(200)
        self._model_views.addTab(self._software_preview, "Model Preview")
        self._model_views.addTab(self._viewport, "Textured 3D")
        self._model_views.setToolTip(
            "Model Preview always shows parsed geometry. "
            "Textured 3D uses the graphics card for materials and interactive inspection."
        )
        self._top_splitter.addWidget(self._model_views)

        self._props = PropertiesPanel()
        self._props.set_export_zone_fn(self._on_export_zone_requested)
        self._props.setMinimumWidth(200)
        self._top_splitter.addWidget(self._props)
        self._top_splitter.setSizes([900, 280])
        self._props.lod_changed.connect(self._viewport.set_lod)

        # ── Bottom: tabbed panel [Texture | Scene | Skeleton | Hex] ──────────
        self._tab_panel = QTabWidget()
        self._tab_panel.setObjectName("BottomTabs")
        self._tab_panel.setMinimumHeight(312)
        self._right_splitter.addWidget(self._tab_panel)

        self._right_splitter.setSizes([520, 300])
        self._right_splitter.setStretchFactor(0, 1)  # viewport stretches
        self._right_splitter.setStretchFactor(1, 0)  # bottom panel holds size

        # Tab: Texture viewer
        self._overview = AssetOverview()
        self._tab_panel.addTab(self._overview, "Asset Details")

        self._tex_viewer = TextureViewer()
        self._tab_panel.addTab(self._tex_viewer, "Texture Preview")

        # Tab: Scene hierarchy
        self._scene_panel = ScenePanel()
        self._scene_panel.instance_selected.connect(self._on_instance_selected)
        self._tab_panel.addTab(self._scene_panel, "Scene Objects")

        # Tab: Skeleton
        self._skel_viewer = SkeletonViewer()
        self._tab_panel.addTab(self._skel_viewer, "Skeleton")

        # Tab: Hex inspector
        self._hex_inspector = HexInspector()
        self._tab_panel.addTab(self._hex_inspector, "Raw Bytes")

        outer.setSizes([480, 960])
        # The landing page is the Overview.  Do not show an empty black model
        # viewport before the user has selected a model.
        self._top_splitter.setVisible(False)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_lbl = QLabel("Ready — open a game folder to begin")
        self._status.addWidget(self._status_lbl)

        # Loading progress bar (hidden until TOC load starts)
        from PyQt6.QtWidgets import QProgressBar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate spinner
        self._progress.setFixedWidth(120)
        self._progress.setFixedHeight(20)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._status.addPermanentWidget(self._progress)

        # Permanent right-side status info
        self._status_right = QLabel("")
        self._status.addPermanentWidget(self._status_right)

    def _setup_menus(self):
        mb = QMenuBar(self)
        self.setMenuBar(mb)

        # File
        file_m = mb.addMenu("File")
        act_open = QAction("Open Game Folder…", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._open_game_folder)
        file_m.addAction(act_open)

        act_toc = QAction("Open TOC File…", self)
        act_toc.triggered.connect(self._open_toc_file)
        file_m.addAction(act_toc)

        act_hashes = QAction("Load hashes.txt…", self)
        act_hashes.triggered.connect(self._load_hashes_file)
        file_m.addAction(act_hashes)

        file_m.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(QApplication.quit)
        file_m.addAction(act_quit)

        # Edit
        edit_m = mb.addMenu("Edit")
        act_prefs = QAction("Preferences…", self)
        act_prefs.setShortcut(QKeySequence("Ctrl+,"))
        act_prefs.triggered.connect(self._open_preferences)
        edit_m.addAction(act_prefs)

        # View
        view_m = mb.addMenu("View")
        self._act_wire = QAction("Wireframe", self)
        self._act_wire.setCheckable(True)
        self._act_wire.triggered.connect(self._toggle_wireframe)
        view_m.addAction(self._act_wire)

        self._act_bloom = QAction("Bloom and emissive glow", self)
        self._act_bloom.setCheckable(True)
        self._act_bloom.setChecked(True)
        self._act_bloom.setToolTip(
            "Apply HDR glow around lava, energy, lights, and other emissive materials."
        )
        self._act_bloom.toggled.connect(self._viewport.set_bloom_enabled)
        view_m.addAction(self._act_bloom)

        act_frame = QAction("Frame Model", self)
        act_frame.setShortcut(QKeySequence("F"))
        act_frame.triggered.connect(self._frame_scene)
        view_m.addAction(act_frame)

        act_search = QAction("Focus Asset Search", self)
        act_search.setShortcut(QKeySequence("Ctrl+L"))
        act_search.triggered.connect(self._browser.focus_search)
        view_m.addAction(act_search)

        view_m.addSeparator()

        act_controls = QAction("Viewport Controls…", self)
        act_controls.setShortcut(QKeySequence("Ctrl+K"))
        act_controls.triggered.connect(self._open_controls_dialog)
        view_m.addAction(act_controls)

        # Help
        help_m = mb.addMenu("Help")
        act_about = QAction("About RCRA Forge", self)
        act_about.triggered.connect(self._show_about)
        help_m.addAction(act_about)

    def _setup_toolbar(self):
        tb = QToolBar("Main Toolbar", self)
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)

        act_open = QAction("Open Rift Apart Folder", self)
        act_open.triggered.connect(self._open_game_folder)
        tb.addAction(act_open)

        tb.addSeparator()
        act_search = QAction("Find an Asset", self)
        act_search.setShortcut(QKeySequence("Ctrl+L"))
        act_search.triggered.connect(self._browser.focus_search)
        tb.addAction(act_search)

        tb.addSeparator()

        guidance = QLabel("  Choose a category, then click a row to preview it.  ")
        guidance.setObjectName("ToolbarGuidance")
        tb.addWidget(guidance)

        self._game_path_lbl = QLabel("  Rift Apart folder not loaded  ")
        self._game_path_lbl.setObjectName("GamePathLabel")
        tb.addWidget(self._game_path_lbl)

    # ── Theming ───────────────────────────────────────────────────────────────

    def _apply_theme(self):
        self._load_config()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_game_folder(self):
        import string, ctypes

        # Get all available drive letters on Windows
        drives = []
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(letter)
                bitmask >>= 1
        except Exception:
            drives = list('CDEFGHIJKLMNOPQRSTUVWXYZ')

        # Search all drives for Steam install
        steam_subpaths = [
            r"Steam\steamapps\common\Ratchet & Clank - Rift Apart",
            r"SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart",
            r"Games\Steam\steamapps\common\Ratchet & Clank - Rift Apart",
            r"Program Files (x86)\Steam\steamapps\common\Ratchet & Clank - Rift Apart",
            r"Program Files\Steam\steamapps\common\Ratchet & Clank - Rift Apart",
        ]

        default_dir = ""
        for drive in drives:
            for sub in steam_subpaths:
                candidate = f"{drive}:\\{sub}"
                if os.path.exists(candidate):
                    default_dir = candidate
                    break
            if default_dir:
                break

        folder = QFileDialog.getExistingDirectory(
            self, "Select Rift Apart Game Folder", default_dir
        )
        if not folder:
            return

        self.load_game_folder(folder)

    def load_game_folder(self, folder: str) -> bool:
        """Load a Rift Apart install without requiring a folder dialog."""
        folder = os.path.abspath(folder)
        toc_candidates = [
            os.path.join(folder, 'toc'),
            os.path.join(folder, 'data', 'toc'),
        ]
        toc_path = next((p for p in toc_candidates if os.path.exists(p)), None)

        if not toc_path:
            QMessageBox.warning(self, "TOC Not Found",
                f"Could not find a 'toc' file in:\n{folder}\n\n"
                "Make sure you selected the correct game folder containing the 'toc' file.")
            return False

        self._load_toc(toc_path)
        self._game_path_lbl.setText(f"  {os.path.basename(folder)}  ")
        return True

    def _load_hashes_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load hashes.txt", "",
            "Hash files (hashes.txt);;Text Files (*.txt);;All Files (*.*)"
        )
        if not path:
            return
        from core.hashes import get_lookup
        lookup = get_lookup()
        count = lookup.load(path)
        self._status_lbl.setText(f"Loaded {count:,} asset names from hashes.txt")
        # Refresh the browser with new names if TOC is already loaded
        if self._toc_parser:
            self._browser.set_lookup(lookup)

    def _open_toc_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open TOC File", "", "TOC Files (toc);;All Files (*.*)"
        )
        if path:
            self._load_toc(path)

    def _load_toc(self, path: str):
        import time
        if self._load_thread is not None and self._load_thread.isRunning():
            self._status_lbl.setText("Steam archive index is already loading — please wait")
            return
        # A new load must not let the hashes callback pair with the previous
        # parser and mark the library ready before this TOC finishes.
        self._toc_parser = None
        self._toc_path = path
        self._toc_load_start = time.time()
        toc_size_mb = os.path.getsize(path) / (1024*1024)
        self._status_lbl.setText(
            f"Loading toc… ({toc_size_mb:.1f} MB)  please wait"
        )
        self._progress.setVisible(True)
        self._browser.clear()
        self._ready_library_presented = False

        self._load_thread = QThread(self)
        self._loader = TocLoader(path)          # keep reference on self!
        self._loader.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._loader.run)
        self._loader.progress.connect(self._status_lbl.setText)
        self._loader.finished.connect(self._on_toc_loaded)
        self._loader.hashes_ready.connect(self._on_hashes_ready)
        self._loader.error.connect(self._on_load_error)
        self._loader.finished.connect(self._load_thread.quit)
        self._loader.error.connect(self._load_thread.quit)
        self._load_thread.start()
        print(f"[_load_toc] thread started for {path}")

    def _on_toc_loaded(self, parser, entries, timing, groups):
        import time
        t0 = time.perf_counter()
        elapsed_wall = time.time() - getattr(self, '_toc_load_start', 0)
        self._toc_parser = parser
        self._progress.setVisible(False)
        self._props.set_toc_parser(parser, self._toc_path)
        t1 = time.perf_counter()
        from core.hashes import get_lookup
        lookup = get_lookup()
        visible_lookup = lookup if lookup and lookup.is_loaded() else None
        self._browser.load_entries_grouped(entries, groups, visible_lookup)
        self._hero_assets.setText(f"{len(entries):,}")
        self._hero_archives.setText(f"{len(parser.archives):,}")
        self._active_asset_lbl.setText("Index ready — resolving human-readable asset names…")
        t2 = time.perf_counter()
        print(f"[main] progress_hide:{t1-t0:.3f}s  load_browser:{t2-t1:.3f}s  "
              f"wall:{elapsed_wall:.2f}s")
        self._status_lbl.setText(
            f"Loaded {len(entries):,} assets  ·  "
            f"{len(parser.archives)} archives  ·  "
            f"wall:{elapsed_wall:.1f}s  [{timing}]  — names loading…"
        )

        self._present_ready_library(visible_lookup)

    def _on_hashes_ready(self, lookup):
        """Called when hashes.txt finishes loading in background."""
        self._browser.set_lookup(lookup)
        self._present_ready_library(lookup)

    def _present_ready_library(self, lookup):
        """Expose a populated browse view once both TOC and names are ready."""
        if self._ready_library_presented:
            return
        if not self._toc_parser or not lookup or not lookup.is_loaded():
            return

        n = len(lookup) if lookup and lookup.is_loaded() else 0
        named_installed = 0
        counts = {"model": 0, "texture": 0, "actor": 0}
        if self._toc_parser and lookup and lookup.is_loaded():
            try:
                ids = self._toc_parser.entries._ids[:len(self._toc_parser.entries)]
                for asset_id in ids:
                    path = lookup.lookup(int(asset_id))
                    if not path:
                        continue
                    named_installed += 1
                    path = path.casefold()
                    if path.endswith(".model"):
                        counts["model"] += 1
                    elif path.endswith(".texture"):
                        counts["texture"] += 1
                    elif path.endswith(".actor"):
                        counts["actor"] += 1
            except Exception:
                named_installed = n
        self._hero_named.setText(f"{named_installed:,}")
        current = self._status_lbl.text()
        current = current.replace("— asset names loading…", "").replace("— names loading…", "")
        self._status_lbl.setText(f"{current.strip()}  ·  {n:,} names")
        # Present a useful populated browser immediately without choosing or
        # opening a specific asset.  Raw archive buckets looked like an empty
        # tool to users because every useful row was hidden behind a folder.
        active_search = self._browser._search.text()
        active_filter = self._browser.current_type_filter()
        if not active_search.strip() and active_filter == "All Types":
            active_filter = ".model"
        # Reapply even an existing filter: load_entries_grouped deliberately
        # rebuilds archive wrappers, so a same-folder reload otherwise leaves
        # the combo saying models while showing only game-archive folders.
        self._browser.set_search(active_search, active_filter)
        self._overview.show_ready(
            len(self._toc_parser.entries) if self._toc_parser else 0,
            counts["model"],
            counts["texture"],
            counts["actor"],
        )
        self._active_asset_lbl.setText(
            f"Ready — {counts['model']:,} models listed • click one to preview"
        )
        self._ready_library_presented = True

    def _on_load_error(self, msg: str):
        self._progress.setVisible(False)
        self._status_lbl.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Load Error", msg)

    def _on_asset_activated(self, entry):
        if self._toc_parser is None:
            self._status_lbl.setText("No TOC loaded — open a game folder first")
            return

        if self._asset_thread is not None and self._asset_thread.isRunning():
            self._queued_entry = entry
            self._status_lbl.setText("Preview queued — finishing the current asset…")
            return

        # Get display name from lookup for the export filename
        lookup = self._browser._lookup
        asset_name = None
        full_path = f"{entry.asset_id:016X}"
        if lookup and lookup.is_loaded():
            asset_name = lookup.name(entry.asset_id)
            full_path = lookup.full_path(entry.asset_id)
            self._active_asset_lbl.setText(full_path)

        self._props.set_entry(entry, name=asset_name)
        # Texture data belongs to exactly one selected asset. Keeping the
        # previous model's cache could make a later material index accidentally
        # display or export the wrong texture.
        self._props._cached_tex_data = {}
        self._props._mat_names = {}
        self._model_views.setTabText(1, "Textured 3D")
        self._model_views.setTabToolTip(
            1, "Game textures will appear here when the selected model references them."
        )
        self._current_entry = entry   # cached for texture export mat_names lookup
        self._current_actor = None
        extension = full_path.rsplit('.', 1)[-1] if '.' in full_path else "raw"
        self._overview.show_loading(
            asset_name or f"{entry.asset_id:016X}", full_path, extension, entry.size
        )
        self._top_splitter.setVisible(False)
        self._right_splitter.setSizes([0, 820])
        self._tab_panel.setCurrentWidget(self._overview)
        self._status_lbl.setText(f"Loading asset {entry.asset_id:#018x}…")

        self._asset_thread = QThread(self)
        self._asset_loader = AssetLoader(entry, self._toc_parser, self._browser._lookup)  # keep reference!
        self._asset_loader.moveToThread(self._asset_thread)
        self._asset_thread.started.connect(self._asset_loader.run)

        self._asset_loader.mesh_ready.connect(self._on_mesh_ready)
        self._asset_loader.texture_ready.connect(self._on_texture_ready)
        self._asset_loader.materials_ready.connect(self._viewport.load_textures)
        self._asset_loader.materials_ready.connect(self._software_preview.load_textures)
        self._asset_loader.materials_ready.connect(self._on_materials_ready)
        self._asset_loader.fur_environment_ready.connect(
            self._viewport.set_fur_environment
        )
        self._asset_loader.materials_finished.connect(self._on_materials_finished)
        self._asset_loader.skel_ready.connect(self._on_skel_ready)
        self._asset_loader.zone_ready.connect(self._on_zone_ready)
        self._asset_loader.level_ready.connect(self._on_level_ready)
        self._asset_loader.raw_ready.connect(self._on_raw_ready)
        self._asset_loader.result_ready.connect(self._on_result_ready)
        self._asset_loader.error.connect(self._on_asset_error)

        # One completion signal covers models, textures, zones and raw assets.
        # The previous signal-specific scheme left some worker threads alive.
        self._asset_loader.completed.connect(self._asset_thread.quit)
        self._asset_loader.completed.connect(self._asset_loader.deleteLater)
        self._asset_thread.finished.connect(self._on_asset_thread_finished)

        self._asset_thread.start()

    def _on_asset_thread_finished(self):
        thread = self._asset_thread
        self._asset_thread = None
        self._asset_loader = None
        if thread is not None:
            thread.deleteLater()
        if self._queued_entry is not None:
            entry = self._queued_entry
            self._queued_entry = None
            QTimer.singleShot(0, lambda e=entry: self._on_asset_activated(e))

    def _on_group_activated(self, group):
        """User double-clicked a named group in the Groups tree view."""
        self._props.set_group(group)
        name = group.slug.rsplit('/', 1)[-1]
        self._status_lbl.setText(
            f"Group selected: {name}  ({group.count} parts) — "
            f"click 'Export Group as GLB' in Properties to export"
        )

    def _on_quick_export(self, entry, fmt: str):
        """Handle right-click quick export from asset browser."""
        from PyQt6.QtWidgets import QFileDialog
        import os

        # Get asset name for filename
        lookup = self._browser._lookup
        name = None
        if lookup and lookup.is_loaded():
            name = lookup.name(entry.asset_id)
        stem = (name or f"asset_{entry.asset_id:016X}").rsplit('.', 1)[0]

        ext_map = {'glb': 'GLB Files (*.glb)', 'fbx': 'FBX Files (*.fbx)', 'obj': 'OBJ Files (*.obj)'}
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {fmt.upper()}", f"{stem}.{fmt}",
            f"{ext_map.get(fmt, 'All Files (*.*)')};;All Files (*.*)"
        )
        if not path:
            return

        if not self._toc_path:
            self._status_lbl.setText("No game data loaded")
            return

        try:
            from core.archive import TocParser
            from core.mesh import ModelParser

            toc = TocParser(self._toc_path)
            toc.parse()
            raw = toc.extract_asset(entry)
            model = ModelParser(raw).parse()

            if fmt == 'glb':
                from exporters.gltf_exporter import GltfExporter
                GltfExporter(model, name=stem).export(path)
            elif fmt == 'fbx':
                from exporters.fbx_exporter import FbxExporter
                FbxExporter(model, name=stem).export(path)
            elif fmt == 'obj':
                from exporters.gltf_exporter import ObjExporter
                ObjExporter(model, name=stem).export(path)

            self._status_lbl.setText(f"Exported {stem}.{fmt}")
        except Exception as ex:
            import traceback
            self._status_lbl.setText(f"Export failed: {ex}")
            print(f"[quick_export] error: {ex}\n{traceback.format_exc()}")

    def _on_add_to_export_list(self, entry):
        """Handle right-click add to export list from asset browser."""
        lookup = self._browser._lookup
        name = None
        if lookup and lookup.is_loaded():
            name = lookup.name(entry.asset_id)
        self._props.add_to_export_list(entry, name=name)
        self._browser.mark_export_list(
            {e.asset_id for e in self._props.get_export_list_entries()}
        )

    def _on_remove_from_export_list(self, entry):
        """Handle right-click remove from export list from asset browser."""
        self._props.remove_from_export_list(entry)
        self._browser.mark_export_list(
            {e.asset_id for e in self._props.get_export_list_entries()}
        )

    def _on_mesh_ready(self, model_asset):
        self._top_splitter.setVisible(True)
        self._right_splitter.setSizes([500, 320] if self._current_actor else [590, 230])
        self._software_preview.load_mesh(model_asset)
        self._viewport.load_mesh(model_asset)
        self._model_views.setCurrentWidget(self._software_preview)
        self._props.set_mesh_asset(model_asset)
        from core.mesh import mesh_to_numpy
        total_verts = 0
        total_tris  = 0
        for mesh in model_asset.meshes:
            pos, _, _, idx = mesh_to_numpy(model_asset, mesh)
            if pos is not None: total_verts += len(pos)
            if idx is not None: total_tris  += len(idx) // 3
        self._model_status_base = (
            f"Model loaded — {total_verts:,} vertices, {total_tris:,} triangles, "
            f"{len(model_asset.meshes)} sub-meshes, {len(model_asset.joints)} bones"
        )
        self._status_lbl.setText(f"{self._model_status_base} · loading textures…")
        self._status_right.setText("Textures: loading…")
        self._model_views.setTabText(1, "Textured 3D (loading…)")
        if self._current_actor is None:
            self._overview.show_visual(
                "3D model",
                "Use Model Preview for fast geometry. Referenced game textures "
                "and animated effects appear in the GPU view as they finish loading.",
                f"{total_verts:,} vertices\n{total_tris:,} triangles\n"
                f"{len(model_asset.meshes)} sub-meshes\n{len(model_asset.joints)} bones",
            )
        else:
            self._tab_panel.setCurrentWidget(self._overview)

    def _on_texture_ready(self, tex_asset):
        # Textures deserve the main stage; keeping an empty black 3D viewport
        # above them made successful loads look like failures.
        self._top_splitter.setVisible(False)
        self._right_splitter.setSizes([0, 820])
        self._tex_viewer.load_texture(tex_asset)
        self._tab_panel.setCurrentWidget(self._tex_viewer)
        self._status_lbl.setText(
            f"Texture loaded — {tex_asset.width}×{tex_asset.height} {tex_asset.format_name}"
        )
        self._overview.show_visual(
            "Texture",
            "The selected texture is visible in the main image viewer.",
            f"{tex_asset.width} × {tex_asset.height}\n{tex_asset.format_name}\n"
            f"{tex_asset.mips} mip levels",
        )

    def _on_result_ready(self, result):
        """Turn every parsed result into an obvious, user-visible response."""
        lookup = self._browser._lookup
        entry = getattr(self, '_current_entry', None)
        path = lookup.full_path(entry.asset_id) if entry and lookup and lookup.is_loaded() \
            else (result.label or "Unknown asset")

        if result.actor is not None:
            self._current_actor = result.actor
            self._overview.show_actor(result.actor, path)
            self._tab_panel.setCurrentWidget(self._overview)
            if not result.actor.model_asset_id:
                self._top_splitter.setVisible(False)
                self._right_splitter.setSizes([0, 820])
                self._status_lbl.setText(
                    "Actor loaded — data only; no renderable model is referenced"
                )
            else:
                self._status_lbl.setText("Actor loaded — resolving linked 3D model…")
            return

        if result.model is not None or result.texture is not None:
            return
        if result.zone is not None:
            self._overview.show_visual(
                "Scene",
                "This zone contains placed scene entries. Use Scene Objects to inspect them.",
                f"{result.zone.entry_count:,} scene entries",
            )
            return
        if result.level is not None:
            self._overview.show_visual(
                "Level",
                "This level container exposes its scene information in Scene Objects.",
                getattr(result.level, 'description', ''),
            )
            return

        size = len(result.raw) if result.raw else (entry.size if entry else 0)
        self._overview.show_data(result.atype or "Unknown", path, size)
        self._top_splitter.setVisible(False)
        self._right_splitter.setSizes([0, 820])
        self._tab_panel.setCurrentWidget(self._overview)
        self._status_lbl.setText(
            f"{(result.atype or 'Data').title()} loaded — information only; no visual preview"
        )

    def _on_materials_ready(self, tex_data: dict):
        """Merge progressively decoded texture data for preview and export."""
        if not tex_data:
            return
        # Build mat_names from the current model asset (already parsed, no re-extraction needed)
        mat_names = {}
        try:
            model = getattr(self._viewport, '_current_model', None)
            if model and model.material_names:
                for mat_idx in tex_data:
                    if mat_idx < len(model.material_names):
                        raw = model.material_names[mat_idx]
                        # Use just the filename stem
                        mat_names[mat_idx] = raw.replace('\\', '/').split('/')[-1].replace('.material', '')
        except Exception:
            pass

        cached = getattr(self._props, '_cached_tex_data', {}) or {}
        for mat_idx, slots in tex_data.items():
            if isinstance(slots, dict) and isinstance(cached.get(mat_idx), dict):
                cached[mat_idx].update(slots)
            else:
                cached[mat_idx] = slots
        cached_names = getattr(self._props, '_mat_names', {}) or {}
        cached_names.update(mat_names)
        self._props._cached_tex_data = cached
        self._props._mat_names = cached_names

        textured_materials = sum(
            1 for slots in cached.values()
            if isinstance(slots, dict) and any(
                role == 'base_color' or role.startswith('base_color_')
                or role == 'color_id' or role.startswith('color_id_')
                for role in slots
            )
        )
        effect_materials = sum(
            1 for slots in cached.values()
            if isinstance(slots, dict) and any(
                _is_effect_role(role)
                for role in slots
            )
        )
        if effect_materials and not textured_materials:
            self._status_right.setText(
                f"Effects: {effect_materials} emissive material"
                f"{'s' if effect_materials != 1 else ''} ready"
            )
        elif textured_materials:
            self._status_right.setText(
                f"Textures: {textured_materials} material"
                f"{'s' if textured_materials != 1 else ''} ready"
            )

    def _on_materials_finished(self, tex_data: dict):
        """Make the final textured/untextured state explicit to the user."""
        base = getattr(self, '_model_status_base', "Model loaded")
        textured_materials = sum(
            1 for slots in (tex_data or {}).values()
            if isinstance(slots, dict) and any(
                role == 'base_color' or role.startswith('base_color_')
                or role == 'color_id' or role.startswith('color_id_')
                for role in slots
            )
        )
        effect_materials = sum(
            1 for slots in (tex_data or {}).values()
            if isinstance(slots, dict) and any(
                _is_effect_role(role)
                for role in slots
            )
        )
        if textured_materials:
            suffix = "material" if textured_materials == 1 else "materials"
            self._model_views.setTabText(1, "Textured 3D")
            self._model_views.setTabToolTip(
                1, f"Decoded game textures are active on {textured_materials} {suffix}."
            )
            self._status_lbl.setText(
                f"{base} · textures ready for {textured_materials} {suffix}"
            )
            self._status_right.setText(f"Textures: {textured_materials} {suffix}")
        elif effect_materials:
            suffix = "material" if effect_materials == 1 else "materials"
            self._model_views.setTabText(1, "Effects 3D")
            self._model_views.setTabToolTip(
                1, f"Animated emissive game effects are active on "
                f"{effect_materials} {suffix}."
            )
            self._status_lbl.setText(
                f"{base} · animated emissive effects ready for "
                f"{effect_materials} {suffix}"
            )
            self._status_right.setText(f"Effects: {effect_materials} {suffix}")
            self._model_views.setCurrentWidget(self._viewport)
        else:
            self._model_views.setTabText(1, "Material 3D")
            self._model_views.setTabToolTip(
                1, "This model uses shader values or procedural material data "
                "rather than a base-colour image texture."
            )
            self._status_lbl.setText(f"{base} · shader-based material; no base-colour image")
            self._status_right.setText("Material: shader-based")

    def _on_skel_ready(self, skel):
        self._skel_viewer.load_skeleton(skel)
        # Skeletons accompany many ordinary models; silently switching tabs
        # hid the actor explanation and made the preview appear unrelated.
        if self._current_actor is None:
            self._status_right.setText(
                f"{self._status_right.text()}  ·  Bones: {len(skel.bones)}"
            )

    def _on_level_ready(self, level_info, inst_table):
        self._tab_panel.setCurrentWidget(self._scene_panel)
        self._status_lbl.setText(
            f"Asset loaded — type: {level_info.asset_type}"
        )
        self._props.log(f"[INFO] {level_info.description}")

    def _on_zone_ready(self, zone):
        self._scene_panel.load_zone(zone)
        self._props.set_zone(zone)
        self._tab_panel.setCurrentWidget(self._scene_panel)
        kind = "art" if zone.is_art_zone else "gp"
        n_with_model = sum(1 for e in zone.entries if e.model_id)
        self._status_lbl.setText(
            f"Zone loaded — {zone.entry_count} scene node(s) ({kind})"
        )
        print(f"[zone] {zone.name}: {zone.entry_count} entries, "
              f"is_art={zone.is_art_zone}, "
              f"model_ids={len(zone.model_ids or [])}, "
              f"entries_with_model_id={n_with_model}")

    def _on_export_zone_requested(self, zone):
        """Export all resolved zone actors as a single GLB with world transforms."""
        from PyQt6.QtWidgets import QFileDialog, QProgressDialog
        from PyQt6.QtCore import Qt

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Zone as GLB",
            zone.name.split('/')[-1].replace('.zone', '') + "_assembled.glb",
            "GLB Files (*.glb)"
        )
        if not path:
            return

        # Progress dialog
        progress = QProgressDialog("Assembling zone...", "Cancel", 0, zone.entry_count, self)
        progress.setWindowTitle("Zone Export")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumWidth(360)
        progress.show()
        # Style the dialog's internal progress bar for readability
        from PyQt6.QtWidgets import QProgressBar as _QPB
        _bar = progress.findChild(_QPB)
        if _bar:
            _bar.setStyleSheet(
                "QProgressBar { height: 20px; color: #e0e4ef; text-align: center; "
                "font-size: 12px; background: #1e2028; border: 1px solid #2a2d36; "
                "border-radius: 3px; } "
                "QProgressBar::chunk { background: #3a6fbf; border-radius: 3px; }"
            )

        try:
            from core.level_assembler import LevelAssembler, export_zone_glb

            def on_progress(current, total):
                progress.setValue(current)
                progress.setLabelText(f"Resolving node {current}/{total}…")
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()

            assembler = LevelAssembler(self._toc_parser, self._browser._lookup)
            result    = assembler.assemble_zone(zone, progress_cb=on_progress)

            progress.setLabelText(f"Writing GLB…")
            QApplication.processEvents()

            n = export_zone_glb(result, path)
            progress.close()

            skipped = result.skip_count
            self._status_lbl.setText(
                f"Zone exported — {n} model(s) placed, {skipped} skipped"
            )
            print(f"[zone export] {n} nodes → {path}")
            if skipped:
                print(f"[zone export] {skipped} skipped:")
                for entry, reason in result.skipped:
                    id_str = f"{entry.asset_id:#018x}"
                    label  = entry.name or id_str
                    print(f"  [{entry.index}] {label} ({id_str}): {reason}")

        except Exception as ex:
            import traceback
            progress.close()
            self._status_lbl.setText(f"Zone export failed: {ex}")
            print(f"[zone export] error: {ex}\n{traceback.format_exc()}")

    def _on_raw_ready(self, data: bytes, label: str):
        self._hex_inspector.load_data(data, label)

    def _on_asset_error(self, msg: str):
        self._status_lbl.setText(f"Asset error: {msg}")
        self._props.log(f"[ERR] {msg}")
        self._overview.show_error(msg)
        self._tab_panel.setCurrentWidget(self._overview)

    def _on_instance_selected(self, entry):
        """Focus viewport camera on the selected scene node's world position."""
        try:
            import numpy as np
            pos = np.array([entry.x, entry.y, entry.z], dtype='float32')
            self._viewport.camera.target = pos
            self._viewport.camera.distance = 20.0
            self._viewport.update()
            self._status_lbl.setText(
                f"Scene node: {entry.name.split(chr(92))[-1] if entry.name else 'unnamed'} "
                f"— pos ({entry.x:.1f}, {entry.y:.1f}, {entry.z:.1f})"
            )
        except Exception:
            pass
        pos = inst.position
        self._viewport.camera.target = pos.astype('float32')
        self._viewport.update()
        self._status_lbl.setText(
            f"Instance {inst.instance_id:#010x} @ "
            f"({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"
        )

    def _toggle_wireframe(self, checked: bool):
        self._viewport.set_wireframe(checked)
        self._act_wire.setChecked(checked)

    def _frame_scene(self):
        if self._model_views.currentWidget() is self._software_preview:
            self._software_preview.reset_view()
        else:
            self._viewport.frame_model()

    def _open_controls_dialog(self):
        dlg = ControlsDialog(self)
        dlg.exec()
        # Always reload so both preview implementations pick up saved changes.
        self._viewport.reload_controls()
        self._software_preview.reload_controls()

    def _open_preferences(self):
        """Open the Preferences dialog (theme / colour customisation)."""
        def apply_fn(qss: str):
            self.setStyleSheet(qss)
        dlg = PreferencesDialog(apply_fn, self)
        if dlg.exec():
            self._save_config()

    def _save_config(self):
        """Persist current theme to config.json next to the executable."""
        import json, os
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            existing = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r') as f:
                    existing = json.load(f)
            existing["theme"] = theme_manager.to_dict()
            with open(cfg_path, 'w') as f:
                json.dump(existing, f, indent=2)
        except Exception as ex:
            print(f"[config] failed to save: {ex}")

    def _load_config(self):
        """Load theme (and other settings) from config.json."""
        import json, os
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r') as f:
                    cfg = json.load(f)
                if "theme" in cfg:
                    theme_manager.from_dict(cfg["theme"])
        except Exception as ex:
            print(f"[config] failed to load: {ex}")
        # The built-in theme is the default even when no config file exists.
        # Previously a fresh install never applied any stylesheet at all.
        self.setStyleSheet(theme_manager.stylesheet())

    def _show_about(self):
        QMessageBox.about(self, "About RCRA Forge",
            "<h3>RCRA Forge v0.5.7.1</h3>"
            "<p>Ratchet &amp; Clank: Rift Apart level editor and model exporter.</p>"
            "<p>Format reverse engineering credit:<br>"
            "&nbsp;• chaoticgd / <i>ripped_apart</i> (MIT)<br>"
            "&nbsp;• thtrandomlurker (mesh format)<br>"
            "&nbsp;• doesthisusername (lump names)</p>"
            "<p>Built with Python, PyQt6, PyOpenGL, NumPy.</p>")
