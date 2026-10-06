"""The shareable HTML report: what it says about the data it was built from."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dashboard.report import build_report, table_html


def test_table_marks_passing_rows_even_with_numpy_booleans():
    df = pd.DataFrame({"scenario": ["a", "b", "c"], "months": [167, 165, 160],
                       "ann_return": [0.132, -0.01, np.nan], "survives_95": np.array([True, False, None])})
    out = table_html(df)
    assert out.count('class="pass"') == 1
    assert "<td>167</td>" in out and "167.0" not in out          # counts stay integers
    assert "+13.2%" in out and "-1.0%" in out


def test_report_embeds_plotly_once_and_states_its_sources():
    figs = [go.Figure(go.Scatter(x=[1, 2], y=[3, 4])) for _ in range(3)]
    page = build_report("T <x>", "sub", [("Charts", figs), ("Note", ["a & b"])],
                        [("Scores panel", 1.7e9), ("Validation", 0.0)], warning="Stale: Validation")
    assert page.count("plotly.js v") == 1                       # library inlined once, works offline
    assert "T &lt;x&gt;" in page and "a &amp; b" in page        # text is escaped
    assert "Validation missing" in page and "Stale: Validation" in page
