"""
ui/controls_dialog.py
Viewport Controls customisation dialog for RCRA Forge.

Maya-style motion with direct mouse bindings:
  LMB drag          → Tumble around the model pivot
  MMB drag          → Track in the camera view plane
  RMB drag          → Dolly horizontally
  Scroll wheel      → Dolly
  F / A             → Frame model

User-configurable:
  - Invert orbit X / Y axes
  - Invert scroll-wheel zoom direction
  - Zoom speed multiplier

Settings are persisted via QSettings (no external file needed).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QCheckBox, QDoubleSpinBox,
    QPushButton, QDialogButtonBox, QFrame, QLabel,
)
from PyQt6.QtCore import Qt, QSettings

from ui.camera_controls import AUTODESK_MOUSE_BINDINGS


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULTS: dict = {
    "invert_orbit_x": False,
    "invert_orbit_y": False,
    "invert_zoom":    False,
    "zoom_speed":     1.0,
}

_ORG = "RCRAForge"
_APP = "RCRAForge"
_GRP = "viewport_controls"


def load_controls() -> dict:
    """Return current control settings, falling back to DEFAULTS."""
    s = QSettings(_ORG, _APP)
    s.beginGroup(_GRP)
    cfg = {}
    for k, default in DEFAULTS.items():
        raw = s.value(k, default)
        if isinstance(default, bool):
            raw = raw.lower() == "true" if isinstance(raw, str) else bool(raw)
        elif isinstance(default, float):
            raw = float(raw)
        cfg[k] = raw
    s.endGroup()
    return cfg


def save_controls(cfg: dict):
    """Persist control settings."""
    s = QSettings(_ORG, _APP)
    s.beginGroup(_GRP)
    for k, v in cfg.items():
        s.setValue(k, v)
    s.endGroup()


# ── Dialog ────────────────────────────────────────────────────────────────────

class ControlsDialog(QDialog):
    """Modal dialog for editing viewport control preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Viewport Controls")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._cfg = load_controls()
        self._build_ui()
        self._populate()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Bindings reference (read-only) ────────────────────────────────────
        ref_grp = QGroupBox("Maya-style Camera Motion")
        ref_grp.setStyleSheet("QGroupBox { font-weight: 600; }")
        rf = QFormLayout(ref_grp)
        rf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        rf.setSpacing(6)
        bindings = list(AUTODESK_MOUSE_BINDINGS) + [
            ("Scroll wheel", "Dolly"),
            ("F / A", "Frame model"),
        ]
        for key, action in bindings:
            key_lbl = QLabel(key)
            key_lbl.setStyleSheet("color: #8090a0; font-size: 12px;")
            act_lbl = QLabel(action)
            act_lbl.setStyleSheet("font-size: 12px;")
            rf.addRow(key_lbl, act_lbl)
        root.addWidget(ref_grp)

        # ── Axis inversion ────────────────────────────────────────────────────
        invert_grp = QGroupBox("Invert Axes")
        invert_grp.setStyleSheet("QGroupBox { font-weight: 600; }")
        ivf = QFormLayout(invert_grp)
        ivf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        ivf.setSpacing(8)

        self._inv_orbit_x = QCheckBox("Invert horizontal orbit (yaw)")
        self._inv_orbit_y = QCheckBox("Invert vertical orbit (pitch)")
        self._inv_zoom    = QCheckBox("Invert scroll-wheel zoom direction")

        ivf.addRow(self._inv_orbit_x)
        ivf.addRow(self._inv_orbit_y)
        ivf.addRow(self._inv_zoom)
        root.addWidget(invert_grp)

        # ── Zoom speed ────────────────────────────────────────────────────────
        zoom_grp = QGroupBox("Zoom Speed")
        zoom_grp.setStyleSheet("QGroupBox { font-weight: 600; }")
        zf = QFormLayout(zoom_grp)
        zf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        zf.setSpacing(8)

        self._zoom_speed = QDoubleSpinBox()
        self._zoom_speed.setRange(0.1, 5.0)
        self._zoom_speed.setSingleStep(0.1)
        self._zoom_speed.setDecimals(1)
        self._zoom_speed.setSuffix("x")
        zf.addRow("Speed multiplier:", self._zoom_speed)
        root.addWidget(zoom_grp)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2a2d36;")
        root.addWidget(sep)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(self._reset_btn)
        btn_row.addStretch()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._accept)
        bbox.rejected.connect(self.reject)
        btn_row.addWidget(bbox)
        root.addLayout(btn_row)

    def _populate(self):
        c = self._cfg
        self._inv_orbit_x.setChecked(bool(c["invert_orbit_x"]))
        self._inv_orbit_y.setChecked(bool(c["invert_orbit_y"]))
        self._inv_zoom.setChecked(bool(c["invert_zoom"]))
        self._zoom_speed.setValue(float(c["zoom_speed"]))

    def _collect(self) -> dict:
        return {
            "invert_orbit_x": self._inv_orbit_x.isChecked(),
            "invert_orbit_y": self._inv_orbit_y.isChecked(),
            "invert_zoom":    self._inv_zoom.isChecked(),
            "zoom_speed":     self._zoom_speed.value(),
        }

    def _reset(self):
        self._cfg = dict(DEFAULTS)
        self._populate()

    def _accept(self):
        save_controls(self._collect())
        self.accept()

    def result_config(self) -> dict:
        return load_controls()
