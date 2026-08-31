"""
ui/skeleton_viewer.py
Skeleton inspector panel for RCRA Forge.

Left: bone hierarchy tree.
Right: 2D front/side projection of the rest-pose skeleton.
"""

import math
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
)

from core.skeleton import Skeleton, Bone


# ── 2D Skeleton Canvas ────────────────────────────────────────────────────────

class SkeletonCanvas(QWidget):
    """Draws a stick-figure bone diagram projected onto XY / XZ planes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._skel:     Skeleton = None
        self._world_pos: dict[int, np.ndarray] = {}
        self._selected:  int = -1
        self.setMinimumSize(180, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def load_skeleton(self, skel: Skeleton):
        self._skel      = skel
        self._world_pos = skel.world_positions()
        self._selected  = -1
        self.update()

    def select_bone(self, idx: int):
        self._selected = idx
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, e):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.fillRect(self.rect(), QColor("#13151a"))

            if not self._skel or not self._world_pos:
                p.setPen(QColor("#405060"))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No skeleton loaded")
                p.end()
                return

            positions = self._world_pos
            if not positions:
                p.end()
                return

            pts3d = np.array(list(positions.values()))
            self._draw_projection(p, positions, proj='xy')
            p.end()
        except Exception:
            pass

    def _draw_projection(self, p: QPainter, world_pos: dict, proj: str = 'xy'):
        pts = {idx: self._project(v, proj) for idx, v in world_pos.items()}

        # Fit to canvas
        if not pts:
            return
        xs = [v[0] for v in pts.values()]
        ys = [v[1] for v in pts.values()]
        mn_x, mx_x = min(xs), max(xs)
        mn_y, mx_y = min(ys), max(ys)
        rng_x = mx_x - mn_x or 1
        rng_y = mx_y - mn_y or 1

        pad = 28
        W, H = self.width() - pad*2, self.height() - pad*2

        def to_screen(v):
            sx = pad + (v[0] - mn_x) / rng_x * W
            sy = pad + (1.0 - (v[1] - mn_y) / rng_y) * H
            return QPoint(int(sx), int(sy))

        # Draw bone sticks
        pen_bone = QPen(QColor("#2a4a6a"), 1.5)
        pen_sel  = QPen(QColor("#5dade2"), 2.5)
        p.setFont(QFont("Consolas", 7))

        for bone in self._skel.bones:
            if bone.parent == -1 or bone.parent not in pts:
                continue
            a = to_screen(pts[bone.parent])
            b = to_screen(pts[bone.index])
            p.setPen(pen_sel if bone.index == self._selected else pen_bone)
            p.drawLine(a, b)

        # Draw joints
        for idx, v in pts.items():
            sp = to_screen(v)
            is_sel = idx == self._selected
            r = 4 if is_sel else 3
            p.setBrush(QBrush(QColor("#5dade2") if is_sel else QColor("#1a3a5a")))
            p.setPen(QPen(QColor("#4090c0") if is_sel else QColor("#2a5a8a"), 1))
            p.drawEllipse(sp.x() - r, sp.y() - r, r*2, r*2)

    @staticmethod
    def _project(v: np.ndarray, proj: str) -> tuple[float, float]:
        if proj == 'xy':
            return float(v[0]), float(v[1])
        elif proj == 'xz':
            return float(v[0]), float(v[2])
        return float(v[0]), float(v[1])


# ── Skeleton Viewer Panel ─────────────────────────────────────────────────────

class SkeletonViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._skel: Skeleton = None
        self._build_ui()

    def load_skeleton(self, skel: Skeleton):
        self._skel = skel
        self._canvas.load_skeleton(skel)
        self._build_tree(skel)
        self._status.setText(f"{len(skel.bones)} bones")

    def clear(self):
        self._skel = None
        self._canvas.load_skeleton(None)
        self._tree.clear()
        self._status.setText("No skeleton loaded")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QFrame()
        hdr.setObjectName("BrowserHeader")
        hdr.setFixedHeight(36)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 4, 8, 4)
        title = QLabel("SKELETON")
        title.setObjectName("PanelTitle")
        hl.addWidget(title)
        layout.addWidget(hdr)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # Bone tree
        self._tree = QTreeWidget()
        self._tree.setObjectName("AssetTree")
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(12)
        self._tree.setMinimumWidth(160)
        self._tree.itemClicked.connect(self._on_bone_clicked)
        splitter.addWidget(self._tree)

        # Canvas
        self._canvas = SkeletonCanvas()
        splitter.addWidget(self._canvas)
        splitter.setSizes([200, 300])

        self._status = QLabel("No skeleton loaded")
        self._status.setObjectName("StatusLabel")
        self._status.setContentsMargins(8, 3, 8, 3)
        self._status.setFixedHeight(26)
        layout.addWidget(self._status)

    def _build_tree(self, skel: Skeleton):
        self._tree.clear()
        items: dict[int, QTreeWidgetItem] = {}

        def add_bone(bone: Bone, parent_item):
            item = QTreeWidgetItem(parent_item)
            item.setText(0, f"🦴 {bone.name}")
            item.setData(0, Qt.ItemDataRole.UserRole, bone.index)
            item.setForeground(0, QColor("#80b0d0"))
            f = item.font(0)
            f.setFamily("Consolas")
            f.setPointSize(9)
            item.setFont(0, f)
            items[bone.index] = item
            for child in skel.children_of(bone):
                add_bone(child, item)
            item.setExpanded(True)
            return item

        for root_bone in skel.root_bones():
            add_bone(root_bone, self._tree.invisibleRootItem())

    def _on_bone_clicked(self, item: QTreeWidgetItem, col: int):
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is not None:
            self._canvas.select_bone(idx)
