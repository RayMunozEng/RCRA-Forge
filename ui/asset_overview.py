"""Clear, user-facing summary for visual and data-only Rift Apart assets."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class AssetOverview(QWidget):
    """A visible response for every selection, including non-renderable data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        body = QWidget()
        body.setObjectName("OverviewBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(12)

        self._eyebrow = QLabel("Asset details")
        self._eyebrow.setObjectName("OverviewEyebrow")
        self._title = QLabel("Choose an asset")
        self._title.setObjectName("OverviewTitle")
        self._title.setWordWrap(True)
        self._badge = QLabel("No selection")
        self._badge.setObjectName("OverviewBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedHeight(28)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self._eyebrow)
        title_col.addWidget(self._title)
        title_row.addLayout(title_col, 1)
        title_row.addWidget(self._badge)
        layout.addLayout(title_row)

        self._path = QLabel("Search or choose a row from Game assets.")
        self._path.setObjectName("OverviewPath")
        self._path.setWordWrap(True)
        layout.addWidget(self._path)

        divider = QFrame()
        divider.setObjectName("OverviewDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        self._message = QLabel(
            "Models and textures open a preview. Other files show their available details here."
        )
        self._message.setObjectName("OverviewMessage")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._details = QLabel("")
        self._details.setObjectName("OverviewDetails")
        self._details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._details.setWordWrap(True)
        layout.addWidget(self._details)
        layout.addStretch(1)

        self._hint = QLabel(
            "Tip: choose Visual files to list assets with an image, model, or scene preview."
        )
        self._hint.setObjectName("OverviewHint")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        scroll.setWidget(body)

    def show_ready(
        self,
        asset_count: int,
        model_count: int,
        texture_count: int,
        actor_count: int,
    ):
        """Show unmistakable proof that the Steam archive index is ready."""
        self._eyebrow.setText("Game data ready")
        self._title.setText("Models ready to browse")
        self._path.setText(
            "The model list is already open in Game assets. Nothing has been "
            "auto-selected."
        )
        self._badge.setText("Ready")
        self._badge.setProperty("state", "visual")
        self._message.setText(
            f"{model_count:,} models are listed on the left. Click a gold model group "
            "or an individual model file to open Model Preview."
        )
        self._details.setText(
            f"{asset_count:,} total archive entries\n"
            f"{model_count:,} models\n"
            f"{texture_count:,} textures\n"
            f"{actor_count:,} actors"
        )
        self._hint.setText(
            "Use 3D models, Textures, Visual files, or All assets to change the list."
        )
        self._refresh_badge()

    def show_loading(self, name: str, path: str, extension: str, size: int):
        ext = extension.upper() or "RAW"
        self._eyebrow.setText("Loading selected asset")
        self._title.setText(name)
        self._path.setText(path)
        self._badge.setText(ext)
        self._badge.setProperty("state", "loading")
        self._refresh_badge()
        self._message.setText("Reading and identifying this file from the game archive…")
        self._details.setText(f"Stored file size: {size:,} bytes")

    def show_actor(self, actor, actor_path: str):
        self._eyebrow.setText("Actor definition")
        if actor.has_model and actor.model_asset_id:
            self._badge.setText("3D MODEL LINKED")
            self._badge.setProperty("state", "visual")
            self._message.setText(
                "This actor references a renderable model. The linked model is now "
                "being shown in the 3D viewport."
            )
            self._details.setText(
                f"Actor\n{actor_path}\n\nLinked model\n{actor.model_path}\n\n"
                f"Model asset ID\n{actor.model_asset_id:016X}"
            )
        elif actor.has_model:
            self._badge.setText("MODEL NOT INSTALLED")
            self._badge.setProperty("state", "warning")
            self._message.setText(
                "This actor names a model, but that model could not be resolved in "
                "the installed archive/name index."
            )
            self._details.setText(f"Actor\n{actor_path}\n\nModel path\n{actor.model_path}")
        else:
            self._badge.setText("DATA ONLY")
            self._badge.setProperty("state", "data")
            self._message.setText(
                "This actor has no model. It defines gameplay, navigation, effects, "
                "or placement behavior, so there is no 3D object to display."
            )
            strings = "\n".join(actor.all_strings[:12]) or "No readable strings"
            self._details.setText(f"Actor\n{actor_path}\n\nEmbedded data\n{strings}")
        self._refresh_badge()

    def show_visual(self, kind: str, message: str, details: str = ""):
        self._eyebrow.setText(f"{kind} preview")
        self._badge.setText("Preview open")
        self._badge.setProperty("state", "visual")
        self._message.setText(message)
        self._details.setText(details)
        self._refresh_badge()

    def show_data(self, kind: str, path: str, size: int, details: str = ""):
        self._eyebrow.setText(f"{kind or 'Data'} file")
        self._badge.setText("Details only")
        self._badge.setProperty("state", "data")
        self._message.setText(
            "This file does not contain directly renderable geometry or pixels. "
            "Its raw structure is available in Raw Bytes."
        )
        self._details.setText(
            f"Path\n{path}\n\nArchive payload\n{size:,} bytes"
            + (f"\n\n{details}" if details else "")
        )
        self._refresh_badge()

    def show_error(self, message: str):
        self._eyebrow.setText("Preview failed")
        self._badge.setText("Error")
        self._badge.setProperty("state", "error")
        self._message.setText(message)
        self._refresh_badge()

    def _refresh_badge(self):
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)
