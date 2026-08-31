"""
core/theme.py
Theme / colour-scheme system for RCRA Forge.

Colour slots are named semantic roles (e.g. BG_BASE, ACCENT) rather than
raw hex values.  A Theme is a dict mapping slot → "#rrggbb".

Two built-in presets are provided (Dark, Light).  The user can customise any
slot via the Preferences dialog; overrides are saved to config.json.

Usage
-----
    from core.theme import theme_manager
    qss = theme_manager.stylesheet()   # call after load_config()
    widget.setStyleSheet(qss)
"""

import json, os, copy
from pathlib import Path
from typing import Dict

# ── Slot definitions ─────────────────────────────────────────────────────────

SLOTS: Dict[str, str] = {
    # key             : human label
    "BG_BASE"         : "Base background",
    "BG_PANEL"        : "Panel background",
    "BG_DEEP"         : "Deep background",
    "BG_SURFACE"      : "Surface / widget background",
    "BG_ALT"          : "Alternate row background",
    "BG_HOVER"        : "Hover background",
    "BG_SELECT"       : "Selection background",
    "BG_SELECT_DEEP"  : "Selection background (deep)",
    "BORDER"          : "Border",
    "BORDER_FOCUS"    : "Focus border",
    "BORDER_STRONG"   : "Strong border",
    "TEXT_PRIMARY"    : "Primary text",
    "TEXT_SECONDARY"  : "Secondary text",
    "TEXT_DIM"        : "Dimmed text",
    "TEXT_MUTED"      : "Muted / label text",
    "TEXT_SELECT"     : "Selected text",
    "TEXT_MONO"       : "Monospace / value text",
    "ACCENT"          : "Accent (buttons, links)",
    "ACCENT_HOVER"    : "Accent hover",
    "ACCENT_PRESS"    : "Accent pressed",
    "ACCENT_LIGHT"    : "Accent light (text on dark)",
    "ACCENT_BRIGHT"   : "Accent bright highlight",
    "WARN"            : "Warning / groups toggle",
    "WARN_HOVER"      : "Warning hover",
    "WARN_BG"         : "Warning background",
    "SCROLLBAR"       : "Scrollbar handle",
    "SCROLLBAR_HOVER" : "Scrollbar handle hover",
    "EXPORT_BG"       : "Export button background",
    "EXPORT_BORDER"   : "Export button border",
    "EXPORT_TEXT"     : "Export button text",
}

# ── Built-in presets ─────────────────────────────────────────────────────────

