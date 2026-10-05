"""Plotly Dash GUI for the composite fundamental screener.

Run with:  python -m dashboard        (opens http://localhost:8050)
      or:  python -m dashboard.app --universe kospi --survivorship

Results views read the parquet/CSV artifacts written by the pipeline — they
perform no computation of their own, so what you see is exactly what was
validated. The universe and survivorship mode are switchable in the page,
and the "Run pipeline" tab launches the same CLI commands the README
documents (see dashboard/jobs.py), reloading the views when a run finishes.
"""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, no_update
from plotly.subplots import make_subplots

import config
from dashboard import analysis
from dashboard.grids import col, grid, register_exports, row_rule
from dashboard.jobs import RUNNER, STEPS, step_commands, survivorship_supported
from screener.universes import UNIVERSES, Universe, get_universe


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
    xsec = panel[panel["as_of_date"] == last][cols].dropna(subset=["composite_score"]).copy()
    # Ohlson's O is a logit; the implied one-to-two-year default probability
    # is the logistic of it. Shown because "O = -7.9" means little on sight.
    xsec.insert(xsec.columns.get_loc("o_score") + 1, "o_default_prob",
                1 / (1 + np.exp(-xsec["o_score"])))
    return xsec.round({"f_score": 0, "z_score": 3, "o_score": 3, "o_default_prob": 7,
                       "composite_score": 3}).sort_values("composite_score", ascending=False)


# Textbook cutoffs from the original papers, applied to the raw scores.
# Altman: the 1968 public-company model's zones (distress < 1.81, safe >
# 2.99). Piotroski: his "high" portfolio is F = 8-9, "low" is 0-1.
# Ohlson: O is a logit, so P(default) > 50% is O > 0.
SCREENS = {
    "f_high": ("Piotroski high (F ≥ 8)", lambda x: x["f_score"] >= 8),
    "f_low": ("Piotroski low (F ≤ 2)", lambda x: x["f_score"] <= 2),
    "z_safe": ("Altman safe zone (Z > 2.99)", lambda x: x["z_score"] > 2.99),
    "z_grey": ("Altman grey zone (1.81–2.99)", lambda x: x["z_score"].between(1.81, 2.99)),
    "z_distress": ("Altman distress zone (Z < 1.81)", lambda x: x["z_score"] < 1.81),
    "o_safe": ("Ohlson P(default) < 50% (O < 0)", lambda x: x["o_score"] < 0),
    "o_risk": ("Ohlson P(default) > 50% (O > 0)", lambda x: x["o_score"] > 0),
}


def apply_screens(xsec: pd.DataFrame, keys) -> pd.DataFrame:
    """Rows passing every selected screen (AND). A name missing a score a
    screen needs fails that screen rather than passing by default."""
    mask = pd.Series(True, index=xsec.index)
    for k in keys or []:
        mask &= SCREENS[k][1](xsec).fillna(False).astype(bool)
    return xsec[mask]


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


SCATTER_MAX_POINTS = 20_000


def fig_f_scatter(panel: pd.DataFrame, max_points: int = SCATTER_MAX_POINTS) -> go.Figure:
    """F-Score against next-month return. The OLS line is fitted on every
    company-month; only the plotted points are sampled when there are more
    than `max_points` (the Russell 3000 has ~400k, which the browser cannot
    draw responsively), so the fit never depends on the sample."""
    df = panel.dropna(subset=["f_score", "fwd_ret_1m", "sector"])
    n = len(df)
    shown = df.sample(max_points, random_state=0) if n > max_points else df
    fig = px.scatter(shown, x="f_score", y="fwd_ret_1m", color="sector", opacity=0.25,
                     labels={"f_score": "Piotroski F-Score", "fwd_ret_1m": "Next-month return"})
    if n >= 2 and df["f_score"].nunique() > 1:
        slope, intercept = np.polyfit(df["f_score"], df["fwd_ret_1m"], 1)
        xs = np.array([df["f_score"].min(), df["f_score"].max()])
        fig.add_trace(go.Scatter(x=xs, y=intercept + slope * xs, mode="lines",
                                 name=f"OLS, all {n:,} points (slope {slope:+.2%}/pt)",
                                 line=dict(color="black", width=2)))
    title = "F-Score vs. forward 1-month return (all company-months)"
    if n > max_points:
        title += f" — showing a random {max_points:,} of {n:,}"
    fig.update_layout(title=title, yaxis_tickformat=".0%", height=550)
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




def fig_company_history(panel: pd.DataFrame, ticker: str) -> go.Figure:
    """One company's score history: the three raw scores plus where the
    composite placed it each month. Raw scores, not sector z-scores, so the
    numbers match the published thresholds (F 0-9, Z 1.81/2.99, O > 0 i.e. P(default) > 50%)."""
    df = panel[panel["ticker"] == ticker].sort_values("as_of_date")
    rows = [("f_score", "Piotroski F"), ("z_score", "Altman Z"),
            ("o_score", "Ohlson O"), ("composite_score", "Composite")]
    fig = make_subplots(rows=len(rows), cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        subplot_titles=[label for _, label in rows])
    for i, (col, label) in enumerate(rows, 1):
        if col not in df:
            continue
        hover = None
        if col == "composite_score" and "decile" in df:
            hover = [f"decile {d:.0f}" if pd.notna(d) else "unranked" for d in df["decile"]]
        fig.add_trace(go.Scatter(x=df["as_of_date"], y=df[col], name=label, mode="lines+markers",
                                 marker=dict(size=4), line=dict(shape="hv"), text=hover,
                                 showlegend=False), row=i, col=1)
    sector = df["sector"].dropna().iloc[-1] if df["sector"].notna().any() else "unknown sector"
    fig.update_layout(title=f"{ticker} — {sector}", height=780, margin=dict(t=80))
    return fig


