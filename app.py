from __future__ import annotations

import base64
import importlib
from datetime import timedelta
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit_shadcn_ui as ui

import raw_availability_data as raw_availability_data_module
from asset_metadata import ASSET_METADATA_PATH
from availability_domain import (
    availability_domain_table_inventory,
    calculate_final_availability,
    build_contract_seed_view,
    build_discrepancy_events,
    build_export_pack_catalog,
    build_monthly_availability_seed,
    exclusions_template,
    export_final_availability_pack,
    parse_uploaded_exclusions,
    parse_uploaded_raw_availability,
    raw_upload_template,
    template_csv_bytes,
)
from availability_data import (
    aggregate_asset_availability,
    load_availability_data,
    weighted_availability,
)
from incident_data import INCIDENTS_PATH, load_incidents_data, normalize_site_name


raw_availability_data_module = importlib.reload(raw_availability_data_module)
GRANULARITY_OPTIONS = raw_availability_data_module.GRANULARITY_OPTIONS
SITE_LEVEL = raw_availability_data_module.SITE_LEVEL
load_daily_component_availability = raw_availability_data_module.load_daily_component_availability
raw_files = raw_availability_data_module.raw_files


alt.data_transformers.disable_max_rows()

st.set_page_config(
    page_title="BESS Availability Dashboard",
    page_icon=":zap:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


FILTER_LABELS = {
    "O&M": "om_provider",
    "PCS OEM": "pcs_oem",
    "ESS OEM": "ess_oem",
}

APP_BACKGROUND = "#FFF1E5"
LOGO_PATH = Path(r"C:\Users\g.mantinan\Downloads\gresham_house_logo.jpg")
ALL_SITES = "__ALL__"
DATE_PRESETS = ("Last month", "Last three months", "Mar-to-date", "Custom")
FORECAST_SCENARIOS = (99.0, 97.0, 95.0)
APP_VERSION_NAME = "v0.5.0"
APP_VERSION_RELEASED = "16 Jun 2026"
APP_VERSION_CHANGES = (
    "Local Git repository initialised for the AM Dashboard workspace.",
    "Availability module navigation added for portfolio, asset detail, and commercial views.",
    "Shadcn-style Streamlit KPI cards and status badges added to the dashboard shell.",
)
RAW_COMPONENT_CACHE_VERSION = "site-level-min-pcs-battery-v4-bradford-sources"
INCIDENT_CACHE_VERSION = "incidents-open-items-v1"
OUTAGE_THRESHOLD_PCT = 99.999
MAX_OUTAGE_SERIES = 20
MAX_AVERAGE_SERIES = 24


@st.cache_data(show_spinner="Loading raw availability data...")
def cached_availability_data(cache_version: str, raw_fingerprint: tuple[tuple[str, int, int], ...]) -> tuple[pd.DataFrame, str]:
    _ = (cache_version, raw_fingerprint)
    return load_availability_data()


@st.cache_data(show_spinner="Loading raw component availability data...")
def cached_daily_component_availability(
    cache_version: str,
    raw_fingerprint: tuple[tuple[str, int, int], ...],
) -> pd.DataFrame:
    _ = (cache_version, raw_fingerprint)
    return load_daily_component_availability()


@st.cache_data(show_spinner="Loading incidents data...")
def cached_incidents_data(cache_version: str, incident_fingerprint: tuple[str, int, int]) -> pd.DataFrame:
    _ = (cache_version, incident_fingerprint)
    return load_incidents_data()


def raw_data_fingerprint() -> tuple[tuple[str, int, int], ...]:
    files = []
    for path in raw_files():
        stat = path.stat()
        files.append((path.name, stat.st_size, stat.st_mtime_ns))
    if ASSET_METADATA_PATH.exists():
        stat = ASSET_METADATA_PATH.stat()
        files.append((f"asset-metadata:{ASSET_METADATA_PATH.name}", stat.st_size, stat.st_mtime_ns))
    return tuple(files)


def incidents_fingerprint() -> tuple[str, int, int]:
    if not INCIDENTS_PATH.exists():
        return (str(INCIDENTS_PATH), 0, 0)
    stat = INCIDENTS_PATH.stat()
    return (str(INCIDENTS_PATH), stat.st_size, stat.st_mtime_ns)


def version_badge_html() -> str:
    changes = "".join(f"<li>{escape(change)}</li>" for change in APP_VERSION_CHANGES)
    tooltip_title = "Released " + APP_VERSION_RELEASED + "\n" + "\n".join(f"- {change}" for change in APP_VERSION_CHANGES)
    return (
        f"<span class='version-badge' tabindex='0' title='{escape(tooltip_title, quote=True)}'>{escape(APP_VERSION_NAME)}"
        "<span class='version-tooltip'>"
        f"<div class='version-tooltip-title'>Released {escape(APP_VERSION_RELEASED)}</div>"
        f"<ul>{changes}</ul>"
        "</span>"
        "</span>"
    )


def render_context_badges(source_name: str, max_timestamp: pd.Timestamp) -> None:
    ui.badges(
        badge_list=[
            (APP_VERSION_NAME, "secondary"),
            (source_name, "outline"),
            (f"Updated {max_timestamp:%d %b %Y %H:%M}", "outline"),
        ],
        class_name="dashboard-context-badges",
        key="dashboard_context_badges",
    )


def render_availability_metric_card(title: str, value: float | None, delta: str | None, key: str) -> None:
    description = delta or "No prior comparison"
    ui.metric_card(
        title=title,
        content=format_pct(value),
        description=description,
        key=key,
    )


def brand_header_html(source_name: str, max_timestamp: pd.Timestamp) -> str:
    logo = ""
    if LOGO_PATH.exists():
        encoded_logo = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        logo = f"<img class='brand-mark' src='data:image/jpeg;base64,{encoded_logo}' alt='Gresham House logo'>"

    return (
        "<div class='brand-header'>"
        f"{logo}"
        "<div class='brand-copy'>"
        "<div class='title-line'>"
        "<h1>BESS Availability</h1>"
        f"{version_badge_html()}"
        "</div>"
        "<div class='timestamp'>Availability command centre for portfolio, asset, and commercial views.</div>"
        "</div>"
        "</div>"
    )


def mar_to_date_label_html() -> str:
    return (
        "<span class='mar-to-date-label' "
        "title='Earlier data is not available yet. This view starts from the first available March 2026 data point.'>"
        "Mar-to-date"
        "</span>"
    )


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --page-bg: #FFF1E5;
            --card-bg: #fff8f2;
            --card-bg-strong: #fffbf7;
            --ink: #172026;
            --muted: #667085;
            --border: #d9cbbf;
            --good: #16815d;
            --warn: #c77b16;
            --danger: #c3423f;
            --accent: #2a7f7f;
            --accent-soft: rgba(42, 127, 127, 0.11);
            --soft: #FFF1E5;
        }

        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stHeader"],
        [data-testid="stMain"],
        section.stMain {
            background: var(--page-bg);
        }

        .block-container {
            max-width: 1280px;
            padding-top: 0.7rem;
            padding-bottom: 2.4rem;
        }

        h1, h2, h3, p {
            letter-spacing: 0;
        }

        div[data-testid="stMarkdownContainer"] p {
            line-height: 1.45;
        }

        .brand-header {
            align-items: center;
            display: flex;
            gap: 1rem;
            min-height: 70px;
        }

        .brand-mark {
            aspect-ratio: 1;
            border-radius: 4px;
            display: block;
            flex: 0 0 64px;
            height: 64px;
            object-fit: cover;
            width: 64px;
        }

        .brand-copy {
            display: flex;
            flex-direction: column;
            gap: 0.18rem;
            min-width: 0;
        }

        .title-line {
            align-items: baseline;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
        }

        .title-line h1 {
            color: var(--ink);
            font-size: 2rem;
            line-height: 1.05;
            margin: 0;
        }

        .version-badge {
            background: rgba(23, 32, 38, 0.06);
            border: 1px solid var(--border);
            border-radius: 999px;
            color: var(--ink);
            cursor: default;
            display: inline-flex;
            font-size: 0.78rem;
            font-weight: 650;
            line-height: 1;
            padding: 0.38rem 0.55rem;
            position: relative;
        }

        .version-tooltip {
            background: #172026;
            border-radius: 8px;
            box-shadow: 0 14px 30px rgba(23, 32, 38, 0.2);
            color: #fff;
            display: none;
            font-size: 0.78rem;
            font-weight: 400;
            left: 0;
            line-height: 1.4;
            min-width: 280px;
            padding: 0.75rem 0.85rem;
            position: absolute;
            top: 1.95rem;
            z-index: 20;
        }

        .version-badge:hover .version-tooltip,
        .version-badge:focus .version-tooltip,
        .version-badge:focus-within .version-tooltip {
            display: block !important;
        }

        .version-tooltip-title {
            font-weight: 700;
            margin-bottom: 0.35rem;
        }

        .version-tooltip ul {
            margin: 0;
            padding-left: 1rem;
        }

        div[data-testid="stMetric"] {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-top: 3px solid var(--accent);
            border-radius: 8px;
            padding: 1rem 1rem 0.85rem;
            box-shadow: 0 12px 28px rgba(23, 32, 38, 0.055);
        }

        div[data-testid="stMetricLabel"] {
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }

        div[data-testid="stMetricValue"] {
            color: var(--ink);
            font-size: 1.9rem;
            font-weight: 720;
            line-height: 1.1;
        }

        div[data-testid="stMetricDelta"] {
            font-size: 0.78rem;
        }

        .section-title {
            align-items: center;
            color: var(--ink);
            display: flex;
            font-size: 1rem;
            font-weight: 720;
            gap: 0.55rem;
            margin: 1.2rem 0 0.45rem;
        }

        .section-title::before {
            background: var(--accent);
            border-radius: 999px;
            content: "";
            display: inline-block;
            height: 0.62rem;
            width: 0.62rem;
        }

        .timestamp {
            color: var(--muted);
            font-size: 0.82rem;
            margin-top: 0;
        }

        .filter-spacer {
            height: 0;
        }

        div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.top-banner-marker) + div[data-testid="stLayoutWrapper"] {
            backdrop-filter: blur(8px);
            background: rgba(255, 248, 242, 0.96);
            border: 1px solid var(--border);
            border-radius: 8px;
            box-shadow: 0 10px 24px rgba(23, 32, 38, 0.055);
            margin-bottom: 0.9rem;
            padding: 0.55rem 0.75rem;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .control-caption {
            color: var(--muted);
            font-size: 0.78rem;
            margin-top: -0.25rem;
        }

        .period-label {
            color: var(--ink);
            font-size: 0.875rem;
            font-weight: 400;
            line-height: 1.35;
            margin-bottom: 0.35rem;
        }

        .period-box {
            align-items: center;
            background: var(--card-bg-strong);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--ink);
            display: flex;
            font-size: 0.92rem;
            min-height: 2.45rem;
            padding: 0 0.75rem;
        }

        .mar-to-date-label {
            border-bottom: 1px dotted var(--muted);
            cursor: help;
            font-weight: 650;
        }

        .forecast-note {
            color: var(--muted);
            font-size: 0.82rem;
            margin: -0.15rem 0 0.55rem;
        }

        div[data-testid="stTextInput"] input:disabled {
            color: var(--ink);
            opacity: 1;
        }

        div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] [data-baseweb="select"] > div,
        div[data-testid="stDateInput"] input {
            background: var(--card-bg-strong);
            border-color: var(--border);
            border-radius: 8px;
        }

        div[data-testid="stTabs"] {
            margin-top: 1rem;
        }

        div[data-testid="stTabs"] [role="tablist"] {
            background: rgba(255, 248, 242, 0.74);
            border: 1px solid var(--border);
            border-radius: 8px;
            gap: 0.25rem;
            padding: 0.25rem;
        }

        div[data-testid="stTabs"] [role="tab"] {
            border-radius: 6px;
            color: var(--muted);
            min-height: 2.35rem;
            padding: 0.35rem 0.9rem;
        }

        div[data-testid="stTabs"] [role="tab"] p {
            font-size: 0.9rem;
            font-weight: 700;
        }

        div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
            background: var(--ink);
            color: #fff;
        }

        div[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {
            color: #fff;
        }

        .stPlotlyChart,
        div[data-testid="stVegaLiteChart"] {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.45rem;
            box-shadow: 0 10px 24px rgba(23, 32, 38, 0.045);
        }

        div[data-testid="stDataFrame"] {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            box-shadow: 0 10px 24px rgba(23, 32, 38, 0.04);
            padding: 0.25rem;
        }

        .insights-panel {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            box-shadow: 0 10px 24px rgba(23, 32, 38, 0.045);
            border-left: 4px solid var(--accent);
            padding: 0.95rem 1rem;
        }

        .insights-panel ul {
            margin: 0;
            padding-left: 1.1rem;
        }

        .insights-panel li {
            margin: 0.35rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    legend_hover_rules = [
        ".js-plotly-plot:has(.legend .traces:hover) .scatterlayer .trace { opacity: 0.18; filter: saturate(0.25); }"
    ]
    for index in range(1, 241):
        legend_hover_rules.append(
            ".js-plotly-plot:has(.legend .traces:nth-child("
            f"{index}"
            "):hover) .scatterlayer .trace:nth-child("
            f"{index}"
            ") { opacity: 1; filter: none; }"
        )
    st.markdown(f"<style>{''.join(legend_hover_rules)}</style>", unsafe_allow_html=True)


def format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:.1f}%"


def availability_delta(current: float | None, previous: float | None) -> str | None:
    if current is None or previous is None or pd.isna(current) or pd.isna(previous):
        return None
    return f"{current - previous:+.1f} pts vs prior period"


def period_metric(df: pd.DataFrame, end: pd.Timestamp, hours: int | None = None, days: int | None = None) -> tuple[float, float]:
    if hours is not None:
        start = end - timedelta(hours=hours)
    elif days is not None:
        start = end - timedelta(days=days)
    else:
        raise ValueError("Provide hours or days")

    current = df[(df["timestamp"] > start) & (df["timestamp"] <= end)]
    duration = end - start
    previous_start = start - duration
    previous = df[(df["timestamp"] > previous_start) & (df["timestamp"] <= start)]
    return weighted_availability(current), weighted_availability(previous)


def build_asset_chart(asset_summary: pd.DataFrame) -> go.Figure:
    max_marker_size = 52
    sizeref = 2.0 * asset_summary["mw"].max() / (max_marker_size**2)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=asset_summary["asset_name"],
            y=asset_summary["availability_pct"],
            mode="markers",
            marker=dict(
                size=asset_summary["mw"],
                sizemode="area",
                sizeref=sizeref,
                sizemin=12,
                color=asset_summary["availability_pct"],
                colorscale=[
                    [0.0, "#c3423f"],
                    [0.55, "#d9a441"],
                    [0.78, "#5aa469"],
                    [1.0, "#16815d"],
                ],
                cmin=85,
                cmax=100,
                line=dict(width=1.4, color="#172026"),
                colorbar=dict(title="Availability", ticksuffix="%"),
            ),
            customdata=asset_summary[["mw", "om_provider", "pcs_oem", "ess_oem"]],
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Availability %{y:.1f}%<br>"
                "Capacity %{customdata[0]:.1f} MW<br>"
                "O&M %{customdata[1]}<br>"
                "PCS OEM %{customdata[2]}<br>"
                "ESS OEM %{customdata[3]}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=95, line_width=1, line_dash="dot", line_color="#9aa4b2")
    fig.update_layout(
        height=430,
        margin=dict(l=20, r=20, t=20, b=70),
        plot_bgcolor=APP_BACKGROUND,
        paper_bgcolor=APP_BACKGROUND,
        yaxis=dict(title="", ticksuffix="%", range=[80, 100.5], gridcolor="#e0d1c5"),
        xaxis=dict(title="", tickangle=-25, showgrid=False),
        font=dict(family="Inter, Segoe UI, sans-serif", color="#172026"),
    )
    return fig


def build_component_timeseries_chart(component_daily: pd.DataFrame, title: str) -> alt.Chart:
    chart_data = component_daily.copy()
    chart_data = add_series_labels(chart_data)
    chart_data["availability_label"] = chart_data["availability_pct"].map(lambda value: f"{value:.1f}%")

    drill = alt.selection_point(
        name="drill",
        fields=["site_id", "asset_name", "level", "component_id", "component_label", "parent_id", "drill_level"],
        on="click",
        nearest=True,
        empty=False,
    )
    legend_focus = alt.selection_point(
        name="legend_focus",
        fields=["series_label"],
        bind="legend",
        on="mouseover",
        clear="mouseout",
        empty=True,
    )

    base = alt.Chart(chart_data).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0)),
        y=alt.Y(
            "availability_pct:Q",
            title="Availability (%)",
            scale=alt.Scale(domain=[0, 100]),
            axis=alt.Axis(
                format=".0f",
                labelExpr="format(datum.value, '.0f') + '%'",
                titleAngle=0,
                titleAlign="left",
                titleBaseline="bottom",
                titlePadding=10,
                titleX=0,
                titleY=-10,
            ),
        ),
        color=alt.Color(
            "series_label:N",
            title=None,
            legend=alt.Legend(orient="top", columns=6, symbolType="stroke"),
        ),
        opacity=alt.condition(legend_focus, alt.value(1), alt.value(0.16)),
        tooltip=[
            alt.Tooltip("asset_name:N", title="Site"),
            alt.Tooltip("component_label:N", title="Component"),
            alt.Tooltip("date:T", title="Date", format="%d %b %Y"),
            alt.Tooltip("availability_label:N", title="Availability"),
        ],
    )

    line = base.mark_line(point=alt.OverlayMarkDef(filled=True, size=45), strokeWidth=2.2)
    selectors = base.mark_point(size=180, opacity=0.001).add_params(drill)

    return (
        (line + selectors)
        .add_params(legend_focus)
        .properties(height=420, title=alt.TitleParams(text=title, anchor="start", fontSize=15))
        .configure(background=APP_BACKGROUND)
        .configure_view(stroke="#d9cbbf")
        .configure_axis(gridColor="#e0d1c5", labelColor="#172026", titleColor="#172026")
        .configure_legend(labelColor="#172026", titleColor="#172026", symbolLimit=0)
    )