PRESETS: Dict[str, Dict[str, str]] = {
    "Dark (Default)": {
        "BG_BASE"         : "#0b111c",
        "BG_PANEL"        : "#111a2a",
        "BG_DEEP"         : "#070c14",
        "BG_SURFACE"      : "#1a2940",
        "BG_ALT"          : "#142034",
        "BG_HOVER"        : "#263b5c",
        "BG_SELECT"       : "#355b91",
        "BG_SELECT_DEEP"  : "#294a78",
        "BORDER"          : "#334867",
        "BORDER_FOCUS"    : "#ff8b32",
        "BORDER_STRONG"   : "#4a6389",
        "TEXT_PRIMARY"    : "#f3f7ff",
        "TEXT_SECONDARY"  : "#d9e3f2",
        "TEXT_DIM"        : "#bac8dc",
        "TEXT_MUTED"      : "#93a6c5",
        "TEXT_SELECT"     : "#ffffff",
        "TEXT_MONO"       : "#a9d6ff",
        "ACCENT"          : "#3979c7",
        "ACCENT_HOVER"    : "#4b8bd8",
        "ACCENT_PRESS"    : "#24568f",
        "ACCENT_LIGHT"    : "#80bdff",
        "ACCENT_BRIGHT"   : "#70c4ff",
        "WARN"            : "#ff8b32",
        "WARN_HOVER"      : "#ffad68",
        "WARN_BG"         : "#3b2717",
        "SCROLLBAR"       : "#405574",
        "SCROLLBAR_HOVER" : "#5b749b",
        "EXPORT_BG"       : "#2865aa",
        "EXPORT_BORDER"   : "#65a5ed",
        "EXPORT_TEXT"     : "#ffffff",
    },
    "Midnight Blue": {
        "BG_BASE"         : "#0e1420",
        "BG_PANEL"        : "#0a0f18",
        "BG_DEEP"         : "#060a10",
        "BG_SURFACE"      : "#141a28",
        "BG_ALT"          : "#111825",
        "BG_HOVER"        : "#1a2540",
        "BG_SELECT"       : "#1e3a6e",
        "BG_SELECT_DEEP"  : "#152d58",
        "BORDER"          : "#1e2a40",
        "BORDER_FOCUS"    : "#4080d0",
        "BORDER_STRONG"   : "#283850",
        "TEXT_PRIMARY"    : "#c8d8f0",
        "TEXT_SECONDARY"  : "#a8b8d8",
        "TEXT_DIM"        : "#8090b0",
        "TEXT_MUTED"      : "#506080",
        "TEXT_SELECT"     : "#e8f0ff",
        "TEXT_MONO"       : "#70a8e0",
        "ACCENT"          : "#4080d0",
        "ACCENT_HOVER"    : "#3070c0",
        "ACCENT_PRESS"    : "#205090",
        "ACCENT_LIGHT"    : "#60a0f0",
        "ACCENT_BRIGHT"   : "#80c0ff",
        "WARN"            : "#e09020",
        "WARN_HOVER"      : "#f0b030",
        "WARN_BG"         : "#201800",
        "SCROLLBAR"       : "#1e2a40",
        "SCROLLBAR_HOVER" : "#2e4060",
        "EXPORT_BG"       : "#1a3a70",
        "EXPORT_BORDER"   : "#3060b0",
        "EXPORT_TEXT"     : "#c8e0ff",
    },
    "Slate": {
        "BG_BASE"         : "#1c1e24",
        "BG_PANEL"        : "#141618",
        "BG_DEEP"         : "#0e1012",
        "BG_SURFACE"      : "#20222a",
        "BG_ALT"          : "#1e2028",
        "BG_HOVER"        : "#282c38",
        "BG_SELECT"       : "#2a3550",
        "BG_SELECT_DEEP"  : "#222c44",
        "BORDER"          : "#2c2f3a",
        "BORDER_FOCUS"    : "#5080c0",
        "BORDER_STRONG"   : "#3a3e4c",
        "TEXT_PRIMARY"    : "#d0d4de",
        "TEXT_SECONDARY"  : "#b0b6c4",
        "TEXT_DIM"        : "#8890a4",
        "TEXT_MUTED"      : "#606878",
        "TEXT_SELECT"     : "#ffffff",
        "TEXT_MONO"       : "#8ab0d0",
        "ACCENT"          : "#5080c0",
        "ACCENT_HOVER"    : "#4070b0",
        "ACCENT_PRESS"    : "#305090",
        "ACCENT_LIGHT"    : "#70a0e0",
        "ACCENT_BRIGHT"   : "#90c0f0",
        "WARN"            : "#d09030",
        "WARN_HOVER"      : "#e0a840",
        "WARN_BG"         : "#241c08",
        "SCROLLBAR"       : "#282c3a",
        "SCROLLBAR_HOVER" : "#384258",
        "EXPORT_BG"       : "#204878",
        "EXPORT_BORDER"   : "#4070b8",
        "EXPORT_TEXT"     : "#d0e8ff",
    },
    "Light": {
        "BG_BASE"         : "#f0f2f5",
        "BG_PANEL"        : "#e4e7ec",
        "BG_DEEP"         : "#d8dce4",
        "BG_SURFACE"      : "#ffffff",
        "BG_ALT"          : "#f5f6f8",
        "BG_HOVER"        : "#dce4f0",
        "BG_SELECT"       : "#c0d4ee",
        "BG_SELECT_DEEP"  : "#b0c8e8",
        "BORDER"          : "#c8cdd8",
        "BORDER_FOCUS"    : "#3a6fbf",
        "BORDER_STRONG"   : "#b0b8c8",
        "TEXT_PRIMARY"    : "#1a1e28",
        "TEXT_SECONDARY"  : "#2a3040",
        "TEXT_DIM"        : "#485060",
        "TEXT_MUTED"      : "#707888",
        "TEXT_SELECT"     : "#0a0e18",
        "TEXT_MONO"       : "#2050a0",
        "ACCENT"          : "#3a6fbf",
        "ACCENT_HOVER"    : "#2a5faf",
        "ACCENT_PRESS"    : "#1a4f9f",
        "ACCENT_LIGHT"    : "#2050a0",
        "ACCENT_BRIGHT"   : "#1a40a0",
        "WARN"            : "#b87000",
        "WARN_HOVER"      : "#c88010",
        "WARN_BG"         : "#fff8e0",
        "SCROLLBAR"       : "#b0b8c8",
        "SCROLLBAR_HOVER" : "#8090a8",
        "EXPORT_BG"       : "#3a6fbf",
        "EXPORT_BORDER"   : "#2a5faf",
        "EXPORT_TEXT"     : "#ffffff",
    },
}