# ---------------------------------------------------------------------------
# Universe resolution and cached loading
# ---------------------------------------------------------------------------

ARTIFACTS = [("Scores panel", "panel_path"), ("Bucket returns", "bucket_returns_path"),
             ("Validation", "validation_path"), ("Rolling spread", "rolling_path")]


def _mtime(path) -> float:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def _artifact_mtimes(uni: Universe) -> tuple:
    return tuple(_mtime(getattr(uni, attr)) for _, attr in ARTIFACTS)


@lru_cache(maxsize=8)
def _cached_data(uni: Universe, mtimes: tuple):
    # `mtimes` is part of the key only so a pipeline run that rewrites an
    # artifact invalidates the cached copy; it is otherwise unused.
    return load_data(uni)


@lru_cache(maxsize=8)
def _turnover_cached(uni: Universe, mtimes: tuple) -> pd.DataFrame:
    return analysis.bucket_turnover(data_for(uni)[0], uni.n_buckets)


def data_for(uni: Universe):
    """load_data, cached until any of the universe's artifacts change.
    Returns None when the scores panel has not been produced yet."""
    if not Path(uni.panel_path).exists():
        return None
    return _cached_data(uni, _artifact_mtimes(uni))


def artifact_status(uni: Universe) -> list:
    parts = []
    for label, attr in ARTIFACTS:
        t = _mtime(getattr(uni, attr))
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else "missing"
        parts.append(html.Span(f"{label}: {stamp}", style={
            "marginRight": "1.2em", "color": "#666" if t else "#b00"}))
    return parts


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

UNIVERSE_LABELS = {"sp500": "US — S&P 500", "russell3000": "US — Russell 3000",
                   "kospi": "Korea — KOSPI 120", "india": "India — BSE 100 (screener only)"}

DATA_TABS = ["screener", "heatmap", "buckets", "scatter", "rolling", "validation"]
_BOX = {"padding": "2em", "background": "#fff8e1", "border": "1px solid #e0c060", "marginTop": "1em"}


