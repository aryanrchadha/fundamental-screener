"""A single self-contained HTML snapshot of one run, for sharing or archiving.

The page embeds plotly.js once (so it opens offline) and every table as
plain HTML. It states which artifacts it was built from and when they were
written, and repeats the stale-validation warning if one applies — a report
read weeks later must say what it describes.
"""

from __future__ import annotations

import html
import time

import numpy as np
import pandas as pd
import plotly.io as pio

_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:1100px;margin:2em auto;
padding:0 16px;color:#222;background:#fff}
h1{margin-bottom:.2em}h2{margin-top:2em;border-bottom:1px solid #ddd;padding-bottom:.2em}
.meta{color:#666;font-size:14px}.warn{background:#fdecea;border:1px solid #e57373;padding:.8em 1em;margin:1em 0}
.note{background:#fff8e1;border:1px solid #e0c060;padding:.8em 1em;margin:1em 0;font-size:14px}
table{border-collapse:collapse;font-family:monospace;font-size:13px;margin:.6em 0;display:block;overflow-x:auto}
th,td{border:1px solid #ddd;padding:4px 8px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}tr.pass td{background:#e6f4ea;font-weight:bold}
"""

PCT_COLS = {"ann_return", "mean_spread", "annualized"}
NUM_COLS = {"nw_tstat", "dsr", "dsr_pvalue", "ann_sharpe", "skew", "kurtosis"}


def _fmt(col: str, v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if col in PCT_COLS:
        return f"{v:+.1%}"
    if col in NUM_COLS and isinstance(v, (int, float, np.number)):
        return f"{v:.3f}"
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))                   # counts/lags upcast to float by mixed-dtype rows
    return html.escape(str(v))


def _passes(v) -> bool:
    # pandas hands back numpy booleans, and `np.True_ is True` is False.
    return isinstance(v, (bool, np.bool_)) and bool(v)


def table_html(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    body = []
    for r in df.to_dict("records"):          # per-column dtypes, unlike iterrows' upcast row
        cls = ' class="pass"' if _passes(r.get("survives_95")) else ""
        body.append(f"<tr{cls}>" + "".join(f"<td>{_fmt(c, r[c])}</td>" for c in cols) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_report(title: str, subtitle: str, sections: list[tuple[str, list]],
                 artifacts: list[tuple[str, float]], warning: str | None = None) -> str:
    """`sections` is [(heading, [item, ...])] where an item is a plotly
    Figure, a DataFrame, or a string of plain text (escaped)."""
    parts = [f"<h1>{html.escape(title)}</h1>", f"<p class='meta'>{html.escape(subtitle)}</p>"]
    stamps = ", ".join(
        f"{html.escape(label)} {time.strftime('%Y-%m-%d %H:%M', time.localtime(t)) if t else 'missing'}"
        for label, t in artifacts)
    parts.append(f"<p class='meta'>Built {time.strftime('%Y-%m-%d %H:%M')} from: {stamps}.</p>")
    if warning:
        parts.append(f"<div class='warn'>{html.escape(warning)}</div>")
    first_fig = True
    for heading, items in sections:
        parts.append(f"<h2>{html.escape(heading)}</h2>")
        for item in items:
            if isinstance(item, pd.DataFrame):
                parts.append(table_html(item))
            elif isinstance(item, str):
                parts.append(f"<div class='note'>{html.escape(item)}</div>")
            elif item is not None:
                parts.append(pio.to_html(item, full_html=False, include_plotlyjs=first_fig,
                                         config={"displaylogo": False}))
                first_fig = False
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
            f"<body>{''.join(parts)}</body></html>")
