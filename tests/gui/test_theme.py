from dataclasses import asdict

import pytest

from hdd.studio.theme.icons import ICON_DIR, ICONS
from hdd.studio.theme.palette import METHOD_SLOT, matplotlib_rc, series_color
from hdd.studio.theme.qss import GLYPH_NAMES, build_stylesheet
from hdd.studio.theme.tokens import DARK, LIGHT, contrast_ratio

THEMES = pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=["light", "dark"])


@THEMES
def test_text_is_readable_on_every_surface(tokens):
    c = tokens.colors
    for ink in (c.text, c.text_muted):
        for surface in (c.window, c.panel, c.base):
            assert contrast_ratio(ink, surface) >= 4.5
    assert contrast_ratio(c.accent_text, c.accent) >= 4.5
    assert contrast_ratio(c.selection_text, c.selection) >= 4.5
    assert contrast_ratio(c.accent_fg, c.panel) >= 4.5


@THEMES
def test_state_colours_are_readable_as_text(tokens):
    c = tokens.colors
    for ink, tint in ((c.ok, c.ok_bg), (c.warn, c.warn_bg), (c.error, c.error_bg), (c.info, c.info_bg)):
        assert contrast_ratio(ink, c.base) >= 4.5
        assert contrast_ratio(ink, tint) >= 4.5
        assert contrast_ratio(c.text, tint) >= 4.5


@THEMES
def test_input_outlines_are_visible(tokens):
    assert contrast_ratio(tokens.colors.border_strong, tokens.colors.base) >= 3.0


@THEMES
def test_stylesheet_resolves_every_token(tokens):
    glyphs = {name: f"/tmp/{name}.svg" for name in GLYPH_NAMES}
    sheet = build_stylesheet(tokens, glyphs)
    assert "$" not in sheet
    for value in asdict(tokens.colors).values():
        assert value.startswith("#") and len(value) == 7
    assert tokens.colors.accent in sheet


def test_stylesheet_has_none_of_the_rejected_effects():
    sheet = build_stylesheet(LIGHT, {name: "x.svg" for name in GLYPH_NAMES})
    for banned in ("gradient", "box-shadow", "blur"):
        assert banned not in sheet.lower()


def test_every_icon_has_a_file():
    missing = [name for name, stem in ICONS.items() if not (ICON_DIR / f"{stem}.svg").is_file()]
    assert missing == []


def test_icons_render_and_follow_the_theme(theme):
    for name in ICONS:
        assert not theme.icon(name).pixmap(16, 16).isNull()
    light = theme.icon("run").pixmap(16, 16).toImage()
    theme.apply("dark")
    assert theme.tokens is DARK
    assert theme.icon("run").pixmap(16, 16).toImage() != light


def test_theme_switch_rewrites_palette_and_stylesheet(theme, qapp):
    light_sheet = qapp.styleSheet()
    theme.apply("dark")
    assert qapp.styleSheet() != light_sheet
    assert qapp.palette().window().color().name().upper() == DARK.colors.panel
    with pytest.raises(ValueError):
        theme.apply("sepia")


@THEMES
def test_plot_palette_is_never_cycled(tokens):
    assert len(set(tokens.plot.series)) == len(tokens.plot.series) == 8
    assert {series_color(tokens, slot) for slot in METHOD_SLOT.values()} == set(tokens.plot.series[:3])
    with pytest.raises(IndexError):
        series_color(tokens, 8)
    assert matplotlib_rc(tokens)["axes.facecolor"] == tokens.plot.surface
