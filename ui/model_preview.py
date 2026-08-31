"""Reliable CPU-rendered model preview for systems where OpenGL is unavailable.

This is intentionally a preview, not a replacement for the textured OpenGL
viewport.  It draws actual parsed model triangles with a small software
raster/painter pipeline so selecting a model can never result in a blank panel.
"""

from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget

from core.mesh import mesh_to_numpy
from ui.camera_controls import (
    AUTODESK_CONTROL_OVERLAY,
    AUTODESK_CONTROL_TOOLTIP,
    autodesk_mouse_mode,
)
from ui.controls_dialog import load_controls


class SoftwareModelPreview(QWidget):
    MAX_DRAW_TRIANGLES = 14_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self._meshes: list[tuple[np.ndarray, np.ndarray, int]] = []
        self._triangle_count = 0
        self._vertex_count = 0
        self._material_colors: dict[int, tuple[int, int, int]] = {}
        self._yaw = 32.0
        self._pitch = 18.0
        self._zoom = 1.0
        self._pan = np.zeros(2, dtype=np.float32)
        self._last_pos = None
        self._mouse_mode = None
        self._drag_button = Qt.MouseButton.NoButton
        self._controls = load_controls()
        self.setMinimumSize(420, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(AUTODESK_CONTROL_TOOLTIP)

    def load_mesh(self, model):
        self._model = model
        self._meshes = []
        self._material_colors = {}
        self._vertex_count = len(getattr(model, "vertexes", []))
        self._triangle_count = 0

        primary_meshes = [mesh for mesh in model.meshes if mesh.look_index == 0]
        if not primary_meshes:
            primary_meshes = list(model.meshes)
        available_lods = sorted({mesh.lod_level for mesh in primary_meshes})
        preview_lod = available_lods[0] if available_lods else 0

        candidates = []
        for mesh in primary_meshes:
            if mesh.lod_level != preview_lod:
                continue
            positions, _, _, indices = mesh_to_numpy(model, mesh)
            if positions is None or indices is None or len(indices) < 3:
                continue
            triangles = np.asarray(indices, dtype=np.int64).reshape(-1, 3)
            triangles = triangles[
                np.all(triangles >= 0, axis=1)
                & np.all(triangles < len(positions), axis=1)
            ]
            if not len(triangles):
                continue
            candidates.append((np.asarray(positions, dtype=np.float32), triangles, mesh.material_index))
            self._triangle_count += len(triangles)

        stride = max(1, math.ceil(self._triangle_count / self.MAX_DRAW_TRIANGLES))
        self._meshes = [(p, t[::stride], m) for p, t, m in candidates]
        self.reset_view()

    def load_textures(self, material_textures: dict):
        """Use average decoded material colours to make the CPU preview legible."""
        colours = {}
        for mat_idx, slots in (material_textures or {}).items():
            if not isinstance(slots, dict):
                continue
            preferred = None
            for role, payload in slots.items():
                role_l = role.lower()
                if any(key in role_l for key in (
                    "base_color", "albedo", "diffuse", "color_id",
                )):
                    preferred = payload
                    break
            if preferred is None:
                continue
            rgba, width, height = preferred[:3]
            try:
                pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(-1, 4)
                sample = pixels[::max(1, len(pixels) // 4096), :3]
                rgb = np.percentile(sample, 62, axis=0).astype(int)
                colours[int(mat_idx)] = tuple(int(v) for v in rgb)
            except Exception:
                continue
        self._material_colors.update(colours)
        self.update()

    def clear(self):
        self._model = None
        self._meshes = []
        self._triangle_count = 0
        self._vertex_count = 0
        self.update()

    def reset_view(self):
        self._yaw = 32.0
        self._pitch = 18.0
        self._zoom = 1.0
        self._pan[:] = 0.0
        self.update()

    def reload_controls(self):
        """Re-read the shared viewport navigation preferences."""
        self._controls = load_controls()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_background(painter)

        if not self._meshes:
            painter.setPen(QColor("#9fb2cf"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "MODEL PREVIEW\n\nSelect a .model or model-linked .actor",
            )
            return

        all_positions = np.concatenate([positions for positions, _, _ in self._meshes], axis=0)
        mn = all_positions.min(axis=0)
        mx = all_positions.max(axis=0)
        center = (mn + mx) * 0.5
        radius = max(float(np.linalg.norm(mx - mn)) * 0.5, 1e-5)

        yaw = math.radians(self._yaw)
        pitch = math.radians(self._pitch)
        eye_direction = np.array([
            math.cos(yaw) * math.cos(pitch),
            math.sin(pitch),
            math.sin(yaw) * math.cos(pitch),
        ], dtype=np.float32)
        forward = -eye_direction
        world_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        right = np.cross(forward, world_up)
        right /= max(float(np.linalg.norm(right)), 1e-8)
        camera_up = np.cross(right, forward)
        camera_up /= max(float(np.linalg.norm(camera_up)), 1e-8)
        view_basis = np.stack((right, camera_up, eye_direction), axis=0)

        scale = min(self.width(), self.height()) * 0.39 * self._zoom / radius
        origin_x = self.width() * 0.5 + float(self._pan[0])
        origin_y = self.height() * 0.53 + float(self._pan[1])
        light = np.array([-0.35, -0.55, 0.76], dtype=np.float32)
        light /= np.linalg.norm(light)
        draw_faces = []

        for mesh_index, (positions, triangles, material_index) in enumerate(self._meshes):
            rotated = (positions - center) @ view_basis.T
            base = self._material_colors.get(
                material_index,
                self._fallback_colour(mesh_index, material_index),
            )
            for triangle in triangles:
                points = rotated[triangle]
                edge_a = points[1] - points[0]
                edge_b = points[2] - points[0]
                normal = np.cross(edge_a, edge_b)
                norm = float(np.linalg.norm(normal))
                if norm < 1e-9:
                    continue
                normal /= norm
                # Back faces remain faintly visible; many game meshes rely on
                # two-sided materials and should not disappear in preview.
                brightness = 0.28 + 0.72 * abs(float(np.dot(normal, light)))
                # Game materials can average almost black. Keep their hue, but
                # add enough ambient lift that loaded geometry cannot disappear
                # into the dark preview background.
                colour = tuple(
                    min(255, max(42, int(channel * brightness) + 24))
                    for channel in base
                )
                screen = [
                    QPointF(origin_x + float(p[0]) * scale, origin_y - float(p[1]) * scale)
                    for p in points
                ]
                draw_faces.append((float(points[:, 2].mean()), screen, colour))

        draw_faces.sort(key=lambda item: item[0])
        outline = QPen(QColor(82, 112, 155, 135), 0.7)
        for _, screen, colour in draw_faces:
            painter.setPen(outline)
            painter.setBrush(QColor(*colour))
            painter.drawPolygon(QPolygonF(screen))

        self._draw_overlay(painter, len(draw_faces))

    def _draw_background(self, painter: QPainter):
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#17243a"))
        gradient.setColorAt(0.58, QColor("#0e1726"))
        gradient.setColorAt(1.0, QColor("#090f19"))
        painter.fillRect(self.rect(), gradient)

        painter.setPen(QPen(QColor(66, 91, 126, 75), 1.0))
        horizon = int(self.height() * 0.73)
        for step in range(-8, 9):
            x = self.width() * 0.5 + step * self.width() * 0.075
            painter.drawLine(QPointF(self.width() * 0.5, horizon), QPointF(x, self.height()))
        for row in range(7):
            t = row / 6.0
            y = horizon + (t * t) * (self.height() - horizon)
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))

    def _draw_overlay(self, painter: QPainter, drawn_triangles: int):
        painter.setPen(QColor("#f5f8ff"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(18, 26, "RELIABLE MODEL PREVIEW")
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor("#9fb2cf"))
        painter.drawText(
            18,
            44,
            f"{self._vertex_count:,} vertices  •  {self._triangle_count:,} triangles"
            + (f"  •  drawing {drawn_triangles:,}" if drawn_triangles < self._triangle_count else ""),
        )
        painter.setPen(QColor("#ff9b45"))
        painter.drawText(
            18, self.height() - 18,
            AUTODESK_CONTROL_OVERLAY,
        )

    @staticmethod
    def _fallback_colour(mesh_index: int, material_index: int) -> tuple[int, int, int]:
        palette = [
            (85, 178, 255),
            (255, 133, 55),
            (121, 224, 174),
            (184, 128, 255),
            (255, 205, 91),
            (90, 211, 224),
        ]
        return palette[(mesh_index + max(0, material_index)) % len(palette)]

    def mousePressEvent(self, event: QMouseEvent):
        mode = autodesk_mouse_mode(event.button(), event.modifiers())
        if mode is None:
            self._last_pos = None
            self._mouse_mode = None
            self._drag_button = Qt.MouseButton.NoButton
            super().mousePressEvent(event)
            return
        self.setFocus()
        self._last_pos = event.position()
        self._mouse_mode = mode
        self._drag_button = event.button()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_pos is not None and event.buttons() & self._drag_button:
            delta = event.position() - self._last_pos
            self._last_pos = event.position()
            if self._mouse_mode == "tumble":
                dx = -delta.x() if self._controls.get("invert_orbit_x", False) else delta.x()
                dy = -delta.y() if self._controls.get("invert_orbit_y", False) else delta.y()
                self._yaw += dx * 0.32
                self._pitch = max(-88.0, min(88.0, self._pitch - dy * 0.32))
            elif self._mouse_mode == "track":
                self._pan += np.array([delta.x(), delta.y()], dtype=np.float32)
            else:
                speed = float(self._controls.get("zoom_speed", 1.0))
                self._zoom = float(np.clip(
                    self._zoom * math.exp(delta.x() * 0.01 * speed),
                    0.15, 8.0,
                ))
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != self._drag_button:
            super().mouseReleaseEvent(event)
            return
        self._last_pos = None
        self._mouse_mode = None
        self._drag_button = Qt.MouseButton.NoButton
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        steps = event.angleDelta().y() / 120.0
        if self._controls.get("invert_zoom", False):
            steps = -steps
        speed = float(self._controls.get("zoom_speed", 1.0))
        factor = math.exp(steps * math.log(1.12) * speed)
        self._zoom = max(0.15, min(8.0, self._zoom * factor))
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.reset_view()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_F, Qt.Key.Key_A):
            self.reset_view()
            event.accept()
        else:
            super().keyPressEvent(event)