def add_series_labels(df: pd.DataFrame) -> pd.DataFrame:
    labelled = df.copy()
    labelled["series_label"] = labelled["component_label"].astype(str)
    multiple_sites = labelled["site_id"].nunique() > 1
    is_site_level = labelled["level"].eq(SITE_LEVEL).all()
    if multiple_sites and not is_site_level:
        labelled["series_label"] = labelled["asset_name"].astype(str) + " | " + labelled["component_label"].astype(str)
    return labelled


def selected_chart_point(event: object) -> dict | None:
    if not event:
        return None

    selection = event.get("selection", {}) if isinstance(event, dict) else getattr(event, "selection", {})
    drill_selection = selection.get("drill", []) if isinstance(selection, dict) else getattr(selection, "drill", [])
    if isinstance(drill_selection, list) and drill_selection:
        return drill_selection[0]
    if isinstance(drill_selection, dict):
        return drill_selection
    return None


def calculate_outage_metrics(chart_data: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "site_id",
        "asset_name",
        "level",
        "component_id",
        "component_label",
        "series_label",
        "mean_availability_pct",
        "lowest_availability_pct",
        "outage_count",
        "outage_days",
        "mean_outage_duration_days",
        "observed_days",
    ]
    if chart_data.empty:
        return pd.DataFrame(columns=columns)

    labelled = add_series_labels(chart_data)
    rows: list[dict[str, object]] = []
    group_columns = ["site_id", "asset_name", "level", "component_id", "component_label", "series_label"]

    for group_values, series in labelled.groupby(group_columns, dropna=False):
        site_id, asset_name, level, component_id, component_label, series_label = group_values
        series = series.sort_values("date")
        durations: list[int] = []
        current_duration = 0
        in_outage = False
        previous_date: pd.Timestamp | None = None

        for row in series.itertuples(index=False):
            current_date = pd.Timestamp(row.date).normalize()
            is_outage = float(row.availability_pct) < OUTAGE_THRESHOLD_PCT
            date_gap = (current_date - previous_date).days if previous_date is not None else 1

            if is_outage:
                if in_outage and date_gap <= 1:
                    current_duration += 1
                else:
                    if in_outage:
                        durations.append(current_duration)
                    current_duration = 1
                    in_outage = True
            elif in_outage:
                durations.append(current_duration)
                current_duration = 0
                in_outage = False

            previous_date = current_date

        if in_outage:
            durations.append(current_duration)

        outage_count = len(durations)
        outage_days = int((series["availability_pct"] < OUTAGE_THRESHOLD_PCT).sum())
        rows.append(
            {
                "site_id": site_id,
                "asset_name": asset_name,
                "level": level,
                "component_id": component_id,
                "component_label": component_label,
                "series_label": series_label,
                "mean_availability_pct": series["availability_pct"].mean(),
                "lowest_availability_pct": series["availability_pct"].min(),
                "outage_count": outage_count,
                "outage_days": outage_days,
                "mean_outage_duration_days": sum(durations) / outage_count if outage_count else 0.0,
                "observed_days": series["date"].nunique(),
            }
        )

    return pd.DataFrame(rows, columns=columns)


