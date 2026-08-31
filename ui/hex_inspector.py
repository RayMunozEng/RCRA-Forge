"""
ui/hex_inspector.py
Raw hex dump viewer for RCRA Forge.

Lets developers inspect raw WAD lump data — essential for format
reverse-engineering. Displays classic 16-bytes-per-row hex + ASCII view.
Supports jump-to-offset and range highlighting.
"""

import math
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollBar, QLineEdit, QPushButton, QSizePolicy, QFileDialog
)
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QPen,
    QTextCharFormat, QKeyEvent
)


BYTES_PER_ROW  = 16
HEADER_HEIGHT  = 24
ROW_HEIGHT     = 17
ADDR_WIDTH     = 72    # pixels for the address column
HEX_COL_WIDTH  = 26    # pixels per byte in hex area
ASCII_COL_W    = 10    # pixels per byte in ASCII area
HEX_GAP        = 12    # gap between hex and ASCII
GROUP_GAP       = 6    # extra gap every 8 bytes


class HexView(QWidget):
    """Core hex render widget — paints raw bytes in hex + ASCII grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data:          bytes = b''
        self._scroll_offset: int   = 0   # first visible row index
        self._hover_byte:    int   = -1
        self._highlight_start: int = -1
        self._highlight_end:   int = -1

        self._font = QFont("Consolas", 10)
        if not QFontMetrics(self._font).averageCharWidth():
            self._font = QFont("Courier New", 10)
        self._fm   = QFontMetrics(self._font)

        self.setMouseTracking(True)
        self.setMinimumWidth(600)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ── Public ────────────────────────────────────────────────────────────────

    def set_data(self, data: bytes):
        self._data          = data
        self._scroll_offset = 0
        self._hover_byte    = -1
        self.update()

    def scroll_to_offset(self, byte_offset: int):
        row = byte_offset // BYTES_PER_ROW
        self._scroll_offset = max(0, min(row, self._total_rows() - self._visible_rows()))
        self.update()

    def set_highlight(self, start: int, end: int):
        self._highlight_start = start
        self._highlight_end   = end
        self.update()

    def visible_rows(self) -> int:
        return max(1, (self.height() - HEADER_HEIGHT) // ROW_HEIGHT)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self._font)
        p.fillRect(self.rect(), QColor("#13151a"))

        if not self._data:
            p.setPen(QColor("#405060"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data loaded")
            p.end()
            return

        self._draw_header(p)
        self._draw_rows(p)
        p.end()

    def _draw_header(self, p: QPainter):
        p.fillRect(0, 0, self.width(), HEADER_HEIGHT, QColor("#0d0f14"))
        p.setPen(QColor("#304050"))
        p.drawLine(0, HEADER_HEIGHT - 1, self.width(), HEADER_HEIGHT - 1)

        p.setPen(QColor("#506070"))
        p.setFont(self._font)

        p.drawText(QRect(8, 0, ADDR_WIDTH - 8, HEADER_HEIGHT),
                   Qt.AlignmentFlag.AlignVCenter, "Offset")
        for i in range(BYTES_PER_ROW):
            x = self._hex_x(i)
            p.drawText(QRect(x, 0, HEX_COL_WIDTH, HEADER_HEIGHT),
                       Qt.AlignmentFlag.AlignCenter, f"{i:02X}")
        p.drawText(QRect(self._ascii_x(0), 0, BYTES_PER_ROW * ASCII_COL_W, HEADER_HEIGHT),
                   Qt.AlignmentFlag.AlignVCenter, "  ASCII")

    def _draw_rows(self, p: QPainter):
        rows = self.visible_rows()
        data = self._data
        n    = len(data)

        for r in range(rows):
            row_idx = self._scroll_offset + r
            offset  = row_idx * BYTES_PER_ROW
            if offset >= n:
                break

            y = HEADER_HEIGHT + r * ROW_HEIGHT

            # Alternating row background
            if r % 2 == 0:
                p.fillRect(0, y, self.width(), ROW_HEIGHT, QColor("#161820"))

            # Address
            p.setPen(QColor("#4a6070"))
            p.drawText(QRect(8, y, ADDR_WIDTH - 8, ROW_HEIGHT),
                       Qt.AlignmentFlag.AlignVCenter,
                       f"{offset:08X}")

            # Hex bytes
            row_end = min(offset + BYTES_PER_ROW, n)
            for bi in range(row_end - offset):
                byte_idx = offset + bi
                byte_val = data[byte_idx]

                is_hover  = byte_idx == self._hover_byte
                is_hl     = (self._highlight_start <= byte_idx < self._highlight_end)

                bx = self._hex_x(bi)

                if is_hl:
                    p.fillRect(bx - 2, y + 1, HEX_COL_WIDTH + 2, ROW_HEIGHT - 2,
                               QColor("#1a3a6a"))
                if is_hover:
                    p.fillRect(bx - 2, y + 1, HEX_COL_WIDTH + 2, ROW_HEIGHT - 2,
                               QColor("#2a3a5a"))

                # Colour-code: null=dark, printable=bright, other=mid
                if byte_val == 0:
                    p.setPen(QColor("#303840"))
                elif 0x20 <= byte_val < 0x7F:
                    p.setPen(QColor("#80d0a0"))
                else:
                    p.setPen(QColor("#5090c0"))

                p.drawText(QRect(bx, y, HEX_COL_WIDTH, ROW_HEIGHT),
                           Qt.AlignmentFlag.AlignCenter,
                           f"{byte_val:02X}")

                # ASCII column
                ax = self._ascii_x(bi)
                ch = chr(byte_val) if 0x20 <= byte_val < 0x7F else "·"
                p.setPen(QColor("#70a080") if ch != "·" else QColor("#303840"))
                p.drawText(QRect(ax, y, ASCII_COL_W, ROW_HEIGHT),
                           Qt.AlignmentFlag.AlignCenter, ch)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, e):
        byte = self._byte_at(e.pos().x(), e.pos().y())
        if byte != self._hover_byte:
            self._hover_byte = byte
            self.update()

    def leaveEvent(self, e):
        self._hover_byte = -1
        self.update()

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _hex_x(self, col: int) -> int:
        gap = GROUP_GAP if col >= 8 else 0
        return ADDR_WIDTH + col * HEX_COL_WIDTH + gap

    def _ascii_x(self, col: int) -> int:
        return ADDR_WIDTH + BYTES_PER_ROW * HEX_COL_WIDTH + GROUP_GAP + HEX_GAP + col * ASCII_COL_W

    def _byte_at(self, px: int, py: int) -> int:
        if py < HEADER_HEIGHT:
            return -1
        row = self._scroll_offset + (py - HEADER_HEIGHT) // ROW_HEIGHT
        for col in range(BYTES_PER_ROW):
            x = self._hex_x(col)
            if x <= px < x + HEX_COL_WIDTH:
                idx = row * BYTES_PER_ROW + col
                return idx if 0 <= idx < len(self._data) else -1
        return -1

    def _total_rows(self) -> int:
        return math.ceil(len(self._data) / BYTES_PER_ROW)

    def _visible_rows(self) -> int:
        return max(1, (self.height() - HEADER_HEIGHT) // ROW_HEIGHT)

    def sizeHint(self) -> QSize:
        w = ADDR_WIDTH + BYTES_PER_ROW * HEX_COL_WIDTH + GROUP_GAP + HEX_GAP + \
            BYTES_PER_ROW * ASCII_COL_W + 20
        return QSize(w, 400)


class HexInspector(QWidget):
    """Full hex inspector panel with scroll, jump-to-offset, and size display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data:  bytes = b''
        self._label: str   = ''
        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def load_data(self, data: bytes, label: str = ""):
        self._data  = data
        self._label = label
        self._hex_view.set_data(data)
        self._scrollbar.setMaximum(max(0, math.ceil(len(data) / BYTES_PER_ROW) - 1))
        self._scrollbar.setValue(0)
        rows = math.ceil(len(data) / BYTES_PER_ROW)
        self._size_lbl.setText(
            f"{len(data):,} bytes  ·  {rows:,} rows"
            + (f"  ·  {label}" if label else "")
        )
        self._btn_export.setEnabled(True)

    def _do_export(self):
        if not self._data:
            return
        # Suggest a filename based on the label (strip path separators)
        safe = self._label.replace('/', '_').replace('\\', '_') or "hex_dump"
        default = f"{safe}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Hex Dump", default, "Text Files (*.txt);;All Files (*.*)"
        )
        if not path:
            return
        # Build classic hex dump text
        lines = []
        data = self._data
        n    = len(data)
        lines.append(f"# RCRA Forge Hex Dump")
        lines.append(f"# Asset:  {self._label}")
        lines.append(f"# Size:   {n:,} bytes  ({n:#010x})")
        lines.append(f"# Rows:   {math.ceil(n / BYTES_PER_ROW):,}  (16 bytes/row)")
        lines.append("")
        lines.append(f"{'Offset':<10}  {'00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F':<51}  ASCII")
        lines.append("-" * 75)
        for row in range(math.ceil(n / BYTES_PER_ROW)):
            offset = row * BYTES_PER_ROW
            chunk  = data[offset:offset + BYTES_PER_ROW]
            hex_lo = ' '.join(f'{b:02X}' for b in chunk[:8])
            hex_hi = ' '.join(f'{b:02X}' for b in chunk[8:])
            # Pad short rows
            hex_lo = hex_lo.ljust(23)
            hex_hi = hex_hi.ljust(23)
            ascii_ = ''.join(chr(b) if 0x20 <= b < 0x7F else '.' for b in chunk)
            lines.append(f"{offset:08X}   {hex_lo}  {hex_hi}   {ascii_}")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            self._size_lbl.setText(
                f"{n:,} bytes  ·  exported → {os.path.basename(path)}"
            )
        except Exception as ex:
            self._size_lbl.setText(f"Export failed: {ex}")

    def highlight(self, start: int, end: int):
        self._hex_view.set_highlight(start, end)
        self._hex_view.scroll_to_offset(start)
        self._scrollbar.setValue(start // BYTES_PER_ROW)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("BrowserHeader")
        hdr.setFixedHeight(44)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 4, 8, 4)
        title = QLabel("HEX INSPECTOR")
        title.setObjectName("PanelTitle")
        hl.addWidget(title)
        hl.addStretch()

        # Jump-to-offset bar
        hl.addWidget(QLabel("Jump:"))
        self._jump_edit = QLineEdit()
        self._jump_edit.setObjectName("SearchBox")
        self._jump_edit.setPlaceholderText("0x0000")
        self._jump_edit.setFixedWidth(80)
        self._jump_edit.setFixedHeight(32)
        self._jump_edit.returnPressed.connect(self._do_jump)
        hl.addWidget(self._jump_edit)
        btn = QPushButton("→")
        btn.setFixedSize(28, 28)
        btn.clicked.connect(self._do_jump)
        hl.addWidget(btn)

        # Export hex dump button
        self._btn_export = QPushButton("Export text…")
        self._btn_export.setObjectName("ExportBtn")
        self._btn_export.setFixedHeight(32)
        self._btn_export.setEnabled(False)
        self._btn_export.setToolTip("Save full hex dump as a .txt file for analysis")
        self._btn_export.clicked.connect(self._do_export)
        hl.addWidget(self._btn_export)

        layout.addWidget(hdr)

        # Content row: hex view + vertical scrollbar
        content = QFrame()
        cl = QHBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self._hex_view = HexView()
        cl.addWidget(self._hex_view, 1)

        self._scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self._scrollbar.setMinimum(0)
        self._scrollbar.setSingleStep(1)
        self._scrollbar.setPageStep(20)
        self._scrollbar.valueChanged.connect(self._on_scroll)
        cl.addWidget(self._scrollbar)

        layout.addWidget(content, 1)

        # Footer
        self._size_lbl = QLabel("No data loaded")
        self._size_lbl.setObjectName("StatusLabel")
        self._size_lbl.setContentsMargins(8, 3, 8, 3)
        self._size_lbl.setFixedHeight(26)
        layout.addWidget(self._size_lbl)

    def _on_scroll(self, value: int):
        self._hex_view._scroll_offset = value
        self._hex_view.update()

    def _do_jump(self):
        text = self._jump_edit.text().strip()
        try:
            offset = int(text, 16) if text.startswith('0x') or any(c in text.lower() for c in 'abcdef') \
                     else int(text)
            self._hex_view.scroll_to_offset(offset)
            row = offset // BYTES_PER_ROW
            self._scrollbar.setValue(row)
        except ValueError:
            pass
