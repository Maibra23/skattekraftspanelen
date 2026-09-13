"""Tests for the choropleth basemap configuration.

Regression guard: CARTO started stamping its anonymous basemap tiles with an
"API KEY REQUIRED" watermark, which silently defaced the map (tiles still
return HTTP 200, so nothing raises).  The basemap must therefore come from a
tile service that serves clean tiles without credentials.
"""

from src.ui.choropleth import (
    _TILE_ATTRIBUTION,
    _TILE_URL,
    build_base_map,
)

_KEYED_TILE_HOSTS = ("cartocdn.com", "stadiamaps.com", "thunderforest.com", "mapbox.com")


def test_tile_url_is_a_keyless_xyz_template() -> None:
    """The tile template must be complete and free of credential parameters."""
    for placeholder in ("{z}", "{x}", "{y}"):
        assert placeholder in _TILE_URL

    lowered = _TILE_URL.lower()
    assert "api_key" not in lowered
    assert "apikey" not in lowered
    assert "access_token" not in lowered


def test_tile_url_avoids_providers_that_require_credentials() -> None:
    """Hosts known to watermark or reject anonymous traffic are not allowed."""
    for host in _KEYED_TILE_HOSTS:
        assert host not in _TILE_URL


def test_base_map_renders_configured_tiles_with_attribution() -> None:
    """The rendered Leaflet map uses the configured tiles and credits them."""
    html = build_base_map().get_root().render()

    assert _TILE_URL in html
    assert "Esri" in html
    for host in _KEYED_TILE_HOSTS:
        assert host not in html


def test_tile_attribution_is_non_empty() -> None:
    """Custom tile URLs require an attribution string."""
    assert _TILE_ATTRIBUTION.strip()


# ---------------------------------------------------------------------------
# Map layers (METHODOLOGY §13.4).
# The plan's explicit caution: position is a *level* and drift is *signed*.
# Sharing one palette between them would mislead — a diverging scale implies a
# meaningful midpoint, which an index level does not have.
# ---------------------------------------------------------------------------

import colorsys
from dataclasses import replace

import pytest

from src.ui.choropleth import (
    MAP_LAYERS,
    _build_responsive_legend,
    build_colormap,
    color_for,
    resolve_layer,
)
from src.ui.css import DIVERGING_SCALE, POSITION_SCALE
from src.ui.labels import POSITION_BANDS
from src.ui.sidebar import _BAND_LEGEND


