"""
ui/preferences_dialog.py
Preferences dialog for RCRA Forge — Theme / colour customisation.

Opens via Edit → Preferences (or Ctrl+,).
Applies theme changes live to the main window while the dialog is open.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QScrollArea, QWidget, QFrame, QGridLayout,
    QColorDialog, QSizePolicy, QDialogButtonBox, QToolButton,
    QGroupBox, QInputDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from core.theme import theme_manager, SLOTS, PRESETS, BUILTIN_PRESETS


class ColourSwatch(QFrame):
    """Clickable colour swatch — shows current colour, opens picker on click."""

    colour_changed = pyqtSignal(str, str)  # slot_key, new_hex

    def __init__(self, slot_key: str, hex_colour: str, parent=None):
        super().__init__(parent)
        self._slot  = slot_key
        self._hex   = hex_colour
        self._is_overridden = False

        self.setFixedSize(28, 20)
        self.setFrameShape(QFrame.Shape.Box)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Click to change colour\nCurrent: {hex_colour}")
        self._update_bg()

    def set_colour(self, hex_colour: str, is_overridden: bool = False):
        self._hex = hex_colour
        self._is_overridden = is_overridden
        self._update_bg()
        self.setToolTip(f"Click to change\nCurrent: {hex_colour}"
                        + (" (customised)" if is_overridden else ""))

    def _update_bg(self):
        border = "#5ba3f5" if self._is_overridden else "#3a3d4a"
        self.setStyleSheet(
            f"background: {self._hex}; border: 1px solid {border}; border-radius: 2px;"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            initial = QColor(self._hex)
            colour  = QColorDialog.getColor(initial, self, f"Choose colour — {SLOTS.get(self._slot, self._slot)}")
            if colour.isValid():
                self._hex = colour.name()
                self._is_overridden = True
                self._update_bg()
                self.colour_changed.emit(self._slot, self._hex)


class PreferencesDialog(QDialog):
    """Main preferences dialog with tabbed sections and live preview."""

    theme_applied = pyqtSignal()   # emitted whenever stylesheet is updated

    def __init__(self, apply_fn, parent=None):
        """
        apply_fn: callable(stylesheet: str) — called to live-apply theme.
        """
        super().__init__(parent)
        self._apply_fn   = apply_fn
        self._swatches   = {}   # slot_key → ColourSwatch
        self._orig_state = theme_manager.to_dict()   # for Cancel rollback

        self.setWindowTitle("Preferences")
        self.setMinimumSize(560, 600)
        self.resize(600, 700)
        self._build_ui()
        self._populate()
        self._rebuild_preset_combo(theme_manager.current_preset())

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("BrowserHeader")
        hdr.setFixedHeight(40)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        title = QLabel("PREFERENCES")
        title.setObjectName("PanelTitle")
        hl.addWidget(title)
        root.addWidget(hdr)

        # ── Preset row ────────────────────────────────────────────────────────
        preset_bar = QFrame()
        preset_bar.setObjectName("FilterBar")
        preset_bar.setFixedHeight(52)
        pb = QHBoxLayout(preset_bar)
        pb.setContentsMargins(12, 8, 12, 8)
        pb.setSpacing(6)

        pb.addWidget(QLabel("Preset:"))
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(theme_manager.preset_names())
        self._preset_combo.setCurrentText(theme_manager.current_preset())
        self._preset_combo.setFixedWidth(160)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        pb.addWidget(self._preset_combo)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        pb.addWidget(sep)

        reset_btn = QPushButton("↺  Reset")
        reset_btn.setToolTip("Reset all per-slot customisations to the preset defaults")
        reset_btn.setFixedWidth(80)
        reset_btn.clicked.connect(self._reset_overrides)
        pb.addWidget(reset_btn)

        save_btn = QPushButton("⬆  Save as…")
        save_btn.setToolTip("Save current colours as a new named preset")
        save_btn.setFixedWidth(95)
        save_btn.clicked.connect(self._save_as_preset)
        pb.addWidget(save_btn)

        self._delete_btn = QPushButton("🗑  Delete")
        self._delete_btn.setToolTip("Delete the selected user preset")
        self._delete_btn.setFixedWidth(80)
        self._delete_btn.clicked.connect(self._delete_preset)
        pb.addWidget(self._delete_btn)
        pb.addStretch()
        root.addWidget(preset_bar)

        # ── Colour slot grid (scrollable) ─────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        grid  = QGridLayout(inner)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setSpacing(0)
        grid.setVerticalSpacing(2)

        # Group slots into categories
        categories = [
            ("Backgrounds", [
                "BG_BASE", "BG_PANEL", "BG_DEEP", "BG_SURFACE",
                "BG_ALT", "BG_HOVER", "BG_SELECT", "BG_SELECT_DEEP",
            ]),
            ("Borders", [
                "BORDER", "BORDER_FOCUS", "BORDER_STRONG",
            ]),
            ("Text", [
                "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_DIM",
                "TEXT_MUTED", "TEXT_SELECT", "TEXT_MONO",
            ]),
            ("Accent", [
                "ACCENT", "ACCENT_HOVER", "ACCENT_PRESS",
                "ACCENT_LIGHT", "ACCENT_BRIGHT",
            ]),
            ("Warning / Groups", [
                "WARN", "WARN_HOVER", "WARN_BG",
            ]),
            ("Scrollbars", [
                "SCROLLBAR", "SCROLLBAR_HOVER",
            ]),
            ("Export Button", [
                "EXPORT_BG", "EXPORT_BORDER", "EXPORT_TEXT",
            ]),
        ]

        row = 0
        for cat_name, keys in categories:
            # Category header
            cat_lbl = QLabel(cat_name.upper())
            cat_lbl.setObjectName("SubPanelLabel")
            cat_lbl.setContentsMargins(0, 10, 0, 4)
            f = QFont()
            f.setPointSize(9)
            f.setWeight(QFont.Weight.Bold)
            cat_lbl.setFont(f)
            grid.addWidget(cat_lbl, row, 0, 1, 4)
            row += 1

            for slot in keys:
                label = QLabel(SLOTS.get(slot, slot))
                label.setContentsMargins(4, 2, 12, 2)

                swatch = ColourSwatch(slot, "#888888")
                swatch.colour_changed.connect(self._on_colour_changed)
                self._swatches[slot] = swatch

                hex_lbl = QLabel()
                hex_lbl.setObjectName("FieldValue")
                hex_lbl.setFixedWidth(72)
                setattr(swatch, '_hex_label', hex_lbl)

                reset_btn = QToolButton()
                reset_btn.setText("↺")
                reset_btn.setFixedSize(20, 20)
                reset_btn.setToolTip("Reset to preset default")
                reset_btn.clicked.connect(lambda _, s=slot: self._reset_slot(s))

                grid.addWidget(label,     row, 0)
                grid.addWidget(swatch,    row, 1, Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(hex_lbl,   row, 2)
                grid.addWidget(reset_btn, row, 3, Qt.AlignmentFlag.AlignVCenter)
                row += 1

        grid.setColumnStretch(0, 1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # ── Button bar ────────────────────────────────────────────────────────
        btn_bar = QFrame()
        btn_bar.setObjectName("BrowserHeader")
        bb = QHBoxLayout(btn_bar)
        bb.setContentsMargins(12, 8, 12, 8)
        bb.setSpacing(8)
        bb.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(90)
        cancel_btn.clicked.connect(self._on_cancel)
        bb.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(90)
        ok_btn.setObjectName("ExportBtn")
        ok_btn.clicked.connect(self.accept)
        bb.addWidget(ok_btn)

        root.addWidget(btn_bar)

    # ── Populate swatches from current theme ──────────────────────────────────

    def _populate(self):
        resolved  = theme_manager.resolved()
        preset    = PRESETS.get(theme_manager.current_preset(), {})
        overrides = theme_manager.to_dict().get("overrides", {})

        for slot, swatch in self._swatches.items():
            hex_val      = resolved.get(slot, "#888888")
            is_overridden = slot in overrides
            swatch.set_colour(hex_val, is_overridden)
            swatch._hex_label.setText(hex_val)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_preset_changed(self, name: str):
        theme_manager.set_preset(name, clear_overrides=False)
        self._populate()
        self._live_apply()
        self._delete_btn.setEnabled(name not in BUILTIN_PRESETS)

    def _on_colour_changed(self, slot: str, hex_colour: str):
        theme_manager.set_slot(slot, hex_colour)
        swatch = self._swatches.get(slot)
        if swatch:
            swatch._hex_label.setText(hex_colour)
        self._live_apply()

    def _reset_slot(self, slot: str):
        theme_manager.reset_slot(slot)
        resolved = theme_manager.resolved()
        swatch   = self._swatches.get(slot)
        if swatch:
            hex_val = resolved.get(slot, "#888888")
            swatch.set_colour(hex_val, is_overridden=False)
            swatch._hex_label.setText(hex_val)
        self._live_apply()

    def _reset_overrides(self):
        theme_manager.reset_all_overrides()
        self._populate()
        self._live_apply()

    def _live_apply(self):
        self._apply_fn(theme_manager.stylesheet())
        self.theme_applied.emit()

    def _save_as_preset(self):
        """Save current resolved colours as a new named preset."""
        name, ok = QInputDialog.getText(
            self, "Save Preset", "Preset name:",
            text=f"Custom {len(theme_manager.preset_names()) + 1}"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in BUILTIN_PRESETS:
            QMessageBox.warning(self, "Save Preset",
                f"Cannot overwrite built-in preset '{name}'.")
            return
        # Save resolved colours as a new user preset
        theme_manager.save_user_preset(name, theme_manager.resolved())
        # Rebuild combo
        self._rebuild_preset_combo(name)
        self._live_apply()

    def _delete_preset(self):
        """Delete the currently selected user preset."""
        name = self._preset_combo.currentText()
        if name in BUILTIN_PRESETS:
            QMessageBox.warning(self, "Delete Preset",
                f"Cannot delete built-in preset '{name}'.")
            return
        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        theme_manager.delete_user_preset(name)
        fallback = list(theme_manager.preset_names())[0]
        theme_manager.set_preset(fallback, clear_overrides=True)
        self._rebuild_preset_combo(fallback)
        self._populate()
        self._live_apply()

    def _rebuild_preset_combo(self, select_name: str = None):
        """Rebuild the preset combo from current theme_manager presets."""
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItems(theme_manager.preset_names())
        if select_name and select_name in theme_manager.preset_names():
            self._preset_combo.setCurrentText(select_name)
        self._preset_combo.blockSignals(False)
        # Enable delete only for user presets
        current = self._preset_combo.currentText()
        self._delete_btn.setEnabled(current not in BUILTIN_PRESETS)

    def _on_cancel(self):
        theme_manager.from_dict(self._orig_state)
        self._live_apply()
        self.reject()
