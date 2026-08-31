"""Shared Autodesk Maya camera-navigation contract for both model previews."""

from PyQt6.QtCore import Qt


AUTODESK_MOUSE_BINDINGS = (
    ("LMB drag", "Tumble around pivot"),
    ("MMB drag", "Track in view plane"),
    ("RMB drag", "Dolly horizontally"),
)

AUTODESK_CONTROL_TOOLTIP = (
    "Maya-style motion: LMB tumble • MMB track • RMB dolly • "
    "Wheel dolly • F frame / A frame all"
)

AUTODESK_CONTROL_OVERLAY = (
    "LMB TUMBLE   •   MMB TRACK   •   RMB DOLLY   •   F/A FRAME"
)


def autodesk_mouse_mode(button: Qt.MouseButton,
                         modifiers: Qt.KeyboardModifier) -> str | None:
    """Return the direct mouse operation using Maya-like motion directions."""
    _ = modifiers  # Alt remains a harmless optional modifier, never a requirement.
    return {
        Qt.MouseButton.LeftButton: "tumble",
        Qt.MouseButton.MiddleButton: "track",
        Qt.MouseButton.RightButton: "dolly",
    }.get(button)
