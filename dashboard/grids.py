"""AG Grid tables for the dashboard (replacing dash_table.DataTable, which
Dash has deprecated).

Every table in the GUI is built through `grid()` so they share one look and
the same behaviour: sortable, filterable columns, a CSV export button, and
numbers formatted on the client (d3-format) so the underlying values stay
full-precision — a 0.003% default probability is stored as 3e-5 and only
*displayed* rounded, which also keeps exported CSVs exact.
"""

from __future__ import annotations

import dash_ag_grid as dag
from dash import Input, Output, html

_FORMATS = {
    "pct1": ".1%",
    "pct3": ".3%",
    "num3": ".3f",
    "num1": ".1f",
}


def col(field: str, fmt: str | None = None, header: str | None = None, **kw) -> dict:
    """A column definition. `fmt` is a key of _FORMATS for numeric columns."""
    c = {"field": field, "headerName": header or field}
    if fmt:
        spec = _FORMATS[fmt]
        c.update(
            filter="agNumberColumnFilter",
            type="rightAligned",
            valueFormatter={"function": f"params.value == null ? '' : d3.format('{spec}')(params.value)"},
        )
    c.update(kw)
    return c


def row_rule(condition: str, **style) -> dict:
    """A conditional row style; `condition` is JavaScript over params.data."""
    return {"condition": condition, "style": style}


def grid(grid_id: str, columns: list[dict], rows: list | None = None, *, page_size: int | None = None,
         row_rules: list[dict] | None = None, row_id: str | None = None, height: int | None = None,
         export: bool = True) -> html.Div:
    """A table plus its export button. `row_id` names a field to use as each
    row's id (so a click reports e.g. the ticker rather than a row number);
    with no `page_size` the grid grows to fit its rows."""
    options = {"animateRows": False, "enableCellTextSelection": True}
    if page_size:
        options.update(pagination=True, paginationPageSize=page_size,
                       paginationPageSizeSelector=[page_size, 50, 100])
    if not height:
        options["domLayout"] = "autoHeight"
    kwargs = {}
    if row_id:
        kwargs["getRowId"] = f"params.data.{row_id}"
    if row_rules:
        kwargs["getRowStyle"] = {"styleConditions": row_rules}
    table = dag.AgGrid(
        id=grid_id,
        columnDefs=columns,
        rowData=rows or [],
        defaultColDef={"sortable": True, "filter": True, "floatingFilter": True,
                       "resizable": True, "minWidth": 90},
        columnSize="autoSize",               # fit content; scroll sideways when narrow
        dashGridOptions=options,
        csvExportParams={"fileName": f"{grid_id}.csv"},
        className="ag-theme-alpine",
        style={"height": f"{height}px"} if height else {"width": "100%"},
        **kwargs,
    )
    children = [table]
    if export:
        children.insert(0, html.Button("Export CSV", id=f"{grid_id}-export", n_clicks=0,
                                       style={"fontSize": 12, "marginBottom": "0.3em"}))
    return html.Div(children)


def register_exports(app, grid_ids) -> None:
    """One export callback per grid. Takes an explicit list because some
    grids exist only after a universe switch (e.g. Validation when the app
    starts on a screener-only universe), and a callback must be registered
    before the app starts serving."""
    for gid in grid_ids:
        app.callback(Output(gid, "exportDataAsCsv"), Input(f"{gid}-export", "n_clicks"),
                     prevent_initial_call=True)(lambda n: bool(n))
