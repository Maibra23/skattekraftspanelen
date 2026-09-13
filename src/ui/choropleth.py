"""Render an interactive Folium choropleth map of municipal position and drift.

Run scripts/download_geojson.py once before first use to populate data/geo/.

render_choropleth(data, layer, height, key) creates a polygon-based Folium map
using data/geo/kommuner.geojson (from okfse/sweden-geojson).  Two layers are
offered, both on diverging ramps but around different midpoints: relative
position is centred on riket = 100, five-year drift on zero.  Each layer
anchors its colours to explicit domain stops, so the neutral colour lands on
the midpoint exactly rather than halfway along the bar.  Map height is 480 px.
build_colormap() and color_for() are public so that a chart showing the same
quantity can be tinted from the same ramp.  Tooltips show
municipality name and key metrics.  The map is embedded in Streamlit via
streamlit_folium.st_folium().  Basemap tiles come from Esri's light grey
canvas, which needs no API key.

Each layer carries its own legend caption; see MAP_LAYERS.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import branca.colormap as cm
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src.ui.css import COLORS, DIVERGING_SCALE, POSITION_SCALE
from src.ui.labels import SWEDISH_LABELS, format_pct, format_sek

#: DIVERGING_SCALE runs orange (low) to blue (high), which is the right
#: direction for drift: falling behind reads warm, gaining reads cool.
#: POSITION_SCALE runs purple (below riket) to green (above).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_GEOJSON_PATH = _PROJECT_ROOT / "data" / "geo" / "kommuner.geojson"

# Basemap tiles.  CARTO now stamps an "API KEY REQUIRED" watermark onto tiles
# served from basemaps.cartocdn.com without credentials -- the request still
# returns HTTP 200, so the map defaces itself silently.  Esri's light grey
# canvas is served without credentials and matches the muted palette.
_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
)
_TILE_ATTRIBUTION = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
_TILE_MAX_ZOOM = 16

# Map viewport centred on Sweden
_MAP_CENTER = (63.0, 16.5)
_MAP_ZOOM_START = 5


# ---------------------------------------------------------------------------
# Map layers (METHODOLOGY §13.4)
# ---------------------------------------------------------------------------


def even_stops(vmin: float, vmax: float, n: int) -> list[float]:
    """Return n domain stops spread evenly from vmin to vmax.

    Args:
        vmin: First stop.
        vmax: Last stop.
        n: Number of stops, which must equal the number of colours.

    Returns:
        A strictly increasing list of n floats.
    """
    step = (vmax - vmin) / (n - 1)
    return [vmin + i * step for i in range(n)]


@dataclass(frozen=True)
class MapLayer:
    """One selectable choropleth layer.

    Attributes:
        key: Stable identifier used in code and tests.
        column: The column of the merged frame this layer colours by.
        label: Swedish radio-button label.
        colors: Colour ramp, low value first.
        stops: The domain value each colour is anchored at, one per colour,
            strictly increasing, running from vmin to vmax. Anchoring is what
            lets the neutral colour sit on the midpoint rather than halfway
            along the bar: the position ramp spans 80 to 130, so its midpoint
            of 100 falls two fifths of the way across, not at the centre.
        vmin: Value mapped to the first colour; values below are clipped.
        vmax: Value mapped to the last colour; values above are clipped.
        midpoint: The value the neutral colour sits on, and the value drawn
            for a kommun with no data. Every layer here has one, but they are
            not the same: a level is centred on riket = 100, a movement on
            zero. This used to be a diverging bool, which conflated "has a
            midpoint" with "that midpoint is zero", and so could not describe
            a level at all.
        signed: Whether the quantity carries a meaningful sign, so that the
            legend labels read +4 / 0 / -4 rather than 80 / 100 / 130.
        legend_ticks: Extra values to mark on the legend bar, beyond the two
            ends and the midpoint. Only for cuts a reader can act on: the
            position ramp marks the POSITION_BANDS cuts at 90 and 110, which
            are the same cuts the sidebar pills filter on. A drift ramp has
            none, because its inner stops are interpolation points and mean
            nothing on their own.
        legend_caption: Caption under the legend gradient.
        decimals: Digits shown in the tooltip.
    """

    key: str
    column: str
    label: str
    colors: list[str]
    stops: list[float]
    vmin: float
    vmax: float
    midpoint: float
    signed: bool
    legend_caption: str
    legend_ticks: tuple[float, ...] = ()
    decimals: int = 1


#: The two layers the plan specifies. Both diverge, but around different
#: midpoints and in different hues, and that separation is deliberate:
#: position is a level centred on riket = 100, drift is a signed movement
#: centred on zero. They must never share a palette, because a reader toggling
#: between them has to be able to tell which one is on screen. Neither ramp
#: ends in red and green, which would restate the retired vulnerability claim
#: that a low tax base is a high risk.
MAP_LAYERS: dict[str, MapLayer] = {
    "position": MapLayer(
        key="position",
        column="relative_position",
        label=SWEDISH_LABELS["map_layer_position"],
        colors=POSITION_SCALE,
        # Not evenly spaced. The domain is clipped to 80-130, which is not
        # symmetric about 100, so even spacing would drop the neutral colour
        # on 105 and paint every kommun between 100 and 105 as though it sat
        # below the national average. The inner stops fall on the
        # POSITION_BANDS cuts, so the map changes colour where the sidebar
        # pills change band.
        stops=[80.0, 90.0, 100.0, 110.0, 130.0],
        # Clipped to the body of the distribution: the median kommun sits at
        # 96.6 and the maximum at 208, so an unclipped ramp would render nine
        # kommuner in ten as one indistinguishable colour.
        vmin=80.0,
        vmax=130.0,
        midpoint=100.0,
        signed=False,
        legend_caption=SWEDISH_LABELS["map_legend_position"],
        legend_ticks=(90.0, 110.0),
    ),
    "drift": MapLayer(
        key="drift",
        column="drift_5y",
        label=SWEDISH_LABELS["map_layer_drift"],
        colors=DIVERGING_SCALE,
        # Symmetric about zero, so even spacing already puts the neutral
        # colour on the midpoint.
        stops=even_stops(-4.0, 4.0, len(DIVERGING_SCALE)),
        vmin=-4.0,
        vmax=4.0,
        midpoint=0.0,
        signed=True,
        legend_caption=SWEDISH_LABELS["map_legend_drift"],
    ),
}


def build_colormap(layer: MapLayer) -> cm.LinearColormap:
    """Return the branca colormap a layer paints with.

    The colours are anchored to layer.stops rather than stretched evenly
    across the domain, which is what puts the neutral colour on the midpoint.

    Args:
        layer: The layer to build a ramp for.

    Returns:
        A LinearColormap over [layer.vmin, layer.vmax].

    Raises:
        ValueError: If the layer's stops are not strictly increasing, or do
            not match its colours one for one. branca fails obscurely on both,
            so they are caught here.
    """
    if len(layer.stops) != len(layer.colors):
        raise ValueError(
            f"{layer.key}: {len(layer.stops)} stops for {len(layer.colors)} colours"
        )
    if any(b <= a for a, b in zip(layer.stops, layer.stops[1:])):
        raise ValueError(f"{layer.key}: stops must increase, got {layer.stops}")
    return cm.LinearColormap(
        colors=list(layer.colors),
        index=list(layer.stops),
        vmin=layer.vmin,
        vmax=layer.vmax,
        caption=layer.legend_caption,
    )


def color_for(
    layer: MapLayer,
    value: "float | None",
    colormap: "cm.LinearColormap | None" = None,
) -> str:
    """Return the colour a layer paints one value with.

    The single place a value becomes a colour, so that the map and any chart
    of the same quantity cannot drift apart. Values outside the layer's domain
    are clipped to its ends, and a missing value is drawn at the midpoint.

    Args:
        layer: The layer whose ramp to use.
        value: The value to colour. None and NaN are treated as missing.
        colormap: A ramp already built for this layer. Pass one when colouring
            many values, to avoid rebuilding it per value.

    Returns:
        A six-digit hex colour. branca returns eight digits, with an alpha
        byte these ramps never vary; Plotly does not accept that form, so the
        alpha is dropped here rather than at each call site.
    """
    cmap = colormap if colormap is not None else build_colormap(layer)
    if value is None or pd.isna(value):
        value = layer.midpoint
    clipped = max(layer.vmin, min(layer.vmax, float(value)))
    return cmap(clipped)[:7]


def resolve_layer(selection: str) -> MapLayer:
    """Return the layer named by a key or by its Swedish label.

    The radio widget hands back the label; code and tests use the key.

    Args:
        selection: Either a MAP_LAYERS key or a layer's Swedish label.

    Returns:
        The matching MapLayer.

    Raises:
        KeyError: If nothing matches.
    """
    if selection in MAP_LAYERS:
        return MAP_LAYERS[selection]
    for layer in MAP_LAYERS.values():
        if layer.label == selection:
            return layer
    raise KeyError(
        f"Okänt kartlager: {selection!r}. Giltiga lager: "
        + ", ".join(f"{k} ({v.label})" for k, v in MAP_LAYERS.items())
    )

# Tooltip field aliases (Swedish), in display order.  Every field is optional:
# which ones exist depends on what the caller merged in, and after T1.2 the
# position layers carry no vulnerability columns at all.
_TOOLTIP_ALIASES = {
    "kommun_name": SWEDISH_LABELS["th_kommun"],
    "position_fmt": SWEDISH_LABELS["position_index"],
    "scb_index_fmt": SWEDISH_LABELS["position_scb_index"],
    "drift_5y_fmt": SWEDISH_LABELS["drift_5y"],
    "drift_10y_fmt": SWEDISH_LABELS["drift_10y"],
    "tax_base_per_capita_fmt": SWEDISH_LABELS["th_skattekraft"],
    "unemployment_rate_fmt": SWEDISH_LABELS["th_unemployment"],
    "population_fmt": SWEDISH_LABELS["tooltip_population"],
}


def _format_tooltip_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add the formatted tooltip columns the frame has the inputs for.

    Args:
        df: Frame keyed by kommun_kod, carrying any subset of the source
            columns.

    Returns:
        The same frame with formatted `*_fmt` columns added where possible.
    """

    def _signed_points(value: float) -> str:
        return f"{value:+.1f}".replace(".", ",")

    formatters = {
        "position_fmt": ("relative_position", lambda v: f"{v:.1f}".replace(".", ",")),
        "scb_index_fmt": ("tax_base_index_riket", lambda v: f"{v:.0f}"),
        "drift_5y_fmt": ("drift_5y", _signed_points),
        "drift_10y_fmt": ("drift_10y", _signed_points),
        "tax_base_per_capita_fmt": ("tax_base_per_capita", format_sek),
        "unemployment_rate_fmt": ("unemployment_rate", format_pct),
        "population_fmt": (
            "population",
            lambda v: f"{int(v):,}".replace(",", " "),
        ),
    }

    for target, (source, fmt) in formatters.items():
        if source in df.columns:
            df[target] = df[source].apply(lambda v, f=fmt: "" if pd.isna(v) else f(v))

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_choropleth(
    data: pd.DataFrame,
    layer: "str | MapLayer" = "position",
    height: int = 480,
    key: str = "kss_choropleth",
) -> None:
    """Render an interactive Folium choropleth in Streamlit.

    The colour scale comes from the selected layer, and the layers do not share
    one: relative position is a level on a sequential ramp, and five-year
    drift is signed and centred on zero. See MAP_LAYERS.

    Args:
        data: DataFrame keyed by kommun_kod. It must carry the selected layer's
            column; every other column named in _TOOLTIP_ALIASES is optional and
            appears in the tooltip only when present.
        layer: A MAP_LAYERS key, a layer's Swedish label, or a MapLayer.
        height: Map height in pixels.
        key: Streamlit component key for st_folium.
    """
    map_layer = layer if isinstance(layer, MapLayer) else resolve_layer(layer)
    if not _GEOJSON_PATH.exists():
        st.warning(SWEDISH_LABELS["choropleth_missing_geojson"])
        return

    geojson = _load_geojson()

    # Build a lookup from kommun_kod to row data
    df = data.copy()
    df["kommun_kod"] = df["kommun_kod"].astype(str).str.zfill(4)

    # Format display columns for tooltips.  Which columns exist depends on the
    # layer the caller is showing, so each is formatted only when present.
    df = _format_tooltip_columns(df)

    lookup = df.set_index("kommun_kod").to_dict("index")

    # Build the ramp once and reuse it for all 290 polygons.
    colormap = build_colormap(map_layer)

    # Create base map centered on Sweden
    m = build_base_map()

    # Style function.  A kommun with no value for this layer is drawn at the
    # layer's midpoint by color_for, which is the only neutral a diverging
    # ramp has: painting it at the bottom of the ramp would assert that it
    # sits far below riket, which is a claim about missing data.
    def style_function(feature):
        kod = _extract_kommun_kod(feature)
        row = lookup.get(kod, {})
        return {
            "fillColor": color_for(map_layer, row.get(map_layer.column), colormap),
            # Not white.  Both ramps are near-white at the midpoint, and a
            # white stroke on that fill erases the border of every kommun
            # sitting close to riket, which is most of them.
            "color": "#C8CCD2",
            "weight": 0.5,
            "fillOpacity": 0.8,
        }

    # Highlight function
    def highlight_function(feature):
        return {
            "weight": 2,
            "color": COLORS["primary"],
            "fillOpacity": 0.9,
        }

    # Add GeoJSON layer with tooltips
    # Only the fields this frame actually carries: after the cutover the
    # position layers have no vulnerability columns, and an alias pointing at a
    # missing field renders as a blank row in every tooltip.
    present = [f for f in _TOOLTIP_ALIASES if f in df.columns]
    tooltip_fields = present
    tooltip_aliases = [_TOOLTIP_ALIASES[f] for f in present]

    # Inject data into GeoJSON properties for tooltips
    for feature in geojson["features"]:
        kod = _extract_kommun_kod(feature)
        row = lookup.get(kod, {})
        for field in tooltip_fields:
            feature["properties"][field] = row.get(field, "")

    folium.GeoJson(
        geojson,
        name="kommuner",
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=tooltip_aliases,
            localize=False,
            sticky=True,
            style=(
                "background-color: white; "
                "border: 1px solid #ccc; "
                "border-radius: 4px; "
                "padding: 8px 12px; "
                "font-family: Source Sans 3, sans-serif; "
                "font-size: 12px; "
                "color: #1A1A2E; "
                "box-shadow: 0 2px 6px rgba(0,0,0,0.15);"
            ),
        ),
    ).add_to(m)

    # Add responsive legend as custom HTML element
    legend_html = _build_responsive_legend(map_layer)
    m.get_root().html.add_child(folium.Element(legend_html))

    # Hide the selection rectangle that appears on click
    hide_selection_css = """
    <style>
        .leaflet-interactive:focus {
            outline: none !important;
        }
        .folium-map path.leaflet-interactive:focus {
            outline: none !important;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(hide_selection_css))

    # Render in Streamlit (feature_group_to_add=[] prevents selection rectangle)
    st_folium(
        m,
        height=height,
        use_container_width=True,
        key=key,
        returned_objects=[],
        feature_group_to_add=[],
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def build_base_map() -> folium.Map:
    """Create the empty Sweden-centred base map used by the choropleth.

    The tile layer is configured from an explicit URL template rather than a
    named folium provider so that the map cannot silently switch to a service
    that requires an API key.

    Returns:
        A folium.Map with the keyless basemap already attached.
    """
    return folium.Map(
        location=list(_MAP_CENTER),
        zoom_start=_MAP_ZOOM_START,
        tiles=_TILE_URL,
        attr=_TILE_ATTRIBUTION,
        max_zoom=_TILE_MAX_ZOOM,
        control_scale=False,
    )


def _build_responsive_legend(layer: MapLayer) -> str:
    """Build a responsive HTML legend that scales with map container width.

    Both the gradient and the tick labels are positioned by where a value
    actually falls in the domain, not by how many colours precede it. That
    matters because the position ramp spans 80 to 130 and is centred on 100:
    an evenly spaced bar would print 80 / 105 / 130 and put the neutral colour
    under the wrong number. The middle tick used to be a hardcoded "0", which
    was right while the only layer was a zero-centred z-score and wrong the
    moment a level scale arrived.

    Args:
        layer: The layer being drawn.

    Returns:
        HTML string for the legend element.
    """
    span = layer.vmax - layer.vmin

    def pct(value: float) -> float:
        """Where a domain value sits along the bar, 0 to 100."""
        return (value - layer.vmin) / span * 100.0

    fmt = "+.0f" if layer.signed else ".0f"

    def label_for(value: float) -> str:
        """Zero takes no sign, even on a signed scale: "+0" is not a reading."""
        return "0" if layer.signed and value == 0 else format(value, fmt)

    # Gradient stops placed at their own domain positions.
    gradient_stops = ", ".join(
        f"{c} {pct(v):.1f}%" for c, v in zip(layer.colors, layer.stops)
    )

    # Ticks over the bar: the midpoint reads solid, the band cuts faint.
    marks = f'<i class="kss-legend-mid" style="left:{pct(layer.midpoint):.1f}%"></i>'
    marks += "".join(
        f'<i style="left:{pct(t):.1f}%"></i>' for t in layer.legend_ticks
    )

    # Labels.  The ends are pinned to the ends of the bar so they cannot run
    # off it; everything between is centred on its own tick.
    labels = [
        f'<span class="kss-end" style="left:0">{label_for(layer.vmin)}</span>',
        f'<span class="kss-end" style="right:0">{label_for(layer.vmax)}</span>',
        f'<span class="kss-mid" style="left:{pct(layer.midpoint):.1f}%">'
        f'{label_for(layer.midpoint)}</span>',
    ]
    labels += [
        f'<span style="left:{pct(t):.1f}%">{label_for(t)}</span>'
        for t in layer.legend_ticks
    ]

    return f"""
    <style>
        .kss-legend-container {{
            position: absolute;
            top: 10px;
            left: 50px;
            right: 50px;
            z-index: 1000;
            pointer-events: none;
        }}
        .kss-legend {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 4px;
            padding: 6px 10px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.15);
            font-family: Source Sans 3, system-ui, sans-serif;
            font-size: 10px;
            max-width: 100%;
            box-sizing: border-box;
        }}
        .kss-legend-caption {{
            color: #1A1A2E;
            font-weight: 500;
            margin-bottom: 3px;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .kss-legend-bar {{
            position: relative;
            height: 8px;
            width: 100%;
            background: linear-gradient(to right, {gradient_stops});
            border-radius: 2px;
            margin-bottom: 3px;
        }}
        .kss-legend-bar i {{
            position: absolute;
            top: 0;
            bottom: 0;
            width: 1px;
            background: rgba(26, 26, 46, 0.25);
        }}
        .kss-legend-bar i.kss-legend-mid {{
            background: rgba(26, 26, 46, 0.55);
        }}
        .kss-legend-labels {{
            position: relative;
            height: 12px;
            color: #6B7280;
            font-size: 9px;
        }}
        .kss-legend-labels span {{
            position: absolute;
            top: 0;
            white-space: nowrap;
            transform: translateX(-50%);
        }}
        .kss-legend-labels span.kss-end {{
            transform: none;
        }}
        .kss-legend-labels span.kss-mid {{
            color: #1A1A2E;
            font-weight: 600;
        }}
    </style>
    <div class="kss-legend-container">
        <div class="kss-legend">
            <div class="kss-legend-caption">{layer.legend_caption}</div>
            <div class="kss-legend-bar">{marks}</div>
            <div class="kss-legend-labels">{"".join(labels)}</div>
        </div>
    </div>
    """


@st.cache_data
def _load_geojson() -> dict:
    """Load and cache the kommun GeoJSON file."""
    with open(_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _extract_kommun_kod(feature: dict) -> str:
    """Extract a 4-digit kommun code from a GeoJSON feature's properties.

    Handles various property naming conventions in Swedish GeoJSON files:
    'KnKod', 'kommun_kod', 'ref', 'KOD', 'id', or the feature's id field.

    Args:
        feature: A GeoJSON feature dict.

    Returns:
        4-digit zero-padded kommun code string.
    """
    props = feature.get("properties", {})

    # Try common property names
    for key in ("KnKod", "kommun_kod", "ref", "KOD", "id", "KNKOD", "knkod"):
        val = props.get(key)
        if val is not None:
            return str(val).zfill(4)

    # Fall back to feature id
    fid = feature.get("id", "")
    if fid:
        return str(fid).zfill(4)

    return "0000"
