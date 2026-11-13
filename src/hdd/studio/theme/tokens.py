"""Design tokens: the single source of truth for how the Studio looks.

Everything visual (QPalette, the generated style sheet, icons, plots) is derived
from the two ``Tokens`` instances below. To change the look, edit values here
and nothing else.

Rules these values encode:
- one neutral grey scale for all chrome, one desaturated steel-blue accent;
- green / amber / red are reserved for state and always ship with an icon;
- small radius, 1 px hairlines, no gradients, no shadows;
- compact density.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Colors:
    # Surfaces
    window: str  # application chrome: menu bar, tool bars, dock titles, status bar
    panel: str  # dock contents and forms
    base: str  # inputs, trees, tables, editors
    base_alt: str  # alternate table rows
    menu: str  # popup menus and combo lists
    # Interaction
    hover: str
    hover_soft: str  # row hover inside item views
    pressed: str
    selection: str  # selected row, focused view
    selection_inactive: str
    selection_text: str
    # Lines
    border: str  # hairlines between regions
    border_strong: str  # input and button outlines
    # Ink
    text: str
    text_muted: str
    text_disabled: str
    icon: str
    # Accent
    accent: str  # fills (primary button, check box, progress)
    accent_hover: str
    accent_pressed: str
    accent_text: str  # ink on an accent fill
    accent_fg: str  # accent used as a line or as ink on a surface (focus ring, tab marker, links)
    # State (always paired with an icon and a label)
    ok: str
    warn: str
    error: str
    info: str
    ok_bg: str
    warn_bg: str
    error_bg: str
    info_bg: str


@dataclass(frozen=True)
class PlotColors:
    """Chart chrome and data colours.

    ``series`` is the categorical palette in its fixed order (assign in sequence,
    never cycle). It was validated with the dataviz palette validator against
    ``surface`` in each mode: lightness band, chroma floor, adjacent-pair
    colour-vision-deficiency separation and the normal-vision floor all pass; the
    first three slots also pass with every pair compared, which is what scatter
    plots need. Re-run the validator if ``surface`` or any slot changes.
    """

    surface: str
    ink: str
    muted: str  # tick labels, axis titles
    grid: str
    axis: str
    reference: str  # de-emphasised baseline series
    series: tuple[str, ...]


@dataclass(frozen=True)
class Metrics:
    radius: int = 2
    row_height: int = 24
    control_height: int = 26
    icon_small: int = 16
    icon_toolbar: int = 20
    icon_stroke: float = 1.75
    space: int = 4
    scrollbar: int = 12
    separator: int = 5


@dataclass(frozen=True)
class Typography:
    base_pt: float = 10.0
    small_pt: float = 9.0
    heading_pt: float = 12.0


@dataclass(frozen=True)
class Tokens:
    name: str
    is_dark: bool
    colors: Colors
    plot: PlotColors
    metrics: Metrics = Metrics()
    type: Typography = Typography()


LIGHT = Tokens(
    name="light",
    is_dark=False,
    colors=Colors(
        window="#E7E9EC",
        panel="#F4F5F6",
        base="#FFFFFF",
        base_alt="#F8F9FA",
        menu="#FFFFFF",
        hover="#D9DDE2",
        hover_soft="#EEF1F3",
        pressed="#CBD1D7",
        selection="#CFE0EF",
        selection_inactive="#E2E5E9",
        selection_text="#1C2126",
        border="#D0D4D9",
        border_strong="#8A939D",
        text="#1C2126",
        text_muted="#59626D",
        text_disabled="#9AA2AB",
        icon="#434C56",
        accent="#2F6592",
        accent_hover="#295980",
        accent_pressed="#224B6C",
        accent_text="#FFFFFF",
        accent_fg="#2F6592",
        ok="#2B7548",
        warn="#96600A",
        error="#B3261E",
        info="#2F6592",
        ok_bg="#E7F2EB",
        warn_bg="#FAF2E1",
        error_bg="#FBEAE8",
        info_bg="#E9F0F6",
    ),
    plot=PlotColors(
        surface="#FFFFFF",
        ink="#1C2126",
        muted="#59626D",
        grid="#E6E9EC",
        axis="#B1B8C0",
        reference="#8A929B",
        series=(
            "#2A78D6",  # blue
            "#EB6834",  # orange
            "#1BAF7A",  # aqua
            "#EDA100",  # yellow
            "#E87BA4",  # magenta
            "#008300",  # green
            "#6250D6",  # violet
            "#E34948",  # red
        ),
    ),
)

DARK = Tokens(
    name="dark",
    is_dark=True,
    colors=Colors(
        window="#2A2C2F",
        panel="#303236",
        base="#1F2123",
        base_alt="#242629",
        menu="#303236",
        hover="#3C3F44",
        hover_soft="#2A2D31",
        pressed="#474B51",
        selection="#2C4A66",
        selection_inactive="#393C41",
        selection_text="#E8EAED",
        border="#3F4349",
        border_strong="#6E747D",
        text="#DDE0E4",
        text_muted="#9EA5AE",
        text_disabled="#6B7178",
        icon="#C2C7CE",
        accent="#3A76A8",
        accent_hover="#4383B8",
        accent_pressed="#326893",
        accent_text="#FFFFFF",
        accent_fg="#7FB2E0",
        ok="#62B181",
        warn="#D9A640",
        error="#E5786D",
        info="#7FB2E0",
        ok_bg="#24352B",
        warn_bg="#3A3222",
        error_bg="#3F2927",
        info_bg="#26333F",
    ),
    plot=PlotColors(
        surface="#1F2123",
        ink="#DDE0E4",
        muted="#9EA5AE",
        grid="#2E3135",
        axis="#585D65",
        reference="#7C838C",
        series=(
            "#3987E5",  # blue
            "#D95926",  # orange
            "#199E70",  # aqua
            "#C98500",  # yellow
            "#D55181",  # magenta
            "#008300",  # green
            "#9085E9",  # violet
            "#E66767",  # red
        ),
    ),
)

THEMES = {"light": LIGHT, "dark": DARK}


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2 contrast ratio between two ``#RRGGBB`` colours."""
    hi, lo = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)
