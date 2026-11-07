"""Data definition of a text object.

TextData is immutable (frozen). Every change creates a new copy; that way the undo / redo
commands only keep the "before" and "after" copies.

The '\\n' characters in the text are the MANUAL line breaks typed with Enter. Automatic
line wrapping is not written into the text; it is recomputed from the box width on every
draw (see text_layout.py).
"""
from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass
from typing import Any


def new_text_id() -> str:
    return f"text_{uuid.uuid4().hex[:10]}"


@dataclass(frozen=True)
class TextData:
    id: str = ""
    text: str = ""
    # Geometry (image pixel coordinates). x, y: top-left corner of the unrotated box.
    # Rotation happens around the center of the box.
    x: float = 0.0
    y: float = 0.0
    width: float = 220.0
    height: float = 120.0
    rotation: float = 0.0
    # Font
    font_family: str = "Arial"
    font_size: int = 32  # piksel
    bold: bool = False
    italic: bool = False
    color: str = "#ff000000"  # #AARRGGBB
    # Alignment and spacing
    align_h: str = "center"  # left | center | right
    align_v: str = "middle"  # top | middle | bottom
    line_spacing: float = 1.0  # line height multiplier
    letter_spacing: float = 0.0  # piksel
    # Outline
    stroke_enabled: bool = False
    stroke_width: float = 3.0
    stroke_color: str = "#ffffffff"
    # Shadow
    shadow_enabled: bool = False
    shadow_color: str = "#a0000000"
    shadow_dx: float = 3.0
    shadow_dy: float = 3.0
    # Arka plan
    bg_enabled: bool = False
    bg_color: str = "#ffffffff"
    bg_radius: float = 0.0

    def with_(self, **changes: Any) -> "TextData":
        return dataclasses.replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TextData":
        """Ignores unknown fields, fills missing fields with defaults and fixes the types
        (for compatibility between old and new project files)."""
        values: dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            if f.name not in raw:
                continue
            default = f.default
            value = raw[f.name]
            try:
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, int):
                    value = int(value)
                elif isinstance(default, float):
                    value = float(value)
                elif isinstance(default, str):
                    value = str(value)
            except (TypeError, ValueError):
                continue
            values[f.name] = value
        data = cls(**values)
        if not data.id:
            data = data.with_(id=new_text_id())
        return data


GEOMETRY_FIELDS = ("x", "y", "width", "height", "rotation")
STYLE_FIELDS = tuple(
    f.name
    for f in dataclasses.fields(TextData)
    if f.name not in ("id", "text") + GEOMETRY_FIELDS
)
# Fields that affect the line wrapping / shape (position and rotation excluded).
LAYOUT_FIELDS = (
    "text", "width", "height", "font_family", "font_size", "bold", "italic",
    "align_h", "align_v", "line_spacing", "letter_spacing",
)
