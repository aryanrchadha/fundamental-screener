"""Leading B3 (Brazil) blue-chip crosswalk: ticker -> CNPJ, sector.

CVM's Dados Abertos company registry has no B3 ticker field (it's CVM's own
regulatory ID system, keyed by CNPJ — Brazil's federal taxpayer ID for
legal entities), and there is no free, automated, complete ticker<->CNPJ
crosswalk API. So unlike the S&P 500 (pulled live from Wikipedia), this list
is a small, manually curated, and DOCUMENTED set of Ibovespa constituents —
every CNPJ below was verified against real 2023 CVM DFP filings before being
committed here, not guessed. Two banks (ITUB4, BBDC4) and one insurer-
adjacent holding co are deliberately included alongside industrials: they
exercise the financial-institution exclusion path in cvm_br_client (banks
use Brazil's COSIF chart of accounts, which reuses BPA/BPP account codes for
different line items — see cvm_br_client.py's module docstring).

This is a demonstration universe proving pit_fundamentals' second taxonomy
end-to-end, not a backtestable index — there's no free historical B3
constituent-membership table, no FX-adjusted return series wired up, and no
BRL/USD-aware backtest machinery in screener/backtest.py. Extending this to
a real BR backtest is future work (see README's international-data
limitations section).
"""

from __future__ import annotations

# ticker -> (CNPJ, GICS-equivalent sector, expected to pass or fail the
# classified-balance-sheet check)
BR_BLUE_CHIPS: dict[str, dict[str, str]] = {
    "PETR4": {"cnpj": "33.000.167/0001-01", "name": "Petrobras", "sector": "Energy"},
    "VALE3": {"cnpj": "33.592.510/0001-54", "name": "Vale", "sector": "Materials"},
    "ITUB4": {"cnpj": "60.872.504/0001-23", "name": "Itau Unibanco Holding", "sector": "Financials"},
    "BBDC4": {"cnpj": "60.746.948/0001-12", "name": "Banco Bradesco", "sector": "Financials"},
    "BBAS3": {"cnpj": "00.000.000/0001-91", "name": "Banco do Brasil", "sector": "Financials"},
    "ABEV3": {"cnpj": "07.526.557/0001-00", "name": "Ambev", "sector": "Consumer Staples"},
    "WEGE3": {"cnpj": "84.429.695/0001-11", "name": "WEG", "sector": "Industrials"},
    "B3SA3": {"cnpj": "09.346.601/0001-25", "name": "B3", "sector": "Financials"},
    "GGBR4": {"cnpj": "33.611.500/0001-19", "name": "Gerdau", "sector": "Materials"},
    "SUZB3": {"cnpj": "16.404.287/0001-55", "name": "Suzano", "sector": "Materials"},
    "RADL3": {"cnpj": "61.585.865/0001-51", "name": "Raia Drogasil", "sector": "Consumer Staples"},
    "EQTL3": {"cnpj": "03.220.438/0001-73", "name": "Equatorial Energia", "sector": "Utilities"},
    "RENT3": {"cnpj": "16.670.085/0001-55", "name": "Localiza Rent a Car", "sector": "Industrials"},
    "JBSS3": {"cnpj": "02.916.265/0001-60", "name": "JBS", "sector": "Consumer Staples"},
    "BBSE3": {"cnpj": "17.344.597/0001-94", "name": "BB Seguridade", "sector": "Financials"},
    "LREN3": {"cnpj": "92.754.738/0001-62", "name": "Lojas Renner", "sector": "Consumer Discretionary"},
}

# Known to file under COSIF (bank chart of accounts) rather than the
# industrial classified balance sheet — cvm_br_client's label-verification
# check excludes these automatically, but they're flagged here too so a
# caller can skip the doomed-to-fail ingest attempt if desired.
EXPECTED_COSIF_FILERS = {"ITUB4", "BBDC4", "BBAS3"}


def get_br_blue_chips() -> dict[str, str]:
    """Return {ticker: cnpj} for run_cvm_ingest()."""
    return {t: v["cnpj"] for t, v in BR_BLUE_CHIPS.items()}


def get_br_sectors() -> dict[str, str]:
    return {t: v["sector"] for t, v in BR_BLUE_CHIPS.items()}