def _hue_degrees(hex_color: str) -> float:
    """Hue of a hex colour, 0-360.  Red sits near 0, green near 120."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def _is_red(hex_color: str) -> bool:
    hue = _hue_degrees(hex_color)
    return hue <= 20 or hue >= 340


def _is_green(hex_color: str) -> bool:
    return 80 <= _hue_degrees(hex_color) <= 170


class TestMapLayers:
    def test_the_three_planned_layers_exist(self):
        assert set(MAP_LAYERS) == {"position", "drift"}

    def test_each_layer_reads_a_different_column(self):
        columns = [layer.column for layer in MAP_LAYERS.values()]
        assert len(set(columns)) == len(columns)

    def test_position_diverges_around_riket_not_zero(self):
        """A level has a midpoint after all, and it is 100, not 0.  The old
        `diverging` bool could only say "centred on zero", which is why this
        layer was drawn on a single-hue ramp instead."""
        layer = MAP_LAYERS["position"]
        assert layer.midpoint == 100.0
        assert not layer.signed
        assert layer.colors == POSITION_SCALE

    def test_the_neutral_colour_lands_on_riket_exactly(self):
        """The reason the stops are explicit.  The domain is 80-130, so an
        evenly spaced ramp would put its neutral on 105 and paint every
        kommun between 100 and 105 as though it sat below the average."""
        layer = MAP_LAYERS["position"]
        assert color_for(layer, 100.0) == POSITION_SCALE[2].lower()
        assert color_for(layer, 80.0) == POSITION_SCALE[0].lower()
        assert color_for(layer, 130.0) == POSITION_SCALE[-1].lower()

    def test_position_turns_colour_on_the_band_cuts(self):
        """The map has to change colour where the sidebar pills change band,
        or the filter and the picture disagree about what 90 means."""
        layer = MAP_LAYERS["position"]
        cuts = tuple(b.upper for b in POSITION_BANDS if b.upper != float("inf"))
        assert cuts == (90.0, 110.0)
        for cut in cuts:
            assert cut in layer.stops
            assert cut in layer.legend_ticks

    def test_the_two_layers_are_told_apart_by_hue(self):
        """A reader toggling between them must see that something changed."""
        position = set(c.lower() for c in MAP_LAYERS["position"].colors)
        drift = set(c.lower() for c in MAP_LAYERS["drift"].colors)
        assert not (position & drift)

    def test_every_layer_anchors_one_stop_per_colour(self):
        """branca fails obscurely on a mismatch, and silently on a domain that
        does not increase."""
        for layer in MAP_LAYERS.values():
            assert len(layer.stops) == len(layer.colors), layer.key
            assert layer.stops[0] == layer.vmin, layer.key
            assert layer.stops[-1] == layer.vmax, layer.key
            assert all(
                b > a for a, b in zip(layer.stops, layer.stops[1:])
            ), layer.key
            assert layer.vmin <= layer.midpoint <= layer.vmax, layer.key

    def test_no_layer_ends_in_red_and_green(self):
        """Red-green deficiency affects ~8 % of men, and both layers are
        headline ones.  This used to block two hex values by name, which
        confused the hazard with one recipe for it: green is only a problem
        opposite red.  The position ramp does end in green, on purpose, and
        is safe because the other end is purple.  What no ramp may do is put
        red at one end and green at the other."""
        for layer in MAP_LAYERS.values():
            low, high = layer.colors[0], layer.colors[-1]
            assert not (_is_red(low) and _is_green(high)), layer.key
            assert not (_is_green(low) and _is_red(high)), layer.key

    def test_the_ends_of_every_ramp_are_far_apart_in_hue(self):
        """A diverging ramp whose ends are neighbours is a sequential ramp
        with extra steps: the reader cannot tell which side of the midpoint
        a kommun is on."""
        for layer in MAP_LAYERS.values():
            gap = abs(_hue_degrees(layer.colors[0]) - _hue_degrees(layer.colors[-1]))
            gap = min(gap, 360 - gap)
            assert gap >= 60, f"{layer.key}: ends only {gap:.0f} degrees apart"

    def test_position_scale_is_clipped_to_the_body_of_the_distribution(self):
        """Median 96.6, p95 127, max 208 — an unclipped scale renders 90 %
        of kommuner as one indistinguishable colour."""
        layer = MAP_LAYERS["position"]
        assert layer.vmin >= 70
        assert layer.vmax <= 150

    def test_drift_is_signed_and_symmetric_about_zero(self):
        layer = MAP_LAYERS["drift"]
        assert layer.signed
        assert layer.midpoint == 0.0
        assert layer.vmin == -layer.vmax, "a signed scale must centre on zero"
        assert color_for(layer, 0.0) == DIVERGING_SCALE[3].lower()

    def test_drift_marks_nothing_beyond_its_midpoint(self):
        """Its inner stops are interpolation points, not readings."""
        assert MAP_LAYERS["drift"].legend_ticks == ()

    def test_drift_keeps_the_diverging_ramp(self):
        assert MAP_LAYERS["drift"].colors == DIVERGING_SCALE

    def test_the_warm_end_always_means_worse(self):
        """DIVERGING_SCALE runs warm (orange) to cool (blue)."""
        warm = DIVERGING_SCALE[0]
        assert MAP_LAYERS["drift"].colors[0] == warm, "falling behind must read warm"

    def test_the_retired_score_is_not_offered_as_a_layer(self):
        """It was withdrawn from the map: r = +0.016 against realised growth,
        and a layer a reader can still select is a layer they will still use."""
        assert "vulnerability" not in MAP_LAYERS
        for layer in MAP_LAYERS.values():
            assert "arbarhet" not in layer.label, layer.label

    def test_every_layer_carries_a_swedish_label_and_caption(self):
        for layer in MAP_LAYERS.values():
            assert layer.label.strip()
            assert layer.legend_caption.strip()


class TestResolveLayer:
    def test_resolves_by_key(self):
        assert resolve_layer("drift").column == "drift_5y"

    def test_resolves_by_swedish_label(self):
        """The radio widget hands back the label, not the key."""
        label = MAP_LAYERS["position"].label
        assert resolve_layer(label).key == "position"

    def test_raises_on_an_unknown_layer(self):
        with pytest.raises(KeyError, match="[Oo]känt kartlager"):
            resolve_layer("nonsense")


class TestColorFor:
    """The one place a value becomes a colour, so the map and any chart of
    the same quantity cannot drift apart."""

    def test_values_outside_the_domain_clip_to_its_ends(self):
        layer = MAP_LAYERS["position"]
        assert color_for(layer, 208.0) == color_for(layer, layer.vmax)
        assert color_for(layer, 12.0) == color_for(layer, layer.vmin)

    def test_a_missing_value_is_drawn_at_the_midpoint(self):
        """Not at the bottom of the ramp, which was the old behaviour and is
        a claim: it says the kommun sits far below riket, rather than that
        nothing is known about it."""
        layer = MAP_LAYERS["position"]
        neutral = color_for(layer, layer.midpoint)
        assert color_for(layer, None) == neutral
        assert color_for(layer, float("nan")) == neutral

    def test_the_colour_is_six_digit_hex(self):
        """branca returns eight digits.  Plotly rejects that form, and the
        histogram is tinted from this function."""
        for layer in MAP_LAYERS.values():
            colour = color_for(layer, layer.midpoint)
            assert len(colour) == 7 and colour.startswith("#"), colour

    def test_passing_a_prebuilt_ramp_changes_nothing(self):
        layer = MAP_LAYERS["drift"]
        cmap = build_colormap(layer)
        for value in (-9.0, -1.0, 0.0, 1.0, 9.0):
            assert color_for(layer, value, cmap) == color_for(layer, value)


class TestBuildColormap:
    def test_rejects_stops_that_do_not_increase(self):
        layer = MAP_LAYERS["position"]
        broken = replace(layer, stops=[80.0, 100.0, 100.0, 110.0, 130.0])
        with pytest.raises(ValueError, match="must increase"):
            build_colormap(broken)

    def test_rejects_a_stop_count_that_misses_the_colours(self):
        layer = MAP_LAYERS["position"]
        broken = replace(layer, stops=[80.0, 100.0, 130.0])
        with pytest.raises(ValueError, match="stops for"):
            build_colormap(broken)


class TestLegend:
    def test_the_midpoint_tick_sits_where_the_midpoint_falls(self):
        """80-130 centred on 100: two fifths across, not halfway.  The middle
        label used to be a hardcoded "0", then a hardcoded average of the two
        ends, and both printed a number the colour under it did not mean."""
        html = _build_responsive_legend(MAP_LAYERS["position"])
        assert "left:40.0%" in html
        assert "left:50.0%" not in html
        assert ">100</span>" in html

    def test_a_signed_midpoint_is_written_without_a_sign(self):
        html = _build_responsive_legend(MAP_LAYERS["drift"])
        assert ">0</span>" in html
        assert ">+0</span>" not in html

    def test_the_gradient_follows_the_stops_not_the_colour_count(self):
        layer = MAP_LAYERS["position"]
        html = _build_responsive_legend(layer)
        for stop in layer.stops:
            pct = (stop - layer.vmin) / (layer.vmax - layer.vmin) * 100
            assert f"{pct:.1f}%" in html

    def test_every_layer_labels_both_ends_and_its_midpoint(self):
        for layer in MAP_LAYERS.values():
            html = _build_responsive_legend(layer)
            assert 'class="kss-end"' in html
            assert 'class="kss-mid"' in html
            assert layer.legend_caption in html


class TestSidebarAgreesWithTheMap:
    def test_band_swatches_come_from_the_map_ramp(self):
        """A pill and the kommuner it selects have to be the same colour."""
        swatches = [colour for colour, _ in _BAND_LEGEND]
        assert all(c in POSITION_SCALE for c in swatches)

    def test_the_swatches_run_high_band_first(self):
        """The legend reads top-down, so it must not invert the ramp."""
        swatches = [colour for colour, _ in _BAND_LEGEND]
        positions = [POSITION_SCALE.index(c) for c in swatches]
        assert positions == sorted(positions, reverse=True)

    def test_there_is_one_swatch_per_band(self):
        assert len(_BAND_LEGEND) == len(POSITION_BANDS)