# ── Stylesheet template ───────────────────────────────────────────────────────

def _build_stylesheet(c: Dict[str, str]) -> str:
    """Build the full Qt stylesheet from a colour slot dict."""
    icon_dir = Path(__file__).resolve().parents[1] / "ui" / "icons"
    chevron_right = (icon_dir / "chevron-right.svg").as_posix()
    chevron_down = (icon_dir / "chevron-down.svg").as_posix()
    chevron_up = (icon_dir / "chevron-up.svg").as_posix()
    return f"""
        QMainWindow, QWidget {{
            background: {c['BG_BASE']};
            color: {c['TEXT_PRIMARY']};
            font-family: 'Segoe UI', 'SF Pro Text', 'Helvetica Neue', sans-serif;
            font-size: 13px;
        }}
        #AppHero {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #090d18, stop:0.42 #121b31, stop:0.76 #172542, stop:1 #0c1220);
            border-bottom: 2px solid #ff7a18;
        }}
        #AppTitle {{
            color: #ffffff;
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 3px;
        }}
        #AppSubtitle {{
            color: #ff9b45;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 1.4px;
        }}
        #ActiveAssetLabel {{
            color: #7f94b9;
            font-family: 'Consolas', 'JetBrains Mono', monospace;
            font-size: 12px;
        }}
        #StatCard {{
            min-width: 88px;
            background: rgba(10, 16, 29, 185);
            border: 1px solid #2c426b;
            border-radius: 8px;
        }}
        #StatValue {{ color: #eef7ff; font-size: 18px; font-weight: 700; }}
        #StatKey {{ color: #9eb0cc; font-size: 11px; font-weight: 700; letter-spacing: 1.3px; }}
        #LiveChip {{
            color: #7dffb2;
            background: rgba(19, 63, 48, 180);
            border: 1px solid #2b9d69;
            border-radius: 17px;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.8px;
        }}
        QMenuBar {{
            background: {c['BG_PANEL']};
            color: {c['TEXT_SECONDARY']};
            border-bottom: 1px solid {c['BORDER']};
            padding: 2px 0;
        }}
        QMenuBar::item:selected {{ background: {c['BORDER']}; }}
        QMenu {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            color: {c['TEXT_PRIMARY']};
        }}
        QMenu::item:selected {{ background: {c['ACCENT']}; color: {c['TEXT_SELECT']}; }}
        QToolBar {{
            background: {c['BG_PANEL']};
            border-bottom: 1px solid {c['BORDER']};
            spacing: 4px;
            padding: 2px 6px;
        }}
        QToolBar QToolButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 3px 8px;
            color: {c['TEXT_SECONDARY']};
        }}
        QToolBar QToolButton:hover    {{ background: {c['BORDER']}; border-color: {c['BORDER_STRONG']}; }}
        QToolBar QToolButton:checked  {{ background: {c['BG_SELECT']}; border-color: {c['ACCENT']}; color: {c['ACCENT_LIGHT']}; }}
        QSplitter::handle {{ background: {c['BORDER']}; width: 4px; height: 4px; }}
        QSplitter::handle:hover   {{ background: {c['ACCENT']}; }}
        QSplitter::handle:pressed {{ background: {c['ACCENT_BRIGHT']}; }}

        #BottomTabs {{
            background: {c['BG_PANEL']};
            border-top: 2px solid {c['BORDER']};
        }}
        #BottomTabs QTabBar::tab {{
            background: {c['BG_BASE']};
            color: {c['TEXT_MUTED']};
            border: none;
            border-bottom: 2px solid transparent;
            padding: 5px 14px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.5px;
        }}
        #BottomTabs QTabBar::tab:hover    {{ color: {c['TEXT_DIM']}; background: {c['BG_SURFACE']}; }}
        #BottomTabs QTabBar::tab:selected {{
            color: {c['ACCENT_LIGHT']};
            border-bottom: 2px solid {c['ACCENT']};
            background: {c['BG_BASE']};
        }}
        #BottomTabs QTabWidget::pane {{ border: none; }}

        #ModelViewTabs {{ background: {c['BG_DEEP']}; }}
        #ModelViewTabs::pane {{ border: 1px solid {c['BORDER_STRONG']}; border-top: none; }}
        #ModelViewTabs QTabBar::tab {{
            background: {c['BG_PANEL']};
            color: {c['TEXT_DIM']};
            border: 1px solid {c['BORDER']};
            border-bottom: 2px solid {c['BORDER']};
            padding: 7px 18px;
            font-size: 12px;
            font-weight: 700;
        }}
        #ModelViewTabs QTabBar::tab:hover {{ color: #ffffff; background: {c['BG_HOVER']}; }}
        #ModelViewTabs QTabBar::tab:selected {{
            color: #ffffff;
            background: {c['BG_SELECT_DEEP']};
            border-bottom: 2px solid #ff8b32;
        }}

        #BrowserHeader {{
            background: {c['BG_PANEL']};
            border-bottom: 1px solid #31486f;
        }}
        #PanelTitle {{
            font-size: 16px;
            font-weight: 800;
            letter-spacing: 1.8px;
            color: #f4f7ff;
        }}
        #PanelSubtitle {{ color: #ff9b45; font-size: 12px; font-weight: 700; letter-spacing: 1px; }}
        #FilterBar {{ background: {c['BG_PANEL']}; border-bottom: 1px solid #283855; }}
        #SearchBox {{
            background: #151e31;
            border: 1px solid #344a72;
            border-radius: 7px;
            padding: 5px 10px;
            color: {c['TEXT_PRIMARY']};
            selection-background-color: #e76f18;
            font-size: 13px;
        }}
        #SearchBox:focus {{ border: 1px solid #ff8428; background: #19243a; }}
        #TypeFilter {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            border-radius: 4px;
            color: {c['TEXT_SECONDARY']};
            font-size: 13px;
        }}
        #AssetTree {{
            background: #0d121e;
            border: none;
            color: {c['TEXT_SECONDARY']};
            alternate-background-color: #111827;
            selection-background-color: {c['BG_SELECT']};
            font-size: 13px;
        }}
        #AssetTree QHeaderView::section {{
            background: #151e31;
            color: {c['TEXT_MUTED']};
            border: none;
            border-bottom: 1px solid #2b3d5e;
            padding: 4px 6px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1px;
        }}
        #AssetTree::item {{ padding: 4px 5px; border-radius: 3px; }}
        #AssetTree::item:hover    {{ background: {c['BG_HOVER']}; }}
        #AssetTree::item:selected {{ background: #304b78; color: #ffffff; border-left: 3px solid #ff8428; }}
        QTreeView::branch {{ background: transparent; }}
        QTreeView::branch:has-children:closed {{
            image: url("{chevron_right}");
        }}
        QTreeView::branch:has-children:open {{
            image: url("{chevron_down}");
        }}
        #StatusLabel {{
            font-size: 12px;
            color: {c['TEXT_MUTED']};
            background: {c['BG_PANEL']};
            border-top: 1px solid {c['BORDER']};
        }}
        #SubPanelLabel {{
            background: {c['BG_DEEP']};
            color: {c['TEXT_MUTED']};
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 1px;
            border-bottom: 1px solid {c['BORDER']};
            padding-left: 8px;
        }}

        QGroupBox {{
            font-size: 12px;
            font-weight: 600;
            color: {c['TEXT_MUTED']};
            border: 1px solid {c['BORDER']};
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            left: 8px;
        }}
        #FieldValue {{
            color: {c['TEXT_MONO']};
            font-family: 'Consolas', 'JetBrains Mono', monospace;
            font-size: 13px;
        }}
        #FmtCombo {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            border-radius: 4px;
            padding: 2px 6px;
            color: {c['TEXT_SECONDARY']};
        }}
        QCheckBox {{ color: {c['TEXT_DIM']}; }}
        QCheckBox::indicator {{
            width: 13px; height: 13px;
            border: 1px solid {c['BORDER_STRONG']};
            border-radius: 3px;
            background: {c['BG_SURFACE']};
        }}
        QCheckBox::indicator:checked {{ background: {c['ACCENT']}; border-color: {c['ACCENT_LIGHT']}; }}
        #ExportBtn {{
            background: {c['EXPORT_BG']};
            border: 1px solid {c['EXPORT_BORDER']};
            border-radius: 5px;
            padding: 6px 12px;
            color: {c['EXPORT_TEXT']};
            font-weight: 600;
            font-size: 12px;
        }}
        #ExportBtn:hover   {{ background: {c['ACCENT_HOVER']}; }}
        #ExportBtn:pressed {{ background: {c['ACCENT_PRESS']}; }}
        #ExportBtn:disabled {{ background: {c['BG_SURFACE']}; color: {c['TEXT_MUTED']}; border-color: {c['BORDER']}; }}
        #ExportStatus {{ color: {c['ACCENT_LIGHT']}; font-size: 12px; }}

        #GroupsToggleBtn {{
            background: transparent;
            border: 1px solid {c['BORDER_STRONG']};
            border-radius: 4px;
            padding: 2px 8px;
            color: {c['TEXT_DIM']};
            font-size: 12px;
            font-weight: 500;
        }}
        #GroupsToggleBtn:hover   {{ background: {c['WARN_BG']}; border-color: {c['WARN']}; color: {c['WARN_HOVER']}; }}
        #GroupsToggleBtn:checked {{ background: {c['WARN_BG']}; border-color: {c['WARN']}; color: {c['WARN']}; font-weight: 700; }}
        #GroupsToggleBtn:checked:hover {{ background: {c['WARN_BG']}; }}
        #QuickFilterBtn {{
            background: #141d2f;
            border: 1px solid #2c3e60;
            border-radius: 11px;
            padding: 2px 8px;
            color: #7f94b9;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.7px;
        }}
        #QuickFilterBtn:hover {{ background: #223454; border-color: #ff8428; color: #ffffff; }}
        #BrowserGuidance {{
            color: #91a4c4;
            font-size: 11px;
            padding: 2px 2px 0 2px;
        }}
        #OverviewBody {{ background: #0d121e; }}
        #OverviewEyebrow {{
            color: #ff8b32;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 1.5px;
        }}
        #OverviewTitle {{ color: #f4f7ff; font-size: 24px; font-weight: 750; }}
        #OverviewPath {{
            color: #7f94b9;
            font-family: 'Consolas', 'JetBrains Mono', monospace;
            font-size: 12px;
        }}
        #OverviewDivider {{ color: #293a59; background: #293a59; max-height: 1px; border: none; }}
        #OverviewMessage {{ color: #d8e3f4; font-size: 15px; line-height: 1.4; }}
        #OverviewDetails {{
            color: #92a8cb;
            background: #121b2c;
            border: 1px solid #283c60;
            border-radius: 8px;
            padding: 14px;
            font-family: 'Consolas', 'JetBrains Mono', monospace;
            font-size: 12px;
        }}
        #OverviewHint {{
            color: #7187ad;
            background: #101a2a;
            border-left: 3px solid #ff8428;
            padding: 10px 12px;
        }}
        #OverviewBadge {{
            min-width: 110px;
            border-radius: 14px;
            padding: 0 12px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.8px;
        }}
        #OverviewBadge[state="loading"] {{ color: #ffc27a; background: #392716; border: 1px solid #9e6429; }}
        #OverviewBadge[state="visual"] {{ color: #7dffb2; background: #133f30; border: 1px solid #2b9d69; }}
        #OverviewBadge[state="data"] {{ color: #a8bad7; background: #1a2538; border: 1px solid #40577b; }}
        #OverviewBadge[state="warning"] {{ color: #ffd37d; background: #3e3117; border: 1px solid #9d7b2d; }}
        #OverviewBadge[state="error"] {{ color: #ff9f9f; background: #421c24; border: 1px solid #a34858; }}
        #LogBox {{
            background: {c['BG_PANEL']};
            border: 1px solid {c['BORDER']};
            border-radius: 4px;
            color: {c['TEXT_MUTED']};
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
        }}
        #GamePathLabel {{ color: {c['TEXT_DIM']}; font-size: 12px; }}
        #ToolbarGuidance {{ color: #ffc184; font-size: 12px; font-weight: 650; }}

        #ZoomRow {{ background: {c['BG_DEEP']}; border-top: 1px solid {c['BORDER']}; }}
        #TexInfo {{ background: {c['BG_PANEL']}; border-top: 1px solid {c['BORDER']}; }}
        #TexInfoKey {{ color: {c['TEXT_DIM']}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
        #TexInfoVal {{ color: {c['TEXT_MONO']}; font-family: 'Consolas', monospace; font-size: 13px; }}

        #InstTable {{
            background: {c['BG_BASE']};
            alternate-background-color: {c['BG_ALT']};
            border: none;
            color: {c['TEXT_DIM']};
            gridline-color: {c['BORDER']};
            selection-background-color: {c['BG_SELECT']};
        }}
        #InstTable QHeaderView::section {{
            background: {c['BG_PANEL']};
            color: {c['TEXT_MUTED']};
            border: none;
            border-bottom: 1px solid {c['BORDER']};
            padding: 3px 6px;
            font-size: 12px;
            font-weight: 600;
        }}

        QScrollBar:vertical {{
            background: {c['BG_PANEL']};
            width: 10px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {c['SCROLLBAR']};
            border-radius: 4px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c['SCROLLBAR_HOVER']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: {c['BG_PANEL']};
            height: 10px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {c['SCROLLBAR']};
            border-radius: 4px;
            min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {c['SCROLLBAR_HOVER']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        QSlider::groove:horizontal {{
            background: {c['BORDER']};
            height: 3px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {c['ACCENT']};
            width: 12px; height: 12px;
            margin: -5px 0;
            border-radius: 6px;
        }}

        QStatusBar {{
            background: {c['BG_PANEL']};
            border-top: 1px solid {c['BORDER']};
            color: {c['TEXT_MUTED']};
            font-size: 12px;
        }}
        QProgressBar {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            border-radius: 3px;
            height: 16px;
            color: {c['TEXT_PRIMARY']};
            text-align: center;
            font-size: 12px;
        }}
        QProgressBar::chunk {{ background: {c['ACCENT']}; border-radius: 3px; }}

        QPushButton {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            border-radius: 4px;
            padding: 3px 8px;
            color: {c['TEXT_SECONDARY']};
        }}
        QPushButton:hover   {{ background: {c['BG_HOVER']}; border-color: {c['BORDER_STRONG']}; }}
        QPushButton:pressed {{ background: {c['BG_ALT']}; }}
        QPushButton:disabled {{ color: #7586a3; background: #121c2b; border-color: #2c3d58; }}

        QTreeWidget, QListWidget, QTableWidget, QTextEdit, QPlainTextEdit {{
            background: {c['BG_DEEP']};
            color: {c['TEXT_SECONDARY']};
            border: 1px solid {c['BORDER']};
            selection-background-color: {c['BG_SELECT']};
            selection-color: #ffffff;
        }}
        QSpinBox, QDoubleSpinBox {{
            background: {c['BG_SURFACE']};
            color: {c['TEXT_PRIMARY']};
            border: 1px solid {c['BORDER_STRONG']};
            border-radius: 4px;
            padding: 3px 6px;
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            width: 18px;
            background: {c['BG_PANEL']};
            border-left: 1px solid {c['BORDER']};
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url("{chevron_up}");
            width: 11px;
            height: 11px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url("{chevron_down}");
            width: 11px;
            height: 11px;
        }}

        /* Fix QScrollArea viewport inheritance */
        QScrollArea > QWidget > QWidget,
        QScrollArea QWidget#PropertiesPanelInner,
        #PropertiesPanelInner {{
            background: {c['BG_BASE']};
            color: {c['TEXT_PRIMARY']};
        }}
        QAbstractScrollArea::viewport {{
            background: {c['BG_BASE']};
        }}

        QDialog {{
            background: {c['BG_BASE']};
            color: {c['TEXT_PRIMARY']};
        }}
        QLabel {{
            color: {c['TEXT_PRIMARY']};
            background: transparent;
        }}
        QLineEdit {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            border-radius: 4px;
            padding: 3px 6px;
            color: {c['TEXT_PRIMARY']};
        }}
        QLineEdit:focus {{ border-color: {c['BORDER_FOCUS']}; }}
        QComboBox {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            border-radius: 4px;
            padding: 3px 25px 3px 6px;
            color: {c['TEXT_PRIMARY']};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border-left: 1px solid {c['BORDER']};
            background: {c['BG_PANEL']};
        }}
        QComboBox::down-arrow {{
            image: url("{chevron_down}");
            width: 12px;
            height: 12px;
        }}
        QComboBox QAbstractItemView {{
            background: {c['BG_SURFACE']};
            border: 1px solid {c['BORDER']};
            selection-background-color: {c['BG_SELECT']};
            color: {c['TEXT_PRIMARY']};
        }}
    """


