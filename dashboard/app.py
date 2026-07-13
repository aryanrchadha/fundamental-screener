"""Plotly Dash dashboard for the composite fundamental screener.

Run with:  python -m dashboard.app   (after screener.backtest + validation)
Serves on http://localhost:8050.

Reads the parquet/CSV artifacts written by the pipeline — it performs no
computation of its own, so what you see is exactly what was validated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dash_table, dcc, html

import config


def load_data():
    panel = pd.read_parquet(config.SCORES_PANEL_PATH)
    dec = pd.read_parquet(config.DECILE_RETURNS_PATH)
    summary = pd.read_csv(config.VALIDATION_SUMMARY_PATH, index_col=0)
    roll = pd.read_parquet(config.ROLLING_SPREAD_PATH)
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


def fig_decile_cumret(dec: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col in [c for c in dec.columns if c.startswith("D")] + ["spread"]:
        cum = (1 + dec[col].fillna(0)).cumprod() - 1
        style = dict(width=3, color="black") if col == "spread" else dict(width=1)
        fig.add_trace(go.Scatter(x=dec.index, y=cum, name="D10-D1 spread" if col == "spread" else col,
                                 line=style))
    fig.update_layout(title="Cumulative decile returns (equal weight, monthly rebalance)",
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


def fig_rolling(roll: pd.DataFrame) -> go.Figure:
    # Neutral title on purpose: the chart reports what the data shows,
    # including decay if that is what it shows.
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=roll.index, y=roll["hi"], line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=roll.index, y=roll["lo"], fill="tonexty",
                             fillcolor="rgba(31,119,180,0.2)", line=dict(width=0),
                             name="±1.96 SE band"))
    fig.add_trace(go.Scatter(x=roll.index, y=roll["ann_spread"], name="Annualized spread",
                             line=dict(color="rgb(31,119,180)", width=2)))
    fig.add_hline(y=0, line_dash="dot")
    fig.update_layout(title=f"Rolling {config.ROLLING_WINDOW_MONTHS}-Month Decile Spread (annualized)",
                      yaxis_tickformat=".0%", height=500)
    return fig


def build_app() -> Dash:
    panel, dec, summary, roll = load_data()
    xsec = latest_cross_section(panel)

    app = Dash(__name__, title="Composite Fundamental Screener")
    table = dash_table.DataTable(
        data=xsec.to_dict("records"),
        columns=[{"name": c, "id": c} for c in xsec.columns],
        filter_action="native", sort_action="native", page_size=25,
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "monospace", "fontSize": 13},
    )
    summary_txt = html.Pre(summary.round(3).to_string(),
                           style={"fontSize": 14, "background": "#f6f6f6", "padding": "1em"})

    app.layout = html.Div(
        style={"maxWidth": "1200px", "margin": "auto", "fontFamily": "sans-serif"},
        children=[
            html.H2("Composite Fundamental Screener"),
            dcc.Tabs([
                dcc.Tab(label="Screener table", children=[
                    html.P(f"Latest cross-section ({panel['as_of_date'].max():%Y-%m-%d}). "
                           "Filter boxes accept e.g. >5 or contains Tech."),
                    table,
                ]),
                dcc.Tab(label="Sector heatmap", children=[dcc.Graph(figure=fig_sector_heatmap(panel))]),
                dcc.Tab(label="Decile returns", children=[dcc.Graph(figure=fig_decile_cumret(dec))]),
                dcc.Tab(label="F-Score scatter", children=[dcc.Graph(figure=fig_f_scatter(panel))]),
                dcc.Tab(label="Rolling spread", children=[dcc.Graph(figure=fig_rolling(roll))]),
                dcc.Tab(label="Validation", children=[
                    html.H4("Newey-West / Deflated Sharpe summary (D10 − D1)"),
                    summary_txt,
                    html.P("survives_95 = Deflated Sharpe Ratio > 0.95 after correcting for "
                           "4 related trials (F, Z, O, composite) with empirical skew/kurtosis."),
                ]),
            ]),
        ],
    )
    return app


if __name__ == "__main__":
    build_app().run(debug=False, port=8050)