def build_outage_chart(outage_metrics: pd.DataFrame, title: str) -> alt.Chart:
    sort_order = outage_metrics["series_label"].tolist()
    outage_metrics = outage_metrics.copy()
    outage_metrics["mean_outage_label"] = outage_metrics["mean_outage_duration_days"].map(lambda value: f"{value:.1f} days")
    outage_metrics["availability_label"] = outage_metrics["mean_availability_pct"].map(lambda value: f"{value:.1f}%")

    base = alt.Chart(outage_metrics).encode(
        x=alt.X(
            "series_label:N",
            title=None,
            sort=sort_order,
            axis=alt.Axis(labelAngle=-35, labelLimit=120),
        ),
        tooltip=[
            alt.Tooltip("series_label:N", title="Series"),
            alt.Tooltip("mean_outage_label:N", title="Mean outage duration"),
            alt.Tooltip("outage_count:Q", title="Outages", format=".0f"),
            alt.Tooltip("outage_days:Q", title="Outage days", format=".0f"),
            alt.Tooltip("availability_label:N", title="Mean availability"),
        ],
    )

    bars = base.mark_bar(color="#3a7ca5", cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        y=alt.Y(
            "mean_outage_duration_days:Q",
            title="Mean outage duration (days)",
            axis=alt.Axis(format=".1f"),
        )
    )
    dots = base.mark_circle(color="#c3423f", size=85, opacity=0.9).encode(
        y=alt.Y(
            "outage_count:Q",
            title="Number of outages",
            axis=alt.Axis(format=".0f"),
        )
    )

    return (
        alt.layer(bars, dots)
        .resolve_scale(y="independent")
        .properties(height=330, title=alt.TitleParams(text=title, anchor="start", fontSize=15))
        .configure(background=APP_BACKGROUND)
        .configure_view(stroke="#d9cbbf")
        .configure_axis(gridColor="#e0d1c5", labelColor="#172026", titleColor="#172026")
    )


def render_outage_analysis(chart_data: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    st.markdown("<div class='section-title'>Outage Duration and Frequency</div>", unsafe_allow_html=True)
    outage_metrics = calculate_outage_metrics(chart_data)
    if outage_metrics.empty:
        st.info("No outage metrics are available for the selected view.")
        return outage_metrics

    sorted_metrics = outage_metrics.sort_values(
        ["outage_count", "mean_outage_duration_days", "lowest_availability_pct"],
        ascending=[False, False, True],
    )
    chart_metrics = sorted_metrics[sorted_metrics["outage_count"] > 0].head(MAX_OUTAGE_SERIES)
    period_title = f"{start_date:%d %b %Y} to {end_date:%d %b %Y}"

    if chart_metrics.empty:
        st.info(f"No outage events were detected between {period_title}.")
    else:
        st.altair_chart(
            build_outage_chart(chart_metrics, f"Outage profile | {period_title}"),
            width="stretch",
        )

    table = sorted_metrics.rename(
        columns={
            "series_label": "Series",
            "mean_availability_pct": "Mean availability",
            "lowest_availability_pct": "Lowest availability",
            "outage_count": "Outages",
            "outage_days": "Outage days",
            "mean_outage_duration_days": "Mean outage duration",
            "observed_days": "Observed days",
        }
    )
    st.dataframe(
        table[
            [
                "Series",
                "Mean availability",
                "Lowest availability",
                "Outages",
                "Outage days",
                "Mean outage duration",
                "Observed days",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Mean availability": st.column_config.NumberColumn(format="%.1f%%"),
            "Lowest availability": st.column_config.NumberColumn(format="%.1f%%"),
            "Outages": st.column_config.NumberColumn(format="%d"),
            "Outage days": st.column_config.NumberColumn(format="%d"),
            "Mean outage duration": st.column_config.NumberColumn(format="%.1f days"),
            "Observed days": st.column_config.NumberColumn(format="%d"),
        },
    )
    return outage_metrics


def calculate_average_availability_metrics(chart_data: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "series_label",
        "asset_name",
        "level",
        "mean_availability_pct",
        "lowest_availability_pct",
        "observed_days",
    ]
    if chart_data.empty:
        return pd.DataFrame(columns=columns)

    labelled = add_series_labels(chart_data)
    metrics = (
        labelled.groupby(["series_label", "asset_name", "level"], as_index=False)
        .agg(
            mean_availability_pct=("availability_pct", "mean"),
            lowest_availability_pct=("availability_pct", "min"),
            observed_days=("date", "nunique"),
        )
        .sort_values("mean_availability_pct")
        .reset_index(drop=True)
    )
    return metrics[columns]


def build_average_availability_chart(metrics: pd.DataFrame, title: str) -> go.Figure:
    chart_data = metrics.sort_values("mean_availability_pct", ascending=True).head(MAX_AVERAGE_SERIES)
    colors = [
        "#c3423f" if value < 95 else "#c77b16" if value < 99 else "#16815d"
        for value in chart_data["mean_availability_pct"]
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart_data["mean_availability_pct"],
            y=chart_data["series_label"],
            orientation="h",
            marker=dict(color=colors, line=dict(color="#172026", width=0.6)),
            customdata=chart_data[["lowest_availability_pct", "observed_days"]],
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Average %{x:.1f}%<br>"
                "Lowest day %{customdata[0]:.1f}%<br>"
                "Observed days %{customdata[1]:.0f}<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=95, line_width=1.4, line_dash="dot", line_color="#c77b16", annotation_text="95%")
    fig.add_vline(x=99, line_width=1.4, line_dash="dot", line_color="#16815d", annotation_text="99%")
    x_min = max(0, min(90, float(chart_data["mean_availability_pct"].min()) - 2))
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)),
        height=max(330, min(620, 52 + 28 * len(chart_data))),
        margin=dict(l=20, r=30, t=44, b=35),
        plot_bgcolor=APP_BACKGROUND,
        paper_bgcolor=APP_BACKGROUND,
        xaxis=dict(title="", ticksuffix="%", range=[x_min, 100.5], gridcolor="#e0d1c5"),
        yaxis=dict(title="", automargin=True),
        showlegend=False,
        font=dict(family="Inter, Segoe UI, sans-serif", color="#172026"),
    )
    return fig