# ── Theme manager ─────────────────────────────────────────────────────────────

class ThemeManager:
    """Singleton that holds the active colour scheme and builds stylesheets."""

    CONFIG_KEY = "theme"

    def __init__(self):
        self._preset_name: str = "Dark (Default)"
        self._overrides:   Dict[str, str] = {}   # user per-slot overrides
        self._user_presets: Dict[str, Dict[str, str]] = {}  # saved user presets

    # ── Resolved colours ──────────────────────────────────────────────────────

    def resolved(self) -> Dict[str, str]:
        """Return the full merged colour dict (preset + overrides)."""
        if self._preset_name in self._user_presets:
            base = copy.deepcopy(self._user_presets[self._preset_name])
        else:
            base = copy.deepcopy(PRESETS.get(self._preset_name, PRESETS["Dark (Default)"]))
        base.update(self._overrides)
        return base

    def stylesheet(self) -> str:
        return _build_stylesheet(self.resolved())

    # ── Preset ────────────────────────────────────────────────────────────────



    def current_preset(self) -> str:
        return self._preset_name

    def set_preset(self, name: str, clear_overrides: bool = False):
        if name in PRESETS:
            self._preset_name = name
            if clear_overrides:
                self._overrides.clear()

    # ── Per-slot override ─────────────────────────────────────────────────────

    def set_slot(self, slot: str, colour: str):
        self._overrides[slot] = colour

    def reset_slot(self, slot: str):
        self._overrides.pop(slot, None)

    def reset_all_overrides(self):
        self._overrides.clear()

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"preset": self._preset_name, "overrides": copy.deepcopy(self._overrides)}

    def from_dict(self, d: dict):
        self._preset_name = d.get("preset", "Dark (Default)")
        self._overrides   = d.get("overrides", {})
        self._user_presets = d.get("user_presets", {})

    # ── User presets ──────────────────────────────────────────────────────────

    def preset_names(self):
        """All preset names: built-ins first, then user presets alphabetically."""
        return list(PRESETS.keys()) + sorted(self._user_presets.keys())

    def save_user_preset(self, name: str, colours: dict):
        self._user_presets[name] = copy.deepcopy(colours)
        # Switch to it immediately
        self._preset_name = name
        self._overrides.clear()

    def delete_user_preset(self, name: str):
        self._user_presets.pop(name, None)

    def to_dict(self) -> dict:
        return {
            "preset"       : self._preset_name,
            "overrides"    : copy.deepcopy(self._overrides),
            "user_presets" : copy.deepcopy(self._user_presets),
        }


# Expose built-in preset names for guard checks in dialog
BUILTIN_PRESETS = set(PRESETS.keys())

# Singleton
theme_manager = ThemeManager()