def _unavailable(uni: Universe, view: str) -> html.Div:
    """Shown instead of a specific backtest artifact this universe's data
    does not support. Kept generic to `view` rather than claiming blanket
    unavailability: a screener-only universe like India still produces
    bucket returns and a rolling chart (labeled descriptive wherever they
    render) — what it withholds specifically is the Newey-West/Deflated-
    Sharpe validation table, since a single point estimate over a handful
    of independent updates is not a test."""
    if uni.backtestable:
        # A backtestable universe missing an artifact simply hasn't run
        # that step yet — say so instead of implying the data can't support it.
        return html.Div(style=_BOX, children=[
            html.H4(f"{view} has not been produced yet for {uni.name}"),
            html.P("Run the backtest and validation steps from the \"Run pipeline\" tab."),
        ])
    return html.Div(style=_BOX, children=[
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


def stale_warning(uni: Universe):
    """A banner when the validation outputs predate the backtest they claim
    to summarize. That happens whenever the backtest is re-run (e.g. on a
    50-ticker test universe) without re-running validation: the table and
    rolling chart then describe a panel that no longer exists on disk."""
    if not uni.backtestable:
        return None                          # India's rolling chart is written by the backtest itself
    bt = _mtime(uni.bucket_returns_path)
    stale = [label for label, attr in (("Validation", "validation_path"), ("Rolling spread", "rolling_path"))
             if 0 < _mtime(getattr(uni, attr)) < bt]
    if not stale:
        return None
    return html.Div(style={**_BOX, "background": "#fdecea", "border": "1px solid #e57373"}, children=[
        html.B(f"Stale: {' and '.join(stale)} predate the current backtest output."),
        html.P("These numbers were computed from an earlier scores panel and may not match the "
               "other tabs. Re-run the validation step from \"Run pipeline\".",
               style={"margin": "0.4em 0 0"}),
    ])


def render_views(uni: Universe) -> dict:
    """Children for every results tab, keyed by DATA_TABS entry."""
    data = data_for(uni)
    if data is None:
        msg = html.Div(style=_BOX, children=[
            html.H4(f"No scores panel for {uni.name}"
                    + (" (survivorship-corrected)" if uni.survivorship_corrected else "")),
            html.P(f"Expected {Path(uni.panel_path).name} in data/. Run ingest + backtest "
                   "from the \"Run pipeline\" tab, then the views fill in automatically."),
        ])
        return {k: msg for k in DATA_TABS}

    panel, dec, summary, roll = data
    stale = stale_warning(uni)
    if summary is not None:
        s = summary.reset_index()
        validation = [
            stale,
            html.H4(f"Newey-West / Deflated Sharpe summary (D{uni.n_buckets} − D1)"),
            grid("validation-grid", [
                col("strategy", minWidth=170), col("months"), col("ann_return", "pct1"),
                col("ann_sharpe", "num3"), col("nw_tstat", "num3"), col("nw_lag"),
                col("skew", "num3"), col("kurtosis", "num3"), col("dsr", "num3"),
                col("dsr_pvalue", "num3"), col("survives_95"),
            ], s.to_dict("records"), row_rules=VERDICT_RULES),
            html.P("survives_95 = Deflated Sharpe Ratio > 0.95 after correcting for "
                   "4 related trials (F, Z, O, composite) with empirical skew/kurtosis."),
        ]
    else:
        validation = [_unavailable(uni, "Validation summary")]

    return {
        "screener": [],                      # the table itself is static; see _screener
        "heatmap": [dcc.Graph(figure=fig_sector_heatmap(panel))],
        "buckets": [dcc.Graph(figure=fig_decile_cumret(dec, uni.n_buckets)) if dec is not None
                    else _unavailable(uni, "Bucket returns")],
        "scatter": [dcc.Graph(figure=fig_f_scatter(panel))],
        "rolling": [stale, dcc.Graph(figure=fig_rolling(roll, uni.name, uni.backtestable)) if roll is not None
                    else _unavailable(uni, "Rolling spread")],
        "validation": validation,
    }


def _subtitle(uni: Universe) -> str:
    if not uni.backtestable:
        return "Screener only — no backtest is run for this universe."
    mode = "survivorship-corrected" if uni.survivorship_corrected else "static universe"
    return f"{uni.n_buckets} buckets, monthly rebalance, returns in {uni.currency}, {mode}."


def _company_options(uni: Universe):
    data = data_for(uni)
    if data is None:
        return [], None
    panel = data[0]
    xsec = latest_cross_section(panel)
    tickers = xsec["ticker"].tolist() or sorted(panel["ticker"].unique())
    return [{"label": t, "value": t} for t in tickers], (tickers[0] if tickers else None)


def _pipeline_panel(uni: Universe) -> html.Div:
    return html.Div(style={"padding": "1em 0"}, children=[
        html.P("Runs the same commands as the README for the universe selected above, one "
               "step after another. Results tabs reload automatically when the run finishes."),
        dcc.Checklist(id="pipe-steps", value=["backtest", "validation"], inline=True,
                      options=[{"label": f" {s} ", "value": s} for s in STEPS],
                      style={"marginBottom": "0.6em"}),
        html.Div([
            html.Label("Ingest ticker limit (US only, blank = full universe): "),
            dcc.Input(id="pipe-limit", type="number", min=1, step=1, debounce=True,
                      style={"width": "7em"}),
        ], style={"marginBottom": "0.6em"}),
        html.Div(id="pipe-preview", style={"fontFamily": "monospace", "fontSize": 12,
                                           "color": "#444", "whiteSpace": "pre-wrap",
                                           "marginBottom": "0.6em"}),
        html.Button("Run", id="pipe-run", n_clicks=0, style={"marginRight": "0.5em"}),
        html.Button("Stop", id="pipe-stop", n_clicks=0),
        html.Span(id="pipe-status", style={"marginLeft": "1em", "fontWeight": "bold"}),
        html.Pre(id="pipe-log", style={"height": "420px", "overflowY": "auto", "fontSize": 12,
                                       "background": "#111", "color": "#ddd", "padding": "1em",
                                       "marginTop": "1em", "whiteSpace": "pre-wrap"}),
        html.P("Ingest notes: KOSPI needs DART_API_KEY set in the environment that launched "
               "this app; a full S&P 500 ingest takes ~30 min and Russell 3000 longer "
               "(both resumable — already-loaded companies are skipped).",
               style={"color": "#666", "fontSize": 13}),
    ])


VERDICT_RULES = [
    row_rule("params.data.survives_95 === true", backgroundColor="#e6f4ea", fontWeight="bold"),
    row_rule("params.data.stale === true", color="#b00"),
]
VERDICT_COLS = [col("scenario", minWidth=260), col("months"), col("ann_return", "pct1"),
                col("nw_tstat", "num3"), col("dsr", "num3"), col("survives_95")]

# Every grid in the app, for register_exports (see its docstring).
GRID_IDS = ["screener-table", "validation-grid", "month-table", "rob-table", "cost-table",
            "watch-table", "overview-grid"]


def overview_panel(universes=None) -> list:
    df = analysis.run_overview(universes)
    if df.empty:
        return [html.P("No validation tables on disk yet — run the pipeline first.")]
    return [
        html.P("The composite's verdict for every run that has a validation table. "
               "Red rows are stale (validation older than the backtest). Returns are "
               "in each market's own currency, so levels are not comparable across rows; "
               "the verdicts are.", style={"marginTop": "1em"}),
        grid("overview-grid", [
            col("universe"), col("mode", minWidth=170), col("currency"), col("months"),
            col("ann_return", "pct1"), col("nw_tstat", "num3"), col("dsr", "num3"),
            col("survives_95"), col("stale"),
        ], df.to_dict("records"), row_rules=VERDICT_RULES),
        html.P("India is absent by design: it is screener-only and produces no validation table.",
               style={"color": "#666", "fontSize": 13}),
    ]


def compare_panel(universes=None) -> list:
    runs = analysis.available_runs(universes)
    default = [r["key"] for r in runs if r["key"] in ("sp500|static", "sp500|corrected")]
    return [
        html.H4("Compare runs", style={"marginTop": "1.5em"}),
        dcc.Checklist(id="compare-runs", value=default, inline=True,
                      options=[{"label": f" {r['label']} ", "value": r["key"]} for r in runs],
                      style={"fontSize": 13}),
        dcc.Graph(id="compare-graph"),
    ]


def fig_compare(series: dict) -> go.Figure:
    fig = go.Figure()
    for label, cum in series.items():
        fig.add_trace(go.Scatter(x=cum.index, y=cum.values, name=label))
    fig.add_hline(y=0, line_dash="dot")
    fig.update_layout(title="Cumulative composite spread by run (local currency — compare shape "
                            "and timing, not levels)", yaxis_tickformat=".0%", height=450,
                      legend=dict(orientation="h", y=-0.2))
    return fig


def fig_sector_attribution(panel: pd.DataFrame, n_buckets: int) -> go.Figure:
    a = analysis.sector_attribution(panel, n_buckets)
    fig = go.Figure(go.Bar(
        x=a["ann_contribution"], y=a["sector"], orientation="h",
        marker_color=["#2c7fb8" if v >= 0 else "#d62728" for v in a["ann_contribution"]],
        customdata=a[["avg_top_names", "avg_bottom_names"]].values,
        hovertemplate=("%{y}: %{x:+.2%}/yr<br>avg %{customdata[0]:.1f} names in top bucket, "
                       "%{customdata[1]:.1f} in bottom<extra></extra>")))
    total = a["ann_contribution"].sum()
    fig.update_layout(title=f"Where the spread came from, by sector (sums to {total:+.1%}/yr, "
                            "arithmetic)", xaxis_tickformat=".1%", height=420,
                      margin=dict(l=180))
    return fig


def _month_options(uni: Universe):
    data = data_for(uni)
    if data is None or data[1] is None or "spread" not in data[1]:
        return [], None
    dates = data[1]["spread"].dropna().index
    opts = [{"label": f"{d:%Y-%m}", "value": f"{d:%Y-%m-%d}"} for d in dates[::-1]]
    return opts, (opts[0]["value"] if opts else None)


def fig_month_spread(dec: pd.DataFrame, selected=None) -> go.Figure:
    s = dec["spread"].dropna()
    sel = pd.Timestamp(selected) if selected else None
    colors = ["#d62728" if sel is not None and d == sel else ("#2c7fb8" if v >= 0 else "#999")
              for d, v in s.items()]
    fig = go.Figure(go.Bar(x=s.index, y=s.values, marker_color=colors,
                           hovertemplate="%{x|%Y-%m}: %{y:.1%}<extra></extra>"))
    fig.update_layout(title="Monthly top-minus-bottom spread — click a bar to inspect that month",
                      yaxis_tickformat=".0%", height=300, margin=dict(t=50, b=30))
    return fig


def month_panel(options=(), value=None) -> list:
    return [
        dcc.Graph(id="month-graph"),
        html.Div([html.Label("Month: "),
                  dcc.Dropdown(id="month-date", options=list(options), value=value,
                               clearable=False, style={"width": "160px"})],
                 style={"display": "flex", "alignItems": "center", "gap": "0.5em"}),
        html.Div(id="month-summary", style={"margin": "0.8em 0"}),
        grid("month-table", [
            col("ticker"), col("sector", minWidth=170), col("bucket"),
            col("fwd_ret_1m", "pct1"), col("contribution", "pct1"),
        ], page_size=20, row_rules=[row_rule("Math.abs(params.data.contribution) > 0.02",
                                             backgroundColor="#fff3cd")]),
        html.P("contribution = the name's next-month return ÷ its bucket size, + for the top bucket "
               "and − for the bottom, so the column sums to the month's spread. Highlighted names "
               "moved the spread by more than 2 points on their own.",
               style={"color": "#666", "fontSize": 13}),
    ]


def robustness_panel() -> list:
    num = {"type": "number", "debounce": True, "style": {"width": "5em"}}
    return [
        html.P("Re-scores the composite's top-minus-bottom spread under one change at a time, "
               "with the same Newey-West and Deflated Sharpe code as the validation table.",
               style={"marginTop": "1em"}),
        html.Div(style={"display": "flex", "gap": "1.5em", "flexWrap": "wrap", "alignItems": "center"}, children=[
            html.Label(["Winsorize at (pct) ", dcc.Input(id="rob-winsor", value=1, min=0, max=10, step=0.5, **num)]),
            html.Label(["Drop largest months ", dcc.Input(id="rob-top", value=2, min=0, max=24, step=1, **num)]),
            html.Label(["Drop smallest months ", dcc.Input(id="rob-bottom", value=0, min=0, max=24, step=1, **num)]),
        ]),
        html.Label(["Exclude tickers from the top/bottom buckets (comma-separated) ",
                    dcc.Input(id="rob-exclude", type="text", debounce=True, placeholder="e.g. GME, SBET",
                              style={"width": "260px"})], style={"display": "block", "margin": "0.6em 0"}),
        html.Div([html.Label("Exclude sectors "),
                  dcc.Dropdown(id="rob-sectors", multi=True, placeholder="none",
                               style={"minWidth": "320px"})],
                 style={"display": "flex", "alignItems": "center", "gap": "0.5em", "margin": "0.6em 0"}),
        grid("rob-table", VERDICT_COLS, row_rules=VERDICT_RULES),
        dcc.Graph(id="rob-graph"),
        dcc.Graph(id="rob-sector-graph"),
        html.Div(style={**_BOX, "fontSize": 13}, children=[
            html.B("Read these as diagnostics, not new tests. "),
            "Each perturbation tried here is another look at the same data, and the DSR's "
            "N_trials = 4 does not count them. A verdict that flips under a small, reasonable "
            "change is fragile; a perturbation chosen after seeing which way it flips the "
            "verdict is the selection error the DSR exists to prevent.",
        ]),
    ]


SCREENER_GRID_COLS = [
    col("ticker", pinned="left"), col("sector", minWidth=170), col("f_score"),
    col("z_score", "num3"), col("o_score", "num3"), col("o_default_prob", "pct3", header="P(default)"),
    col("composite_score", "num3"), col("decile"),
]


def screener_rows(uni: Universe, screens) -> tuple[list, str]:
    data = data_for(uni)
    if data is None:
        return [], ""
    xsec = latest_cross_section(data[0])
    shown = apply_screens(xsec, screens)
    caption = (f"Latest cross-section ({data[0]['as_of_date'].max():%Y-%m-%d}): "
               f"{len(shown)} of {len(xsec)} names")
    if screens:
        caption += " pass " + " AND ".join(SCREENS[k][0] for k in screens)
    caption += (". Click a column header to sort; the box under it filters. Click a row to "
                "open that company's history; Export CSV saves the filtered, sorted table.")
    return shown.to_dict("records"), caption


def costs_panel() -> list:
    return [
        html.P("What trading the composite's long-short spread would have cost. Each rebalance "
               "replaces part of the top and bottom buckets; every name replaced is sold and "
               "bought, on both legs, at the one-way cost below.", style={"marginTop": "1em"}),
        html.Label(["One-way cost (bps) ",
                    dcc.Input(id="cost-bps", type="number", value=30, min=0, max=500, step=1,
                              debounce=True, style={"width": "5em"})]),
        html.Div(id="cost-summary", style={"margin": "0.8em 0"}),
        grid("cost-table", VERDICT_COLS, row_rules=VERDICT_RULES),
        dcc.Graph(id="cost-graph"),
        dcc.Graph(id="turnover-graph"),
        html.P("Turnover compares target equal weights rebalance to rebalance, ignoring "
               "intra-month drift, so it slightly understates true trading. Rough one-way "
               "costs: large caps ~5–15 bps, small caps ~25–60, micro caps 100+.",
               style={"color": "#666", "fontSize": 13}),
    ]


WATCH_METRICS = {"decile": "Decile (bucket)", "composite_score": "Composite score",
                 "f_score": "Piotroski F", "z_score": "Altman Z", "o_score": "Ohlson O"}


def watchlist_panel() -> list:
    return [
        html.P("Pin tickers to follow them side by side. Pins are saved in this browser, "
               "separately for each universe.", style={"marginTop": "1em"}),
        html.Div(style={"display": "flex", "gap": "1em", "flexWrap": "wrap", "alignItems": "center"}, children=[
            dcc.Dropdown(id="watch-tickers", multi=True, placeholder="Add tickers…",
                         style={"minWidth": "420px", "flex": "1"}),
            dcc.Dropdown(id="watch-metric", value="decile", clearable=False, style={"width": "200px"},
                         options=[{"label": v, "value": k} for k, v in WATCH_METRICS.items()]),
        ]),
        dcc.Store(id="watch-store", storage_type="local"),
        dcc.Graph(id="watch-graph"),
        grid("watch-table", [
            col("ticker"), col("sector", minWidth=170), col("as_of_date"), col("f_score"),
            col("z_score", "num3"), col("o_score", "num3"), col("composite_score", "num3"),
            col("decile"), col("decile_12m_ago"),
        ]),
    ]


def fig_watchlist(panel: pd.DataFrame, tickers, metric: str, n_buckets: int) -> go.Figure:
    fig = go.Figure()
    for t in tickers or []:
        df = panel[panel["ticker"] == t].sort_values("as_of_date")
        fig.add_trace(go.Scatter(x=df["as_of_date"], y=df[metric], name=t, mode="lines",
                                 line=dict(shape="hv")))
    fig.update_layout(title=f"{WATCH_METRICS[metric]} over time", height=450,
                      legend=dict(orientation="h", y=-0.2))
    if metric == "decile":
        fig.update_yaxes(range=[0.5, n_buckets + 0.5], dtick=1,
                         title=f"1 = worst … {n_buckets} = best composite")
    if not tickers:
        fig.update_layout(title="Pick tickers above to plot them")
    return fig


def watchlist_rows(panel: pd.DataFrame, tickers) -> list:
    if not tickers:
        return []
    last = panel["as_of_date"].max()
    x = panel[panel["ticker"].isin(tickers)].sort_values("as_of_date")
    rows = []
    for t, df in x.groupby("ticker"):
        cur = df.iloc[-1]
        prior = df[df["as_of_date"] <= last - pd.DateOffset(months=12)]
        rows.append({
            "ticker": t, "sector": cur["sector"], "as_of_date": f"{cur['as_of_date']:%Y-%m-%d}",
            **{c: (None if pd.isna(cur[c]) else round(float(cur[c]), 3))
               for c in ("f_score", "z_score", "o_score", "composite_score", "decile")},
            "decile_12m_ago": (None if prior.empty or pd.isna(prior.iloc[-1]["decile"])
                               else float(prior.iloc[-1]["decile"])),
        })
    return rows


def build_app(universe="sp500") -> Dash:
    uni0 = get_universe(universe) if isinstance(universe, str) else universe
    # Base (uncorrected) universe per name. A Universe object passed in
    # (tests do this with tmp paths) replaces the registry entry for its name.
    bases = dict(UNIVERSES)
    if not uni0.survivorship_corrected:
        bases[uni0.name] = uni0

    def resolve(name: str, surv) -> Universe:
        base = bases[name]
        return base.corrected() if surv and survivorship_supported(name) else base

    views = render_views(uni0)
    options, first = _company_options(uni0)

    app = Dash(__name__, title="Composite Fundamental Screener",
               suppress_callback_exceptions=True)

    def tab(label, value, children):
        return dcc.Tab(label=label, value=value, children=children)

    app.layout = html.Div(
        style={"maxWidth": "1200px", "margin": "auto", "fontFamily": "sans-serif", "padding": "0 16px"},
        children=[
            html.H2(f"Composite Fundamental Screener — {uni0.name} ({uni0.currency})", id="title"),
            html.Div(style={"display": "flex", "gap": "1.5em", "alignItems": "center",
                            "flexWrap": "wrap"}, children=[
                dcc.Dropdown(id="universe", value=uni0.name, clearable=False, style={"width": "300px"},
                             options=[{"label": UNIVERSE_LABELS.get(n, n), "value": n} for n in bases]),
                dcc.Checklist(id="survivorship",
                              value=["on"] if uni0.survivorship_corrected else [],
                              options=[{"label": " survivorship-corrected", "value": "on",
                                        "disabled": not survivorship_supported(uni0.name)}]),
                html.Button("Reload data", id="reload", n_clicks=0),
            ]),
            html.P(_subtitle(uni0), id="subtitle", style={"color": "#666"}),
            html.Div(artifact_status(uni0), id="data-status", style={"fontSize": 12, "marginBottom": "0.8em"}),
            dcc.Store(id="data-version", data=0),
            dcc.Store(id="job-seen", data=None),
            dcc.Interval(id="pipe-tick", interval=1000),
            dcc.Tabs(id="tabs", value="screener", children=[
                tab("Screener table", "screener", [
                    html.Div(views["screener"], id="view-screener"),
                    dcc.Checklist(id="screens", value=[], inline=True,
                                  options=[{"label": f" {label} ", "value": k}
                                           for k, (label, _) in SCREENS.items()],
                                  style={"margin": "0.8em 0", "fontSize": 13}),
                    html.P(id="screener-caption"),
                    grid("screener-table", SCREENER_GRID_COLS, screener_rows(uni0, [])[0],
                         page_size=25, row_id="ticker"),
                ]),
                tab("Company detail", "company", [
                    dcc.Dropdown(id="company", options=options, value=first, clearable=False,
                                 placeholder="Pick a ticker", style={"width": "300px", "marginTop": "1em"}),
                    dcc.Graph(id="company-graph"),
                ]),
                tab("Sector heatmap", "heatmap", html.Div(views["heatmap"], id="view-heatmap")),
                tab("Bucket returns", "buckets", html.Div(views["buckets"], id="view-buckets")),
                tab("F-Score scatter", "scatter", html.Div(views["scatter"], id="view-scatter")),
                tab("Rolling spread", "rolling", html.Div(views["rolling"], id="view-rolling")),
                tab("Validation", "validation", html.Div(views["validation"], id="view-validation")),
                tab("Month explorer", "month", month_panel(*_month_options(uni0))),
                tab("Robustness", "robust", robustness_panel()),
                tab("Watchlist", "watch", watchlist_panel()),
                tab("Costs", "costs", costs_panel()),
                tab("All runs", "overview", [html.Div(overview_panel(bases), id="view-overview"),
                                             *compare_panel(bases)]),
                tab("Run pipeline", "pipeline", _pipeline_panel(uni0)),
            ]),
        ],
    )

    @app.callback(
        Output("title", "children"), Output("subtitle", "children"),
        Output("data-status", "children"), Output("survivorship", "options"),
        *[Output(f"view-{k}", "children") for k in DATA_TABS],
        Output("company", "options"), Output("company", "value"),
        Output("view-overview", "children"),
        Output("month-date", "options"), Output("month-date", "value"),
        Input("universe", "value"), Input("survivorship", "value"),
        Input("reload", "n_clicks"), Input("data-version", "data"),
        State("company", "value"), State("month-date", "value"),
        prevent_initial_call=True,
    )
    def _render(name, surv, _reload, _version, current, current_month):
        uni = resolve(name, surv)
        v = render_views(uni)
        opts, first_ticker = _company_options(uni)
        keep = current if any(o["value"] == current for o in opts) else first_ticker
        mopts, mfirst = _month_options(uni)
        mkeep = current_month if any(o["value"] == current_month for o in mopts) else mfirst
        return (f"Composite Fundamental Screener — {uni.name} ({uni.currency})",
                _subtitle(uni), artifact_status(uni),
                [{"label": " survivorship-corrected", "value": "on",
                  "disabled": not survivorship_supported(name)}],
                *[v[k] for k in DATA_TABS], opts, keep,
                overview_panel(bases), mopts, mkeep)

    @app.callback(Output("month-graph", "figure"), Output("month-summary", "children"),
                  Output("month-table", "rowData"),
                  Input("month-date", "value"), Input("universe", "value"),
                  Input("survivorship", "value"), Input("data-version", "data"))
    def _month(date, name, surv, _version):
        uni = resolve(name, surv)
        data = data_for(uni)
        if data is None or data[1] is None or "spread" not in data[1] or not date:
            return (go.Figure(layout=dict(title="No bucket returns for this universe", height=300)),
                    "Run the backtest for this universe first.", [])
        panel, dec = data[0], data[1]
        m = analysis.month_buckets(panel, date, uni.n_buckets)
        b = m["buckets"]

        def line(label):
            x = b.get(label)
            if not x:
                return f"{label}: empty"
            return (f"{x['bucket']}: {x['names']} names, mean {x['mean']:+.1%}, "
                    f"median {x['median']:+.1%}")

        summary = [html.B(f"{pd.Timestamp(date):%B %Y} — spread {m['spread']:+.1%}. "),
                   line("top"), html.Br(), line("bottom")]
        if not uni.backtestable:
            summary += [html.Br(), html.I("Descriptive only — this universe is not backtestable.")]
        return fig_month_spread(dec, date), summary, m["contributors"].to_dict("records")

    @app.callback(Output("month-date", "value", allow_duplicate=True),
                  Input("month-graph", "clickData"), prevent_initial_call=True)
    def _month_click(click):
        if not click or not click.get("points"):
            return no_update
        return f"{pd.Timestamp(click['points'][0]['x']):%Y-%m-%d}"

    @app.callback(Output("rob-table", "rowData"), Output("rob-graph", "figure"),
                  Output("rob-sector-graph", "figure"), Output("rob-sectors", "options"),
                  Input("rob-winsor", "value"), Input("rob-top", "value"),
                  Input("rob-bottom", "value"), Input("rob-exclude", "value"),
                  Input("rob-sectors", "value"),
                  Input("universe", "value"), Input("survivorship", "value"),
                  Input("data-version", "data"))
    def _robust(winsor, top, bottom, exclude, sectors, name, surv, _version):
        uni = resolve(name, surv)
        data = data_for(uni)
        empty = go.Figure(layout=dict(title="No bucket returns for this universe", height=300))
        if data is None or data[1] is None or "spread" not in data[1]:
            return [], empty, empty, []
        panel, dec = data[0], data[1]
        all_sectors = sorted(panel["sector"].dropna().unique())
        sectors = [x for x in (sectors or []) if x in all_sectors]
        tickers = [t for t in (exclude or "").split(",") if t.strip()]
        excl = (analysis.spread_excluding(panel, tickers, uni.n_buckets, sectors)
                if tickers or sectors else None)
        label = "Excluding " + ", ".join([t.strip().upper() for t in tickers] + sectors)
        table = analysis.robustness_table(dec["spread"], float(winsor or 0), int(top or 0),
                                          int(bottom or 0), excl, label)
        fig = go.Figure()
        base = dec["spread"].dropna()
        fig.add_trace(go.Scatter(x=base.index, y=(1 + base).cumprod() - 1, name="Baseline",
                                 line=dict(color="black", width=2)))
        if excl is not None and len(excl):
            fig.add_trace(go.Scatter(x=excl.index, y=(1 + excl.dropna()).cumprod() - 1, name=label))
        fig.update_layout(title="Cumulative composite spread", yaxis_tickformat=".0%", height=380,
                          legend=dict(orientation="h", y=-0.2))
        if not uni.backtestable:
            fig.update_layout(title="Cumulative composite spread [descriptive only — not a test]")
        return (table.to_dict("records"), fig, fig_sector_attribution(panel, uni.n_buckets),
                [{"label": x, "value": x} for x in all_sectors])

    @app.callback(Output("cost-summary", "children"), Output("cost-table", "rowData"),
                  Output("cost-graph", "figure"), Output("turnover-graph", "figure"),
                  Input("cost-bps", "value"), Input("universe", "value"),
                  Input("survivorship", "value"), Input("data-version", "data"))
    def _costs(bps, name, surv, _version):
        uni = resolve(name, surv)
        data = data_for(uni)
        empty = go.Figure(layout=dict(title="No bucket returns for this universe", height=300))
        if data is None or data[1] is None or "spread" not in data[1]:
            return "Run the backtest for this universe first.", [], empty, empty
        panel, dec = data[0], data[1]
        bps = float(bps or 0)
        turn = _turnover_cached(uni, _artifact_mtimes(uni))
        spread = dec["spread"].dropna()
        levels = sorted({0.0, 10.0, 25.0, 50.0, bps})
        table = analysis.cost_table(spread, turn, levels)
        be = analysis.breakeven_cost_bps(spread, turn)
        fail = analysis.dsr_fail_cost_bps(spread, turn)
        avg = turn.mean()
        summary = [
            html.B(f"Average one-way turnover per rebalance: top {avg['top']:.1%}, "
                   f"bottom {avg['bottom']:.1%}. "),
            html.Br(),
            ("Gross spread is already non-positive, so costs only deepen the loss."
             if np.isnan(be) else f"Mean net spread reaches zero at {be:.0f} bps one-way. "),
            ("" if np.isnan(fail) else
             f"Deflated Sharpe drops to 0.95 or below at {fail:.1f} bps one-way."
             if fail < 1000 else "Deflated Sharpe survives even at 1,000 bps one-way."),
        ]
        if not uni.backtestable:
            summary += [html.Br(), html.I("Descriptive only — this universe is not backtestable.")]
        net = analysis.net_of_costs(spread, turn, bps)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=spread.index, y=(1 + spread).cumprod() - 1, name="Gross",
                                 line=dict(color="black", width=2)))
        fig.add_trace(go.Scatter(x=net.index, y=(1 + net).cumprod() - 1, name=f"Net of {bps:g} bps"))
        fig.update_layout(title="Cumulative composite spread, gross vs net", yaxis_tickformat=".0%",
                          height=380, legend=dict(orientation="h", y=-0.2))
        tfig = go.Figure()
        for leg in ("top", "bottom"):
            tfig.add_trace(go.Scatter(x=turn.index, y=turn[leg], name=f"{leg} bucket", mode="lines"))
        tfig.update_layout(title="One-way turnover per rebalance", yaxis_tickformat=".0%", height=320,
                           legend=dict(orientation="h", y=-0.25))
        return summary, table.to_dict("records"), fig, tfig

    # The browser store loads its saved pins only after the initial
    # callbacks have run, so `modified_timestamp` is an Input: the picker is
    # filled again once the pins arrive. Until then (store is None) neither
    # callback touches the pins — otherwise the empty pre-load state would
    # be written back over them, wiping the watchlist on every reload.
    @app.callback(Output("watch-tickers", "options"), Output("watch-tickers", "value"),
                  Input("universe", "value"), Input("data-version", "data"),
                  Input("watch-store", "modified_timestamp"), State("watch-store", "data"))
    def _watch_options(name, _version, _ts, store):
        data = data_for(bases[name])
        if data is None:
            return [], []
        tickers = sorted(data[0]["ticker"].dropna().unique())
        opts = [{"label": t, "value": t} for t in tickers]
        if store is None:
            return opts, no_update
        valid = set(tickers)
        return opts, [t for t in store.get(name, []) if t in valid]

    @app.callback(Output("watch-store", "data"),
                  Input("watch-tickers", "value"), State("universe", "value"),
                  State("watch-store", "data"), prevent_initial_call=True)
    def _watch_save(tickers, name, store):
        tickers = tickers or []
        if (store or {}).get(name, []) == tickers:
            return no_update                 # nothing changed; avoid a write/re-fill loop
        return {**(store or {}), name: tickers}

    @app.callback(Output("watch-graph", "figure"), Output("watch-table", "rowData"),
                  Input("watch-tickers", "value"), Input("watch-metric", "value"),
                  Input("universe", "value"), Input("survivorship", "value"),
                  Input("data-version", "data"))
    def _watch(tickers, metric, name, surv, _version):
        uni = resolve(name, surv)
        data = data_for(uni)
        if data is None:
            return go.Figure(layout=dict(title="No scores panel for this universe", height=300)), []
        return fig_watchlist(data[0], tickers, metric, uni.n_buckets), watchlist_rows(data[0], tickers)

    @app.callback(Output("compare-graph", "figure"),
                  Input("compare-runs", "value"), Input("data-version", "data"))
    def _compare(keys, _version):
        runs = [r for r in analysis.available_runs(bases) if r["key"] in (keys or [])]
        return fig_compare(analysis.cumulative_spreads(runs))

    register_exports(app, GRID_IDS)

    @app.callback(Output("screener-table", "rowData"), Output("screener-caption", "children"),
                  Input("screens", "value"), Input("universe", "value"),
                  Input("survivorship", "value"), Input("data-version", "data"))
    def _screener(screens, name, surv, _version):
        return screener_rows(resolve(name, surv), screens)

    @app.callback(Output("company-graph", "figure"),
                  Input("company", "value"), Input("universe", "value"),
                  Input("survivorship", "value"), Input("data-version", "data"))
    def _company(ticker, name, surv, _version):
        data = data_for(resolve(name, surv))
        if data is None or not ticker:
            return go.Figure(layout=dict(title="No company selected", height=300))
        return fig_company_history(data[0], ticker)

    @app.callback(Output("company", "value", allow_duplicate=True), Output("tabs", "value"),
                  Input("screener-table", "cellClicked"), prevent_initial_call=True)
    def _row_click(cell):
        # Rows are keyed by ticker (row_id="ticker"), so the click reports it
        # directly — no lookup through sort/filter/page state.
        if not cell or not cell.get("rowId"):
            return no_update, no_update
        return cell["rowId"], "company"

    @app.callback(Output("pipe-preview", "children"),
                  Input("universe", "value"), Input("survivorship", "value"),
                  Input("pipe-steps", "value"), Input("pipe-limit", "value"))
    def _preview(name, surv, steps, limit):
        cmds = step_commands(name, steps or [], bool(surv), limit)
        if not cmds:
            return "Nothing to run — tick at least one step."
        return "\n".join(c.display() for c in cmds)

    @app.callback(Output("pipe-status", "children", allow_duplicate=True),
                  Input("pipe-run", "n_clicks"),
                  State("universe", "value"), State("survivorship", "value"),
                  State("pipe-steps", "value"), State("pipe-limit", "value"),
                  prevent_initial_call=True)
    def _run(_n, name, surv, steps, limit):
        cmds = step_commands(name, steps or [], bool(surv), limit)
        if not cmds:
            return "Nothing to run."
        try:
            RUNNER.start(f"{name}: {', '.join(s for s in STEPS if s in steps)}", cmds)
        except RuntimeError as e:
            return str(e)
        return "starting…"

    @app.callback(Output("pipe-status", "children", allow_duplicate=True),
                  Input("pipe-stop", "n_clicks"), prevent_initial_call=True)
    def _stop(_n):
        RUNNER.stop()
        return "stopping…"

    @app.callback(Output("pipe-log", "children"), Output("pipe-status", "children"),
                  Output("pipe-run", "disabled"), Output("data-version", "data"),
                  Output("job-seen", "data"),
                  Input("pipe-tick", "n_intervals"),
                  State("data-version", "data"), State("job-seen", "data"))
    def _poll(_n, version, seen):
        job = RUNNER.job
        if job is None:
            return "No pipeline run yet.", "", False, no_update, no_update
        elapsed = (job.finished or time.time()) - job.started
        status = f"{job.label} — {job.status} ({elapsed:.0f}s)"
        # Bump data-version exactly once per finished job so the results
        # tabs re-read the artifacts it wrote (also after a failure: earlier
        # steps may have succeeded).
        bump = job.finished is not None and seen != job.started
        return ("\n".join(job.lines), status, RUNNER.busy(),
                (version or 0) + 1 if bump else no_update,
                job.started if bump else no_update)

    return app


def main(argv=None) -> None:
    import argparse
    import threading
    import webbrowser

    p = argparse.ArgumentParser(description="Composite fundamental screener GUI")
    p.add_argument("--universe", default="sp500", choices=sorted(UNIVERSES))
    p.add_argument("--survivorship", action="store_true",
                   help="start in survivorship-corrected mode (sp500/kospi only)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8050)
    p.add_argument("--open", action="store_true", help="open the GUI in a browser tab")
    a = p.parse_args(argv)

    uni = get_universe(a.universe)
    if a.survivorship and survivorship_supported(a.universe):
        uni = uni.corrected()
    app = build_app(uni)
    url = f"http://{a.host}:{a.port}"
    print(f"Screener GUI on {url}  (Ctrl+C to quit)")
    if a.open:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    app.run(debug=False, host=a.host, port=a.port)


if __name__ == "__main__":
    main()