def render_average_availability_analysis(chart_data: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    st.markdown("<div class='section-title'>Average Availability</div>", unsafe_allow_html=True)
    metrics = calculate_average_availability_metrics(chart_data)
    if metrics.empty:
        st.info("No average availability data is available for the selected view.")
        return metrics

    period_title = f"{start_date:%d %b %Y} to {end_date:%d %b %Y}"
    st.plotly_chart(
        build_average_availability_chart(metrics, f"Average availability | {period_title}"),
        width="stretch",
        config={"displayModeBar": False},
    )

    table = metrics.rename(
        columns={
            "series_label": "Series",
            "mean_availability_pct": "Mean availability",
            "lowest_availability_pct": "Lowest day",
            "observed_days": "Observed days",
        }
    )
    st.dataframe(
        table[["Series", "Mean availability", "Lowest day", "Observed days"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Mean availability": st.column_config.NumberColumn(format="%.1f%%"),
            "Lowest day": st.column_config.NumberColumn(format="%.1f%%"),
            "Observed days": st.column_config.NumberColumn(format="%d"),
        },
    )
    return metrics


def render_insights(chart_data: pd.DataFrame, availability_metrics: pd.DataFrame) -> None:
    st.markdown("<div class='section-title'>Insights</div>", unsafe_allow_html=True)
    insights = build_insights(chart_data, availability_metrics)
    items = "".join(f"<li>{escape(insight)}</li>" for insight in insights)
    st.markdown(f"<div class='insights-panel'><ul>{items}</ul></div>", unsafe_allow_html=True)


def build_insights(chart_data: pd.DataFrame, availability_metrics: pd.DataFrame) -> list[str]:
    if chart_data.empty:
        return ["No data is available for the selected view."]

    if availability_metrics.empty:
        return ["No average availability metrics are available for the selected view."]

    lowest = availability_metrics.sort_values("mean_availability_pct").iloc[0]
    below_95 = availability_metrics[availability_metrics["mean_availability_pct"] < 95]
    below_99 = availability_metrics[availability_metrics["mean_availability_pct"] < 99]
    insights = [
        f"Lowest average availability in this view is {lowest.series_label} at {lowest.mean_availability_pct:.1f}%.",
    ]
    if below_95.empty:
        insights.append("No selected series is below the 95% benchmark for this timeframe.")
    else:
        insights.append(f"{len(below_95)} selected series sit below the 95% benchmark.")
    if not below_99.empty:
        insights.append(f"{len(below_99)} selected series sit below the 99% stretch benchmark.")

    insights.append("The open-items root-case breakdown below can be used to qualify these availability patterns.")
    return insights


def render_asset_detail_module(
    df: pd.DataFrame,
    component_daily: pd.DataFrame | None,
    max_timestamp: pd.Timestamp,
) -> None:
    st.markdown("<div class='section-title'>Asset Detail</div>", unsafe_allow_html=True)
    assets = (
        df[["asset_id", "asset_name"]]
        .drop_duplicates()
        .sort_values("asset_name")
        .reset_index(drop=True)
    )
    if assets.empty:
        st.info("No asset data is available for the current filter.")
        return

    asset_options = assets["asset_id"].tolist()
    asset_labels = dict(zip(assets["asset_id"], assets["asset_name"], strict=False))
    selected_asset_id = st.selectbox(
        "Asset",
        asset_options,
        format_func=lambda asset_id: asset_labels.get(asset_id, asset_id),
        key="asset_detail_asset",
    )

    asset_df = df[df["asset_id"] == selected_asset_id].copy()
    if asset_df.empty:
        st.warning("No measurements are available for the selected asset.")
        return

    asset_name = asset_labels.get(selected_asset_id, selected_asset_id)
    last_24h, _ = period_metric(asset_df, max_timestamp, hours=24)
    last_month, _ = period_metric(asset_df, max_timestamp, days=30)
    mw = asset_df["mw"].dropna().max()
    om_provider = _first_value(asset_df["om_provider"])

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Capacity", f"{mw:.1f} MW" if pd.notna(mw) else "n/a")
    metric_2.metric("Last 24 hours", format_pct(last_24h))
    metric_3.metric("Last month", format_pct(last_month))
    metric_4.metric("O&M", om_provider)

    asset_daily = (
        asset_df.assign(date=asset_df["timestamp"].dt.floor("D"))
        .groupby("date", as_index=False)
        .agg(availability_pct=("availability_pct", "mean"))
        .sort_values("date")
    )
    if not asset_daily.empty:
        st.plotly_chart(
            build_asset_detail_chart(asset_daily, f"{asset_name} daily availability"),
            width="stretch",
            config={"displayModeBar": False},
        )

    if component_daily is None or component_daily.empty:
        st.info("No device-level availability is available for this asset.")
        return

    cutoff_date = pd.Timestamp(max_timestamp).floor("D") - pd.Timedelta(days=30)
    device_data = component_daily[
        (component_daily["site_id"] == selected_asset_id)
        & (pd.to_datetime(component_daily["date"]) >= cutoff_date)
        & (component_daily["level"] != SITE_LEVEL)
    ].copy()
    if device_data.empty:
        st.info("No device-level rows are available for the selected asset and period.")
        return

    device_metrics = (
        device_data.groupby(["level", "component_label"], as_index=False)
        .agg(
            mean_availability_pct=("availability_pct", "mean"),
            lowest_day_pct=("availability_pct", "min"),
            observed_days=("date", "nunique"),
        )
        .sort_values(["mean_availability_pct", "level", "component_label"])
    )
    device_metrics = device_metrics.rename(
        columns={
            "level": "Granularity",
            "component_label": "Component",
            "mean_availability_pct": "Mean availability",
            "lowest_day_pct": "Lowest day",
            "observed_days": "Observed days",
        }
    )
    st.dataframe(
        device_metrics[["Granularity", "Component", "Mean availability", "Lowest day", "Observed days"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Mean availability": st.column_config.NumberColumn(format="%.1f%%"),
            "Lowest day": st.column_config.NumberColumn(format="%.1f%%"),
            "Observed days": st.column_config.NumberColumn(format="%d"),
        },
    )


def build_asset_detail_chart(asset_daily: pd.DataFrame, title: str) -> go.Figure:
    y_min = max(0, min(90, float(asset_daily["availability_pct"].min()) - 2))
    fig = go.Figure(
        go.Scatter(
            x=asset_daily["date"],
            y=asset_daily["availability_pct"],
            mode="lines+markers",
            line=dict(color="#2a7f7f", width=2.4),
            marker=dict(size=6),
            hovertemplate="%{x|%d %b %Y}<br>Availability %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_hline(y=95, line_width=1.4, line_dash="dot", line_color="#c77b16", annotation_text="95%")
    fig.update_layout(
        height=330,
        margin=dict(l=54, r=24, t=48, b=42),
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)),
        plot_bgcolor=APP_BACKGROUND,
        paper_bgcolor=APP_BACKGROUND,
        xaxis=dict(title="", gridcolor="#eadbd0"),
        yaxis=dict(title="Availability (%)", ticksuffix="%", range=[y_min, 100.5], gridcolor="#e0d1c5"),
        font=dict(family="Inter, Segoe UI, sans-serif", color="#172026"),
    )
    return fig


def render_final_availability_workbench(df: pd.DataFrame) -> None:
    st.markdown("<div class='section-title'>Final Availability Workbench</div>", unsafe_allow_html=True)

    template_col, upload_col = st.columns([0.34, 0.66])
    with template_col:
        st.download_button(
            "Raw template",
            data=template_csv_bytes(raw_upload_template()),
            file_name="raw_availability_template.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Exclusions template",
            data=template_csv_bytes(exclusions_template()),
            file_name="availability_exclusions_template.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with upload_col:
        raw_files_uploaded = st.file_uploader(
            "Raw availability files",
            type=["csv", "xlsx", "xlsm"],
            accept_multiple_files=True,
            key="final_availability_raw_uploads",
        )
        exclusions_file = st.file_uploader(
            "Exclusions register",
            type=["csv", "xlsx", "xlsm"],
            key="final_availability_exclusions_upload",
        )

    threshold_pct = st.number_input(
        "Contract availability threshold",
        min_value=0.0,
        max_value=100.0,
        value=95.0,
        step=0.1,
        format="%.1f",
        key="final_availability_threshold",
    )
    use_current_data = st.checkbox(
        "Use current dashboard data",
        value=False,
        key="final_availability_use_current_data",
    )

    if raw_files_uploaded:
        raw_upload, raw_messages = parse_uploaded_raw_availability(raw_files_uploaded, df)
    elif use_current_data:
        raw_upload = df.copy()
        raw_upload["source_file"] = "Current dashboard data"
        raw_messages = []
    else:
        st.info("Upload raw availability data or use the current dashboard data to calculate final availability.")
        return

    for message in raw_messages:
        st.warning(message)
    if raw_upload.empty:
        st.warning("No usable raw availability rows are available.")
        return

    exclusions, exclusion_messages = parse_uploaded_exclusions(exclusions_file, raw_upload)
    for message in exclusion_messages:
        st.warning(message)

    final_result = calculate_final_availability(raw_upload, exclusions, threshold_pct)
    contract_position = final_result["contract_position"]
    portfolio_position = contract_position[contract_position["asset_id"].eq("PORTFOLIO")]
    summary_row = portfolio_position.iloc[0] if not portfolio_position.empty else contract_position.iloc[0]

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    with metric_1:
        ui.metric_card(
            title="Gross availability",
            content=format_pct(summary_row.gross_availability_pct),
            description="Before uploaded exclusions",
            key="final_gross_availability_card",
        )
    with metric_2:
        ui.metric_card(
            title="Final availability",
            content=format_pct(summary_row.final_availability_pct),
            description="After uploaded exclusions",
            key="final_net_availability_card",
        )
    with metric_3:
        ui.metric_card(
            title="Excluded intervals",
            content=f"{int(summary_row.excluded_intervals):,}",
            description=f"{int(summary_row.excluded_days):,} excluded days",
            key="final_excluded_intervals_card",
        )
    with metric_4:
        ui.metric_card(
            title="Discrepancy events",
            content=f"{len(final_result['discrepancy_events']):,}",
            description=f"Below {threshold_pct:.1f}% threshold",
            key="final_discrepancy_events_card",
        )

    display_position = contract_position.rename(
        columns={
            "asset_name": "Asset",
            "gross_availability_pct": "Gross availability",
            "final_availability_pct": "Final availability",
            "availability_delta_pct": "Delta",
            "observed_intervals": "Observed intervals",
            "excluded_intervals": "Excluded intervals",
            "retained_intervals": "Retained intervals",
            "excluded_days": "Excluded days",
            "period_start": "Period start",
            "period_end": "Period end",
        }
    )
    st.dataframe(
        display_position[
            [
                "Asset",
                "Gross availability",
                "Final availability",
                "Delta",
                "Observed intervals",
                "Excluded intervals",
                "Retained intervals",
                "Excluded days",
                "Period start",
                "Period end",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Gross availability": st.column_config.NumberColumn(format="%.2f%%"),
            "Final availability": st.column_config.NumberColumn(format="%.2f%%"),
            "Delta": st.column_config.NumberColumn(format="%+.2f pts"),
            "Observed intervals": st.column_config.NumberColumn(format="%d"),
            "Excluded intervals": st.column_config.NumberColumn(format="%d"),
            "Retained intervals": st.column_config.NumberColumn(format="%d"),
            "Excluded days": st.column_config.NumberColumn(format="%d"),
        },
    )

    export_bytes = export_final_availability_pack(final_result)
    st.download_button(
        "Download final availability pack",
        data=export_bytes,
        file_name="final_availability_pack.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    detail_col, event_col = st.columns([0.52, 0.48])
    with detail_col:
        st.markdown("<div class='section-title'>Exclusions Register</div>", unsafe_allow_html=True)
        if final_result["exclusions_register"].empty:
            st.info("No exclusions have been applied.")
        else:
            st.dataframe(final_result["exclusions_register"], hide_index=True, use_container_width=True)
    with event_col:
        st.markdown("<div class='section-title'>Final Availability Events</div>", unsafe_allow_html=True)
        if final_result["discrepancy_events"].empty:
            st.info("No final availability discrepancy events were detected.")
        else:
            st.dataframe(
                final_result["discrepancy_events"].head(25),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "threshold_pct": st.column_config.NumberColumn(format="%.1f%%"),
                    "mean_final_availability_pct": st.column_config.NumberColumn(format="%.1f%%"),
                    "lowest_final_availability_pct": st.column_config.NumberColumn(format="%.1f%%"),
                    "availability_impact_mw_days": st.column_config.NumberColumn(format="%.2f"),
                },
            )


def render_commercial_om_module(df: pd.DataFrame, component_daily: pd.DataFrame | None) -> None:
    st.markdown("<div class='section-title'>Commercial / O&M Contract Management</div>", unsafe_allow_html=True)

    render_final_availability_workbench(df)

    component_source = component_daily if component_daily is not None else pd.DataFrame()
    contract_seed = build_contract_seed_view(df)
    monthly_seed = build_monthly_availability_seed(component_source, df)
    discrepancy_events = build_discrepancy_events(component_source, df)
    export_catalog = build_export_pack_catalog()

    try:
        table_inventory = availability_domain_table_inventory()
        schema_count = len(table_inventory)
    except OSError as exc:
        table_inventory = pd.DataFrame(columns=["entity", "table_name", "rows"])
        schema_count = 0
        st.warning(f"Could not initialise the availability data model: {exc}")

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Seed contracts", f"{len(contract_seed):,}")
    metric_2.metric("Discrepancy events", f"{len(discrepancy_events):,}")
    metric_3.metric("Data entities", f"{schema_count:,}")
    metric_4.metric("Export packs", f"{len(export_catalog):,}")

    if not contract_seed.empty:
        contract_table = contract_seed.rename(
            columns={
                "asset_name": "Asset",
                "mw": "MW",
                "om_provider": "O&M",
                "pcs_oem": "PCS OEM",
                "ess_oem": "ESS OEM",
                "contract_year": "Contract year",
                "availability_threshold_pct": "Threshold",
                "status": "Status",
            }
        )
        st.dataframe(
            contract_table[["Asset", "MW", "O&M", "PCS OEM", "ESS OEM", "Contract year", "Threshold", "Status"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "MW": st.column_config.NumberColumn(format="%.1f"),
                "Threshold": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    left_col, right_col = st.columns([0.58, 0.42])
    with left_col:
        st.markdown("<div class='section-title'>Discrepancy Events</div>", unsafe_allow_html=True)
        if discrepancy_events.empty:
            st.info("No seeded discrepancy events are available for the current filter.")
        else:
            event_table = discrepancy_events.rename(
                columns={
                    "asset_name": "Asset",
                    "start_date": "Start",
                    "end_date": "End",
                    "duration_days": "Days",
                    "threshold_pct": "Threshold",
                    "mean_availability_pct": "Mean availability",
                    "lowest_availability_pct": "Lowest availability",
                    "availability_impact_mw_days": "Impact MW-days",
                    "status": "Status",
                }
            )
            st.dataframe(
                event_table[
                    [
                        "Asset",
                        "Start",
                        "End",
                        "Days",
                        "Threshold",
                        "Mean availability",
                        "Lowest availability",
                        "Impact MW-days",
                        "Status",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Threshold": st.column_config.NumberColumn(format="%.1f%%"),
                    "Mean availability": st.column_config.NumberColumn(format="%.1f%%"),
                    "Lowest availability": st.column_config.NumberColumn(format="%.1f%%"),
                    "Impact MW-days": st.column_config.NumberColumn(format="%.2f"),
                },
            )

    with right_col:
        st.markdown("<div class='section-title'>Monthly Availability Seed</div>", unsafe_allow_html=True)
        if monthly_seed.empty:
            st.info("No seeded monthly availability is available for the current filter.")
        else:
            monthly_table = monthly_seed.rename(
                columns={
                    "asset_name": "Asset",
                    "month": "Month",
                    "availability_pct": "Availability",
                    "lowest_day_pct": "Lowest day",
                    "observed_days": "Days",
                    "mw": "MW",
                }
            )
            st.dataframe(
                monthly_table[["Asset", "Month", "Availability", "Lowest day", "Days", "MW"]],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Availability": st.column_config.NumberColumn(format="%.1f%%"),
                    "Lowest day": st.column_config.NumberColumn(format="%.1f%%"),
                    "MW": st.column_config.NumberColumn(format="%.1f"),
                },
            )

    export_col, schema_col = st.columns([0.42, 0.58])
    with export_col:
        st.markdown("<div class='section-title'>Export Packs</div>", unsafe_allow_html=True)
        st.dataframe(export_catalog, hide_index=True, use_container_width=True)

    with schema_col:
        st.markdown("<div class='section-title'>Data Model</div>", unsafe_allow_html=True)
        st.dataframe(table_inventory, hide_index=True, use_container_width=True)


def _first_value(series: pd.Series) -> str:
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    return values.iloc[0] if not values.empty else "Unknown"


def daily_availability_for_forecast(df: pd.DataFrame, raw_context: dict[str, object]) -> tuple[pd.DataFrame, str]:
    site_filter = raw_context.get("site_filter")
    working = df.dropna(subset=["timestamp", "availability_pct", "mw"]).copy()
    if site_filter != ALL_SITES:
        working = working[working["asset_id"] == site_filter]

    if working.empty:
        return pd.DataFrame(columns=["date", "availability_pct"]), "Selected site"

    working["date"] = working["timestamp"].dt.floor("D")
    site_daily = (
        working.groupby(["date", "asset_id", "asset_name"], as_index=False)
        .agg(availability_pct=("availability_pct", "mean"), mw=("mw", "max"))
        .dropna(subset=["availability_pct", "mw"])
    )
    if site_daily.empty:
        return pd.DataFrame(columns=["date", "availability_pct"]), "Selected site"

    if site_filter == ALL_SITES:
        site_daily["weighted_availability"] = site_daily["availability_pct"] * site_daily["mw"]
        daily = (
            site_daily.groupby("date", as_index=False)
            .agg(weighted_availability=("weighted_availability", "sum"), mw_weight=("mw", "sum"))
            .sort_values("date")
        )
        daily["availability_pct"] = daily["weighted_availability"] / daily["mw_weight"]
        return daily[["date", "availability_pct"]], "Portfolio (MW weighted)"

    scope_label = site_daily["asset_name"].iloc[0]
    daily = (
        site_daily.groupby("date", as_index=False)["availability_pct"]
        .mean()
        .sort_values("date")
        .reset_index(drop=True)
    )
    return daily, scope_label


def build_forecast_data(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if daily.empty:
        return pd.DataFrame(), pd.DataFrame()

    daily = daily.sort_values("date").reset_index(drop=True)
    actual_days = len(daily)
    actual_sum = daily["availability_pct"].sum()
    actual_average = actual_sum / actual_days
    latest_date = pd.Timestamp(daily["date"].max())
    year_end = pd.Timestamp(year=latest_date.year, month=12, day=31)
    future_dates = pd.date_range(latest_date + pd.Timedelta(days=1), year_end, freq="D")
    remaining_days = len(future_dates)

    actual = daily.copy()
    actual["availability_pct"] = actual["availability_pct"].expanding().mean()
    actual["series"] = "Actual Mar-to-date"
    actual["line_type"] = "Actual"

    rows = []
    summary_rows = []
    for scenario in FORECAST_SCENARIOS:
        scenario_label = f"Future {scenario:.0f}%"
        rows.append(
            {
                "date": latest_date,
                "availability_pct": actual_average,
                "series": scenario_label,
                "line_type": "Scenario",
            }
        )
        for index, date in enumerate(future_dates, start=1):
            forecast_value = (actual_sum + scenario * index) / (actual_days + index)
            rows.append(
                {
                    "date": date,
                    "availability_pct": forecast_value,
                    "series": scenario_label,
                    "line_type": "Scenario",
                }
            )

        final_availability = (
            (actual_sum + scenario * remaining_days) / (actual_days + remaining_days)
            if remaining_days
            else actual_average
        )
        summary_rows.append(
            {
                "scenario": scenario_label,
                "actual_days": actual_days,
                "remaining_days": remaining_days,
                "actual_average_pct": actual_average,
                "future_availability_pct": scenario,
                "final_availability_pct": final_availability,
            }
        )

    line_data = pd.concat([actual, pd.DataFrame(rows)], ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    return line_data, summary


def build_forecast_line_chart(line_data: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    colors = {
        "Actual Mar-to-date": "#172026",
        "Future 99%": "#16815d",
        "Future 97%": "#3a7ca5",
        "Future 95%": "#c77b16",
    }

    for series, data in line_data.groupby("series", sort=False):
        is_actual = series == "Actual Mar-to-date"
        fig.add_trace(
            go.Scatter(
                x=data["date"],
                y=data["availability_pct"],
                mode="lines",
                name=series,
                line=dict(
                    color=colors.get(series, "#667085"),
                    width=3 if is_actual else 2.5,
                    dash="solid" if is_actual else "dash",
                ),
                hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
            )
        )

    y_min = max(0, min(90, float(line_data["availability_pct"].min()) - 1.5))
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)),
        height=450,
        margin=dict(l=20, r=25, t=52, b=86),
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.22, x=0, xanchor="left", yanchor="top"),
        plot_bgcolor=APP_BACKGROUND,
        paper_bgcolor=APP_BACKGROUND,
        yaxis=dict(title="", ticksuffix="%", range=[y_min, 100.5], gridcolor="#e0d1c5"),
        xaxis=dict(title="", showgrid=False),
        font=dict(family="Inter, Segoe UI, sans-serif", color="#172026"),
    )
    return fig


def build_forecast_days_chart(summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    y = summary["scenario"]
    actual_text = summary["actual_days"].map(lambda days: f"{int(days)} actual days")
    future_text = summary.apply(
        lambda row: f"{int(row.remaining_days)} days @ {row.future_availability_pct:.0f}%",
        axis=1,
    )

    fig.add_trace(
        go.Bar(
            y=y,
            x=summary["actual_days"],
            orientation="h",
            name="Actual Mar-to-date",
            marker_color="#667085",
            text=actual_text,
            textposition="inside",
            hovertemplate="Actual days %{x:.0f}<br>Average %{customdata:.2f}%<extra></extra>",
            customdata=summary["actual_average_pct"],
        )
    )
    fig.add_trace(
        go.Bar(
            y=y,
            x=summary["remaining_days"],
            orientation="h",
            name="Future scenario",
            marker_color=["#16815d", "#3a7ca5", "#c77b16"],
            text=future_text,
            textposition="inside",
            hovertemplate=(
                "Remaining days %{x:.0f}<br>"
                "Future availability %{customdata[0]:.0f}%<br>"
                "Forecast final %{customdata[1]:.2f}%<extra></extra>"
            ),
            customdata=summary[["future_availability_pct", "final_availability_pct"]],
        )
    )

    total_days = summary["actual_days"] + summary["remaining_days"]
    for _, row in summary.iterrows():
        fig.add_annotation(
            x=row["actual_days"] + row["remaining_days"],
            y=row["scenario"],
            text=f"Final {row['final_availability_pct']:.2f}%",
            xanchor="left",
            showarrow=False,
            font=dict(size=12, color="#172026"),
        )

    fig.update_layout(
        title=dict(text="Days at availability scenarios", x=0, xanchor="left", font=dict(size=15)),
        height=330,
        margin=dict(l=20, r=104, t=52, b=78),
        barmode="stack",
        plot_bgcolor=APP_BACKGROUND,
        paper_bgcolor=APP_BACKGROUND,
        xaxis=dict(title="Days", range=[0, float(total_days.max()) * 1.18], gridcolor="#e0d1c5"),
        yaxis=dict(title="", autorange="reversed"),
        legend=dict(orientation="h", y=-0.26, x=0, xanchor="left", yanchor="top"),
        font=dict(family="Inter, Segoe UI, sans-serif", color="#172026"),
    )
    return fig


def render_forecast_section(df: pd.DataFrame, raw_context: dict[str, object]) -> pd.DataFrame:
    daily, scope_label = daily_availability_for_forecast(df, raw_context)
    st.markdown(
        f"<div class='section-title'>End-of-year availability forecast ({mar_to_date_label_html()})</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='forecast-note'>Scenario forecast uses observed availability from the first available March 2026 data point through the latest data date, then projects to 31 Dec 2026.</div>",
        unsafe_allow_html=True,
    )

    if daily.empty:
        st.info("No site-level availability data is available for the selected forecast scope.")
        return pd.DataFrame()

    line_data, summary = build_forecast_data(daily)
    if line_data.empty or summary.empty:
        st.info("Not enough data is available to build the forecast.")
        return summary

    chart_col, days_col = st.columns([0.62, 0.38], vertical_alignment="top")
    with chart_col:
        st.plotly_chart(
            build_forecast_line_chart(line_data, f"Forecast cumulative availability | {scope_label}"),
            width="stretch",
            config={"displayModeBar": False},
        )
    with days_col:
        st.plotly_chart(
            build_forecast_days_chart(summary),
            width="stretch",
            config={"displayModeBar": False},
        )

    summary_table = summary.rename(
        columns={
            "scenario": "Scenario",
            "actual_days": "Actual days",
            "remaining_days": "Remaining days",
            "actual_average_pct": "Mar-to-date average",
            "future_availability_pct": "Future availability",
            "final_availability_pct": "Forecast final availability",
        }
    )
    display_table = summary_table[
        [
            "Scenario",
            "Actual days",
            "Remaining days",
            "Mar-to-date average",
            "Future availability",
            "Forecast final availability",
        ]
    ].copy()
    display_table["Actual days"] = display_table["Actual days"].map(lambda value: f"{int(value)}")
    display_table["Remaining days"] = display_table["Remaining days"].map(lambda value: f"{int(value)}")
    display_table["Mar-to-date average"] = display_table["Mar-to-date average"].map(lambda value: f"{value:.2f}%")
    display_table["Future availability"] = display_table["Future availability"].map(lambda value: f"{value:.0f}%")
    display_table["Forecast final availability"] = display_table["Forecast final availability"].map(lambda value: f"{value:.2f}%")
    st.table(display_table)

    return summary


def filter_incidents_for_context(incidents: pd.DataFrame, raw_context: dict[str, object]) -> tuple[pd.DataFrame, str]:
    site_filter = raw_context.get("site_filter")
    if site_filter == ALL_SITES:
        return incidents.copy(), "All sites"

    chart_data = raw_context.get("chart_data")
    if isinstance(chart_data, pd.DataFrame) and not chart_data.empty:
        selected_site = str(chart_data["asset_name"].iloc[0])
    else:
        selected_site = str(site_filter)

    selected_key = normalize_site_name(selected_site)
    filtered = incidents[incidents["site_key"] == selected_key].copy()
    return filtered, selected_site


def build_root_cause_donut(incidents: pd.DataFrame, title: str, *, expanded: bool = False) -> go.Figure:
    summary = (
        incidents.groupby("Root cause", as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values("count", ascending=False)
    )

    fig = go.Figure()
    fig.add_trace(
        go.Pie(
            labels=summary["Root cause"],
            values=summary["count"],
            hole=0.58,
            sort=False,
            direction="clockwise",
            marker=dict(
                colors=[
                    "#3a7ca5",
                    "#16815d",
                    "#c77b16",
                    "#c3423f",
                    "#5b5f97",
                    "#2f7f7f",
                    "#8a6f3d",
                    "#667085",
                ],
                line=dict(color=APP_BACKGROUND, width=2),
            ),
            textinfo="label+percent" if expanded else "percent",
            textposition="inside" if not expanded else "auto",
            hovertemplate="<b>%{label}</b><br>Open items %{value}<br>%{percent}<extra></extra>",
        )
    )
    legend = (
        dict(orientation="v", y=0.5, yanchor="middle", x=1.02, xanchor="left")
        if expanded
        else dict(orientation="h", y=-0.08, yanchor="top", x=0.5, xanchor="center")
    )
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)),
        height=540 if expanded else 390,
        margin=dict(l=10, r=120 if expanded else 10, t=42, b=74 if not expanded else 20),
        showlegend=True,
        legend=legend,
        paper_bgcolor=APP_BACKGROUND,
        plot_bgcolor=APP_BACKGROUND,
        font=dict(family="Inter, Segoe UI, sans-serif", color="#172026"),
    )
    fig.add_annotation(
        text=f"{len(incidents)}<br>open items",
        x=0.5,
        y=0.5,
        font=dict(size=18, color="#172026"),
        showarrow=False,
    )
    return fig


def render_incidents_section(incidents: pd.DataFrame, raw_context: dict[str, object]) -> None:
    scoped_incidents, scope_label = filter_incidents_for_context(incidents, raw_context)
    title_col, expand_col = st.columns([0.78, 0.22], vertical_alignment="center")
    title_col.markdown("<div class='section-title'>Root-case breakdown</div>", unsafe_allow_html=True)
    expanded = expand_col.toggle("Expand chart", key="root_case_expand_chart")

    if scoped_incidents.empty:
        st.info(f"No incidents are available for {scope_label}.")
        return

    display = scoped_incidents[
        ["Site", "Equipment", "Root cause", "Corrective Plans", "Comments", "Long term plan"]
    ].sort_values(["Site", "Root cause", "Equipment"])

    if expanded:
        st.plotly_chart(
            build_root_cause_donut(scoped_incidents, f"Root-case breakdown | {scope_label}", expanded=True),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            height=380,
            column_config={
                "Site": st.column_config.TextColumn(width="small"),
                "Equipment": st.column_config.TextColumn(width="medium"),
                "Root cause": st.column_config.TextColumn(width="medium"),
                "Corrective Plans": st.column_config.TextColumn(width="large"),
                "Comments": st.column_config.TextColumn(width="large"),
                "Long term plan": st.column_config.TextColumn(width="large"),
            },
        )
        return

    chart_col, table_col = st.columns([0.46, 0.54], vertical_alignment="top")
    with chart_col:
        st.plotly_chart(
            build_root_cause_donut(scoped_incidents, f"Root-case breakdown | {scope_label}"),
            width="stretch",
            config={"displayModeBar": False},
        )
    with table_col:
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            height=390,
            column_config={
                "Site": st.column_config.TextColumn(width="small"),
                "Equipment": st.column_config.TextColumn(width="medium"),
                "Root cause": st.column_config.TextColumn(width="medium"),
                "Corrective Plans": st.column_config.TextColumn(width="large"),
                "Comments": st.column_config.TextColumn(width="large"),
                "Long term plan": st.column_config.TextColumn(width="large"),
            },
        )


def component_parent_options(component_daily: pd.DataFrame, level: str) -> pd.DataFrame:
    site_filter = st.session_state.get("raw_site_select", ALL_SITES)
    filtered = component_daily[component_daily["level"] == level]
    if site_filter != ALL_SITES:
        filtered = filtered[filtered["site_id"] == site_filter]

    parents = (
        filtered[["site_id", "asset_name", "parent_id"]]
        .drop_duplicates()
        .sort_values(["asset_name", "parent_id"])
        .reset_index(drop=True)
    )
    parents["parent_key"] = parents["site_id"] + "|" + parents["parent_id"]
    parents["parent_label"] = parents["parent_id"].apply(_parent_label)
    if site_filter == ALL_SITES:
        parents["parent_label"] = parents["asset_name"] + " | " + parents["parent_label"]
    return parents


def render_raw_availability_timeseries(component_daily: pd.DataFrame) -> dict[str, object] | None:
    st.markdown("<div class='section-title'>Raw Availability Time Series</div>", unsafe_allow_html=True)

    pending_drill = st.session_state.pop("raw_pending_drill", None)
    if pending_drill:
        st.session_state.raw_selected_granularity = pending_drill["granularity"]
        st.session_state.raw_site_select = pending_drill["site_id"]
        st.session_state.raw_parent_key = pending_drill["parent_key"]
        st.session_state.raw_drill_label = pending_drill["label"]
        st.session_state.raw_last_drill_signature = pending_drill["signature"]
        st.session_state.raw_device_granularity_select = pending_drill["granularity"]

    if "raw_selected_granularity" not in st.session_state:
        st.session_state.raw_selected_granularity = "PCS"
    if "raw_device_granularity_select" not in st.session_state:
        st.session_state.raw_device_granularity_select = "PCS"
    if "raw_site_select" not in st.session_state:
        st.session_state.raw_site_select = ALL_SITES
    if "raw_parent_key" not in st.session_state:
        st.session_state.raw_parent_key = None
    if "raw_drill_label" not in st.session_state:
        st.session_state.raw_drill_label = None
    if st.session_state.get("raw_date_preset_select") == "YTD":
        st.session_state.raw_date_preset_select = "Mar-to-date"

    min_date = component_daily["date"].min().date()
    max_date = component_daily["date"].max().date()
    default_start = max(min_date, (pd.Timestamp(max_date) - pd.DateOffset(months=1) + pd.DateOffset(days=1)).date())

    sites = component_daily[["site_id", "asset_name"]].drop_duplicates().sort_values("asset_name")
    site_options = [ALL_SITES, *sites["site_id"].tolist()]
    site_labels = {ALL_SITES: "All sites"}
    for site in sites.itertuples(index=False):
        site_labels[site.site_id] = site.asset_name

    control_1, control_2, control_3, control_4 = st.columns([0.22, 0.22, 0.22, 0.34], vertical_alignment="bottom")
    with control_1:
        st.selectbox(
            "Site",
            site_options,
            key="raw_site_select",
            format_func=lambda option: site_labels.get(option, option),
        )
    with control_2:
        site_filter = st.session_state.raw_site_select
        if site_filter == ALL_SITES:
            granularity = st.selectbox(
                "Granularity",
                (SITE_LEVEL,),
                key="raw_site_granularity_select",
            )
            st.session_state.raw_parent_key = None
            st.session_state.raw_drill_label = None
            st.session_state.raw_last_drill_signature = None
        else:
            granularity = st.selectbox(
                "Granularity",
                GRANULARITY_OPTIONS,
                key="raw_device_granularity_select",
            )
        st.session_state.raw_selected_granularity = granularity
    with control_3:
        date_preset = st.selectbox(
            "Timeframe",
            DATE_PRESETS,
            key="raw_date_preset_select",
        )
    with control_4:
        if date_preset == "Custom":
            selected_dates = st.date_input(
                "Period",
                value=(default_start, max_date),
                min_value=min_date,
                max_value=max_date,
                key="raw_custom_date_range",
            )
        else:
            selected_dates = quick_date_range(date_preset, min_date, max_date)
            st.markdown(
                "<div class='period-label'>Period</div>"
                f"<div class='period-box'>{selected_dates[0]:%d %b %Y} - {selected_dates[1]:%d %b %Y}</div>",
                unsafe_allow_html=True,
            )

    parent_key = None
    if granularity == "PCS-module":
        parents = component_parent_options(component_daily, "PCS-module")
        parent_key = _parent_selectbox(parents, "PCS")
    elif granularity == "Battery rack":
        parents = component_parent_options(component_daily, "Battery rack")
        parent_key = _parent_selectbox(parents, "Battery system")

    if st.session_state.raw_drill_label:
        drill_col, back_col = st.columns([0.82, 0.18], vertical_alignment="center")
        drill_col.caption(f"Drilled into {st.session_state.raw_drill_label}")
        if back_col.button("Back", key="raw_back", use_container_width=True):
            st.session_state.raw_pending_drill = {
                "granularity": "Battery system" if granularity == "Battery rack" else "PCS",
                "site_id": st.session_state.raw_site_select,
                "parent_key": None,
                "label": None,
                "signature": None,
            }
            st.rerun()

    if not isinstance(selected_dates, (tuple, list)) or len(selected_dates) != 2:
        st.info("Select a start and end date.")
        return None

    start_date, end_date = selected_dates
    chart_data = component_daily[
        (component_daily["level"] == granularity)
        & (component_daily["date"].dt.date >= start_date)
        & (component_daily["date"].dt.date <= end_date)
    ].copy()

    site_filter = st.session_state.raw_site_select
    if site_filter != ALL_SITES:
        chart_data = chart_data[chart_data["site_id"] == site_filter]

    if parent_key:
        parent_site_id, parent_id = parse_parent_key(parent_key)
        chart_data = chart_data[(chart_data["site_id"] == parent_site_id) & (chart_data["parent_id"] == parent_id)]

    if chart_data.empty:
        st.warning("No raw availability data matches the selected view.")
        return None

    chart_title = granularity
    if parent_key:
        parent_site_id, parent_id = parse_parent_key(parent_key)
        parent_label = _parent_label(parent_id)
        if site_filter == ALL_SITES:
            site_name = chart_data["asset_name"].iloc[0] if not chart_data.empty else parent_site_id
            parent_label = f"{site_name} | {parent_label}"
        chart_title = f"{granularity} under {parent_label}"

    event = st.altair_chart(
        build_component_timeseries_chart(chart_data, chart_title),
        width="stretch",
        key="raw_availability_timeseries",
        on_select="rerun",
        selection_mode="drill",
    )

    context = {
        "chart_data": chart_data,
        "granularity": granularity,
        "start_date": start_date,
        "end_date": end_date,
        "site_filter": site_filter,
        "parent_key": parent_key,
        "chart_title": chart_title,
    }

    point = selected_chart_point(event)
    if not point:
        return context

    site_id = point.get("site_id")
    asset_name = point.get("asset_name")
    level = point.get("level")
    component_id = point.get("component_id")
    component_label = point.get("component_label")
    drill_level = point.get("drill_level")
    if not drill_level or pd.isna(drill_level):
        return context

    signature = f"{site_id}|{level}|{component_id}"
    if signature == st.session_state.get("raw_last_drill_signature"):
        return context

    st.session_state.raw_pending_drill = {
        "granularity": drill_level,
        "site_id": site_id,
        "parent_key": f"{site_id}|{component_id}",
        "label": f"{asset_name} | {component_label}",
        "signature": signature,
    }
    st.rerun()
    return context


def _parent_selectbox(parents: pd.DataFrame, label: str) -> str:
    if parents.empty:
        st.caption(f"No {label.lower()} parent is available for this site.")
        return ""

    options = parents["parent_key"].tolist()
    labels = dict(zip(parents["parent_key"], parents["parent_label"], strict=False))
    current_parent = st.session_state.get("raw_parent_key")
    index = options.index(current_parent) if current_parent in options else 0
    widget_key = f"raw_parent_{label}"
    if current_parent not in options:
        st.session_state.raw_parent_key = options[index]
        st.session_state[widget_key] = options[index]

    selected = st.selectbox(
        label,
        options,
        index=index,
        format_func=lambda option: labels.get(option, option),
        key=widget_key,
    )
    st.session_state.raw_parent_key = selected
    return selected


def _parent_label(parent_id: str) -> str:
    return parent_id.replace("BATTERY-", "Battery system ")


def parse_parent_key(parent_key: str) -> tuple[str, str]:
    site_id, parent_id = parent_key.split("|", 1)
    return site_id, parent_id


def quick_date_range(preset: str, min_date, max_date) -> tuple:
    max_ts = pd.Timestamp(max_date)

    if preset == "Last month":
        start = (max_ts - pd.DateOffset(months=1) + pd.DateOffset(days=1)).date()
    elif preset == "Last three months":
        start = (max_ts - pd.DateOffset(months=3) + pd.DateOffset(days=1)).date()
    elif preset == "Mar-to-date":
        start = min_date
    else:
        start = min_date

    return max(start, min_date), max_date


def apply_filter(df: pd.DataFrame, filter_type: str, selected_values: list[str]) -> pd.DataFrame:
    column = FILTER_LABELS[filter_type]
    if not selected_values:
        return df.iloc[0:0]
    return df[df[column].isin(selected_values)]


def main() -> None:
    inject_styles()

    raw_fingerprint = raw_data_fingerprint()
    df, source_name = cached_availability_data(RAW_COMPONENT_CACHE_VERSION, raw_fingerprint)
    max_timestamp = df["timestamp"].max()

    st.markdown("<div class='top-banner-marker'></div>", unsafe_allow_html=True)
    title_col, filter_col = st.columns([0.78, 0.22], vertical_alignment="center")
    with title_col:
        st.markdown(brand_header_html(source_name, max_timestamp), unsafe_allow_html=True)
        render_context_badges(source_name, max_timestamp)

    with filter_col:
        with st.popover("Filter by", use_container_width=True):
            filter_type = st.radio(
                "Filter dimension",
                list(FILTER_LABELS.keys()),
                horizontal=False,
            )
            filter_column = FILTER_LABELS[filter_type]
            options = sorted(df[filter_column].dropna().unique().tolist())
            selected_values = st.multiselect(
                "Values",
                options,
                default=options,
            )

    filtered_df = apply_filter(df, filter_type, selected_values)

    if filtered_df.empty:
        st.warning("No assets match the selected filter.")
        return

    last_3h, prior_3h = period_metric(filtered_df, max_timestamp, hours=3)
    last_24h, prior_24h = period_metric(filtered_df, max_timestamp, hours=24)
    last_month, prior_month = period_metric(filtered_df, max_timestamp, days=30)

    card_1, card_2, card_3 = st.columns(3)
    with card_1:
        render_availability_metric_card(
            "Last 3 hours",
            last_3h,
            availability_delta(last_3h, prior_3h),
            "availability_metric_last_3h",
        )
    with card_2:
        render_availability_metric_card(
            "Last 24 hours",
            last_24h,
            availability_delta(last_24h, prior_24h),
            "availability_metric_last_24h",
        )
    with card_3:
        render_availability_metric_card(
            "Last month",
            last_month,
            availability_delta(last_month, prior_month),
            "availability_metric_last_month",
        )

    component_daily = None
    component_load_error = None
    try:
        component_daily = cached_daily_component_availability(RAW_COMPONENT_CACHE_VERSION, raw_fingerprint)
    except FileNotFoundError as exc:
        component_load_error = str(exc)

    portfolio_tab, asset_detail_tab, commercial_tab = st.tabs(
        ["Portfolio Availability", "Asset Detail", "Commercial / O&M Contract Management"]
    )

    with portfolio_tab:
        raw_context = None
        if component_load_error:
            st.warning(component_load_error)
        elif component_daily is not None:
            raw_context = render_raw_availability_timeseries(component_daily)

        if raw_context:
            render_forecast_section(filtered_df, raw_context)
            availability_metrics = render_average_availability_analysis(
                raw_context["chart_data"],
                raw_context["start_date"],
                raw_context["end_date"],
            )
            render_insights(raw_context["chart_data"], availability_metrics)
            try:
                render_incidents_section(
                    cached_incidents_data(INCIDENT_CACHE_VERSION, incidents_fingerprint()),
                    raw_context,
                )
            except (FileNotFoundError, ValueError) as exc:
                st.warning(str(exc))

        st.markdown("<div class='section-title'>Asset Availability and Capacity</div>", unsafe_allow_html=True)
        lookback_start = max_timestamp - timedelta(hours=24)
        recent = filtered_df[filtered_df["timestamp"] > lookback_start]
        asset_summary = aggregate_asset_availability(recent)
        st.plotly_chart(build_asset_chart(asset_summary), width="stretch", config={"displayModeBar": False})

    with asset_detail_tab:
        render_asset_detail_module(filtered_df, component_daily, max_timestamp)

    with commercial_tab:
        render_commercial_om_module(filtered_df, component_daily)


if __name__ == "__main__":
    main()
