"""
ui/texture_viewer.py
Texture preview panel for RCRA Forge.

Displays a decoded texture preview alongside format metadata.
Falls back to a checkerboard pattern if BCn decode isn't available.
"""

import struct
import math
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy, QPushButton, QFileDialog, QSlider
)
from PyQt6.QtCore import Qt, QSize, QRect, QPoint
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QBrush, QPen, QFont
)

from core.texture import TextureAsset, DXGI_FORMAT_NAMES


class TextureCanvas(QWidget):
    """Widget that renders a QImage with checkerboard background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap:   QPixmap = None
        self._zoom:     float   = 1.0
        self.setMinimumSize(64, 64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_pixmap(self, pm: QPixmap):
        self._pixmap = pm
        self._fit_zoom()
        self.update()

    def set_zoom(self, factor: float):
        self._zoom = max(0.05, min(16.0, factor))
        self.update()

    def _fit_zoom(self):
        if self._pixmap and self.width() > 0 and self.height() > 0:
            zx = self.width()  / self._pixmap.width()
            zy = self.height() / self._pixmap.height()
            self._zoom = min(zx, zy, 1.0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_zoom()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Checkerboard background
        tile = 12
        cols = math.ceil(self.width()  / tile) + 1
        rows = math.ceil(self.height() / tile) + 1
        c1 = QColor(80, 80, 80)
        c2 = QColor(55, 55, 55)
        for row in range(rows):
            for col in range(cols):
                p.fillRect(col*tile, row*tile, tile, tile,
                           c1 if (row+col) % 2 == 0 else c2)

        if self._pixmap:
            w = int(self._pixmap.width()  * self._zoom)
            h = int(self._pixmap.height() * self._zoom)
            x = (self.width()  - w) // 2
            y = (self.height() - h) // 2
            p.drawPixmap(QRect(x, y, w, h), self._pixmap)

        p.end()


class TextureViewer(QWidget):
    """Full texture viewer with metadata strip and export button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._texture: TextureAsset = None
        self._build_ui()
        # Minimum: header(36) + canvas_min(200) + zoom_row(28) + info_strip(48)
        self.setMinimumHeight(312)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_texture(self, tex: TextureAsset):
        self._texture = tex
        self._update_info(tex)
        pm = self._decode_to_pixmap(tex)
        self._canvas.set_pixmap(pm)
        self._btn_export.setEnabled(True)

    def clear(self):
        self._texture = None
        self._canvas.set_pixmap(None)
        self._btn_export.setEnabled(False)
        for lbl in (self._lbl_size, self._lbl_fmt, self._lbl_mips, self._lbl_bytes):
            lbl.setText("—")

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
        lbl = QLabel("TEXTURE VIEWER")
        lbl.setObjectName("PanelTitle")
        hl.addWidget(lbl)
        layout.addWidget(hdr)

        # Canvas
        self._canvas = TextureCanvas()
        self._canvas.setMinimumHeight(80)
        layout.addWidget(self._canvas, 1)

        # Zoom slider
        zoom_row = QFrame()
        zoom_row.setObjectName("ZoomRow")
        zoom_row.setFixedHeight(28)
        zl = QHBoxLayout(zoom_row)
        zl.setContentsMargins(8, 2, 8, 2)
        zl.addWidget(QLabel("Zoom:"))
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(5, 800)
        self._zoom_slider.setValue(100)
        self._zoom_slider.setTickInterval(100)
        self._zoom_slider.valueChanged.connect(
            lambda v: self._canvas.set_zoom(v / 100.0)
        )
        zl.addWidget(self._zoom_slider)
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setFixedWidth(36)
        self._zoom_slider.valueChanged.connect(
            lambda v: self._zoom_lbl.setText(f"{v}%")
        )
        zl.addWidget(self._zoom_lbl)
        layout.addWidget(zoom_row)

        # Info strip
        info = QFrame()
        info.setObjectName("TexInfo")
        info.setFixedHeight(48)
        il = QHBoxLayout(info)
        il.setContentsMargins(12, 4, 12, 4)
        il.setSpacing(20)

        self._lbl_size  = self._info_pair(il, "Size")
        self._lbl_fmt   = self._info_pair(il, "Format")
        self._lbl_mips  = self._info_pair(il, "Mips")
        self._lbl_bytes = self._info_pair(il, "Raw Size")
        il.addStretch()

        self._btn_export = QPushButton("Save texture as DDS…")
        self._btn_export.setObjectName("ExportBtn")
        self._btn_export.setFixedHeight(32)
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_dds)
        il.addWidget(self._btn_export)

        layout.addWidget(info)

    def _info_pair(self, parent_layout, key: str) -> QLabel:
        col = QVBoxLayout()
        col.setSpacing(1)
        k = QLabel(key.upper())
        k.setObjectName("TexInfoKey")
        v = QLabel("—")
        v.setObjectName("TexInfoVal")
        col.addWidget(k)
        col.addWidget(v)
        parent_layout.addLayout(col)
        return v

    # ── Decode ────────────────────────────────────────────────────────────────

    def _decode_to_pixmap(self, tex: TextureAsset) -> QPixmap:
        # Try Pillow decode via DDS wrapping
        png_bytes = tex.to_png_bytes()
        if png_bytes:
            img = QImage.fromData(png_bytes)
            if not img.isNull():
                return QPixmap.fromImage(img)

        # Fallback: solid colour swatch with format text
        pm = QPixmap(tex.width or 64, tex.height or 64)
        pm.fill(QColor(40, 60, 90))
        p = QPainter(pm)
        p.setPen(QColor(180, 210, 255))
        p.setFont(QFont("Consolas", 10))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter,
                   f"{tex.format_name}\n{tex.width}×{tex.height}\n(No BCn decode)")
        p.end()
        return pm

    def _update_info(self, tex: TextureAsset):
        self._lbl_size.setText(f"{tex.width} × {tex.height}")
        self._lbl_fmt.setText(tex.format_name)
        self._lbl_mips.setText(str(tex.mips))
        active_data = tex.hd_pixel_data if tex.hd_pixel_data else tex.pixel_data
        self._lbl_bytes.setText(f"{len(active_data):,} B")

    def _export_dds(self):
        if not self._texture:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save DDS Texture", "texture.dds",
            "DDS Files (*.dds);;All Files (*.*)"
        )
        if path:
            with open(path, 'wb') as f:
                f.write(self._texture.to_dds_bytes())
