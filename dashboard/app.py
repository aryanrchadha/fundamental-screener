"""Plotly Dash dashboard for the composite fundamental screener.

Run with:  python -m dashboard.app   (after screener.backtest + validation)
Serves on http://localhost:8050.

Reads the parquet/CSV artifacts written by the pipeline — it performs no
computation of its own, so what you see is exactly what was validated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dash_table, dcc, html

import config
from screener.universes import get_universe


def load_data(universe="sp500"):
    """Load whatever artifacts this universe actually has.

    A screener-only universe (India) has a scores panel but no return
    series, validation table or rolling spread, because no backtest is run
    for it. Those come back as None and the views that depend on them are
    replaced by an explanation rather than an empty or fabricated chart.
    """
    uni = get_universe(universe) if isinstance(universe, str) else universe
    panel = pd.read_parquet(uni.panel_path)

    def _maybe(path, reader):
        return reader(path) if Path(path).exists() else None

    dec = _maybe(uni.bucket_returns_path, pd.read_parquet)
    summary = _maybe(uni.validation_path, lambda p: pd.read_csv(p, index_col=0))
    roll = _maybe(uni.rolling_path, pd.read_parquet)
    return panel, dec, summary, roll


def latest_cross_section(panel: pd.DataFrame) -> pd.DataFrame:
    last = panel["as_of_date"].max()
    cols = ["ticker", "sector", "f_score", "z_score", "o_score", "composite_score", "decile"]
    xsec = panel[panel["as_of_date"] == last][cols].dropna(subset=["composite_score"])
    return xsec.round(3).sort_values("composite_score", ascending=False)


def fig_sector_heatmap(panel: pd.DataFrame) -> go.Figure:
    df = panel.dropna(subset=["composite_score", "sector"]).copy()
    df["year"] = pd.to_datetime(df["as_of_date"]).dt.year
    grid = df.pivot_table(index="sector", columns="year", values="composite_score", aggfunc="mean")
    fig = px.imshow(grid, aspect="auto", color_continuous_scale="RdBu", origin="lower",
                    labels=dict(color="Avg composite"))
    fig.update_layout(title="Average composite score by sector and year", height=500)
    return fig


def fig_decile_cumret(dec: pd.DataFrame, n_buckets: int = config.N_DECILES) -> go.Figure:
    fig = go.Figure()
    spread_label = f"D{n_buckets}-D1 spread"
    for col in [c for c in dec.columns if c.startswith("D")] + ["spread"]:
        cum = (1 + dec[col].fillna(0)).cumprod() - 1
        style = dict(width=3, color="black") if col == "spread" else dict(width=1)
        fig.add_trace(go.Scatter(x=dec.index, y=cum,
                                 name=spread_label if col == "spread" else col, line=style))
    fig.update_layout(title=f"Cumulative bucket returns ({n_buckets} buckets, equal weight, monthly)",
                      yaxis_tickformat=".0%", height=550)
    return fig


def fig_f_scatter(panel: pd.DataFrame) -> go.Figure:
    df = panel.dropna(subset=["f_score", "fwd_ret_1m", "sector"])
    fig = px.scatter(df, x="f_score", y="fwd_ret_1m", color="sector", opacity=0.25,
                     trendline="ols", trendline_scope="overall",
                     labels={"f_score": "Piotroski F-Score", "fwd_ret_1m": "Next-month return"})
    fig.update_layout(title="F-Score vs. forward 1-month return (all company-months)",
                      yaxis_tickformat=".0%", height=550)
    return fig


def fig_rolling(roll: pd.DataFrame, universe_name: str = "", backtestable: bool = True) -> go.Figure:
    # Neutral title on purpose: the chart reports what the data shows,
    # including decay if that is what it shows.
    fig = go.Figure()
    has_dsr = {"dsr_lo", "dsr_hi"} <= set(roll.columns)
    if has_dsr:
        # The DSR band: the spread each window would need for its OWN
        # Deflated Sharpe Ratio to reach 95%, given that window's
        # volatility, empirical skew/kurtosis and the four related scores
        # tried on this data. A line inside the band marks a window that
        # would NOT have survived the correction the summary table applies.
        fig.add_trace(go.Scatter(x=roll.index, y=roll["dsr_hi"], line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=roll.index, y=roll["dsr_lo"], fill="tonexty",
            fillcolor="rgba(200,120,40,0.18)", line=dict(width=0),
            name="Deflated-Sharpe 95% band (would this window survive?)"))
    fig.add_trace(go.Scatter(x=roll.index, y=roll["hi"], line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=roll.index, y=roll["lo"], fill="tonexty",
                             fillcolor="rgba(31,119,180,0.15)", line=dict(width=0),
                             name="±1.96 SE band (descriptive)"))
    mode = "lines+markers" if not backtestable else "lines"
    fig.add_trace(go.Scatter(x=roll.index, y=roll["ann_spread"], name="Annualized spread",
                             mode=mode, line=dict(color="rgb(31,119,180)", width=2)))
    fig.add_hline(y=0, line_dash="dot")
    title = f"Rolling {config.ROLLING_WINDOW_MONTHS}-Month Spread (annualized)"
    if universe_name:
        title += f" — {universe_name}"
    if not backtestable:
        title += "  [descriptive only — see note below, not a test]"
    fig.update_layout(title=title, yaxis_tickformat=".0%", height=520,
                      legend=dict(orientation="h", y=-0.15))
    if not backtestable:
        n = int(roll["ann_spread"].notna().sum())
        fig.add_annotation(
            text=(f"Only {n} overlapping {config.ROLLING_WINDOW_MONTHS}-month window(s) exist for "
                  f"this universe (its full history is barely longer than one window). "
                  f"This is a shape diagnostic, not an inferential result — see FINDINGS.md."),
            xref="paper", yref="paper", x=0.5, y=1.08, showarrow=False,
            font=dict(size=12, color="#a05a00"), align="center",
        )
    return fig


def build_app(universe="sp500") -> Dash:
    uni = get_universe(universe) if isinstance(universe, str) else universe
    panel, dec, summary, roll = load_data(uni)
    xsec = latest_cross_section(panel)

    app = Dash(__name__, title=f"Composite Fundamental Screener — {uni.name}")
    table = dash_table.DataTable(
        data=xsec.to_dict("records"),
        columns=[{"name": c, "id": c} for c in xsec.columns],
        filter_action="native", sort_action="native", page_size=25,
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "monospace", "fontSize": 13},
    )

    def _unavailable(view: str) -> html.Div:
        """Shown instead of a specific backtest artifact this universe's
        data does not support. Kept generic to `view` rather than claiming
        blanket unavailability: a screener-only universe like India still
        produces bucket returns and a rolling chart (labeled descriptive
        wherever they render) — what it withholds specifically is the
        Newey-West/Deflated-Sharpe validation table, since a single point
        estimate over a handful of independent updates is not a test."""
        return html.Div(style={"padding": "2em", "background": "#fff8e1",
                               "border": "1px solid #e0c060", "marginTop": "1em"},
                        children=[
            html.H4(f"{view} is not available for {uni.name}"),
            html.P(f"This universe's source supports too few independent "
                   f"cross-sections for {view.lower()} to mean anything as a "
                   f"statistical result, so it is not produced here."),
            html.P("Showing an empty or placeholder version would imply evidence "
                   "that does not exist. Other views on this universe that ARE "
                   "real — the screener table, sector heatmap, F-Score scatter, "
                   "and (where present) bucket returns and rolling spread, each "
                   "labeled descriptive rather than inferential — remain available."),
        ])

    tabs = [
        dcc.Tab(label="Screener table", children=[
            html.P(f"Latest cross-section ({panel['as_of_date'].max():%Y-%m-%d}). "
                   "Filter boxes accept e.g. >5 or contains Tech."),
            table,
        ]),
        dcc.Tab(label="Sector heatmap", children=[dcc.Graph(figure=fig_sector_heatmap(panel))]),
        dcc.Tab(label="Bucket returns", children=[
            dcc.Graph(figure=fig_decile_cumret(dec, uni.n_buckets)) if dec is not None
            else _unavailable("Bucket returns")]),
        dcc.Tab(label="F-Score scatter", children=[dcc.Graph(figure=fig_f_scatter(panel))]),
        dcc.Tab(label="Rolling spread", children=[
            dcc.Graph(figure=fig_rolling(roll, uni.name, uni.backtestable)) if roll is not None
            else _unavailable("Rolling spread")]),
        dcc.Tab(label="Validation", children=(
            [html.H4(f"Newey-West / Deflated Sharpe summary (D{uni.n_buckets} − D1)"),
             html.Pre(summary.round(3).to_string(),
                      style={"fontSize": 14, "background": "#f6f6f6", "padding": "1em"}),
             html.P("survives_95 = Deflated Sharpe Ratio > 0.95 after correcting for "
                    "4 related trials (F, Z, O, composite) with empirical skew/kurtosis.")]
            if summary is not None else [_unavailable("Validation summary")])),
    ]

    app.layout = html.Div(
        style={"maxWidth": "1200px", "margin": "auto", "fontFamily": "sans-serif"},
        children=[
            html.H2(f"Composite Fundamental Screener — {uni.name} ({uni.currency})"),
            html.P(("Screener only — no backtest is run for this universe."
                    if not uni.backtestable else
                    f"{uni.n_buckets} buckets, monthly rebalance, returns in {uni.currency}."),
                   style={"color": "#666"}),
            dcc.Tabs(tabs),
        ],
    )
    return app


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Composite fundamental screener dashboard")
    p.add_argument("--universe", default="sp500", choices=["sp500", "russell3000", "kospi", "india"])
    p.add_argument("--port", type=int, default=8050)
    a = p.parse_args()
    build_app(a.universe).run(debug=False, port=a.port)
