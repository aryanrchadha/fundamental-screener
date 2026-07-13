"""Brazil / B3 fundamentals adapter: CVM Dados Abertos -> canonical PIT tags.

WHY BRAZIL, OF THE "LEADING EMERGING MARKETS": SEC EDGAR has no local-market
equivalent for India (NSE/BSE), China (SSE/SZSE), or South Africa (JSE) that
is both free and structured — their regulators either charge for bulk
fundamentals access or only publish unstructured filings (scanned PDFs,
HTML tables meant for humans). Brazil's CVM (Comissão de Valores Mobiliários
— the SEC's direct counterpart) runs "Dados Abertos", a public, no-key-
required open-data portal that publishes every listed company's standardized
annual financial statements (DFP filings) as structured, machine-readable
CSVs, going back to 2010 (when Brazil fully adopted IFRS). It is the closest
free analogue to EDGAR available for a leading EM exchange, which is why it
was chosen over the alternatives. (South Korea's DART system is the next-
best candidate — also free, but requires registering for an API key, which
would need the same "optional, degrades gracefully if unset" treatment this
project already gives FMP. Left as future work — see README.)

WHAT'S DIFFERENT FROM SEC EDGAR, AND HOW THIS ADAPTER HANDLES IT:

1. No XBRL tags — CVM uses its own fixed hierarchical account-code system
   ("Plano de Contas": CD_CONTA, e.g. "1.01" = Ativo Circulante). Codes are
   fixed by *position* in the standard chart of accounts, not globally
   unique names, so this module maps (statement, CD_CONTA) pairs to the
   same canonical tags used everywhere else in pit_fundamentals (Assets,
   AssetsCurrent, NetIncomeLoss, ...) so screener/scores.py runs UNMODIFIED
   on Brazilian data.
2. Financial institutions (banks) file under Brazil's COSIF chart of
   accounts, which reuses the SAME numeric codes for entirely different
   line items — e.g. code "1.01" means "Ativo Circulante" (current assets)
   for an industrial filer but "Caixa e Equivalentes de Caixa" (cash) for a
   bank. Blindly trusting the code would silently produce wrong numbers.
   This adapter verifies each row's DS_CONTA (account description) against
   the expected label before accepting it, and drops (logs, never
   fabricates) any company whose labels don't match the industrial
   template — mirroring how the US path excludes financials for lacking a
   classified balance sheet, just detected differently.
3. There's no per-fact filing timestamp the way EDGAR's `filed` field
   works — but CVM's DFP index file (one row per submitted document) has
   `DT_RECEB` ("date received" by CVM), which plays exactly that role, and
   `VERSAO` numbers amendments/restatements of the same fiscal year (a
   later VERSAO is a real re-filing, e.g. a 10-K/A equivalent). This
   adapter joins line-item rows to the index on (CNPJ, DT_REFER, VERSAO) to
   attach DT_RECEB as `filed_date`.
4. Each DFP submission reports BOTH the current fiscal year (ORDEM_EXERC =
   'ÚLTIMO') and the prior year (ORDEM_EXERC = 'PENÚLTIMO') as comparatives
   in the same document — both become public on the same filed_date, which
   this adapter records directly rather than needing a second snapshot
   query offset.
5. CVM's DRE (income statement) includes a directly-tagged EBIT-equivalent
   line (code 3.05, "Resultado Antes do Resultado Financeiro e dos
   Tributos" — literally "result before financial result and taxes"),
   which is MORE precise than the US-GAAP path's NetIncomeLoss+tax+interest
   approximation. screener/scores.altman_z prefers a canonical 'EBIT' tag
   when present and only falls back to the approximation otherwise.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
import requests_cache

log = logging.getLogger(__name__)

DFP_ZIP_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip"

# (statement file infix, CD_CONTA) -> (canonical tag, expected DS_CONTA
# substring for verification, sign multiplier). The label check is what
# catches the bank/COSIF case: if a company's account at this code isn't
# actually labeled what the industrial chart of accounts expects, the value
# is dropped rather than silently mismapped.
CODE_MAP: dict[tuple[str, str], tuple[str, str, float]] = {
    ("BPA", "1"): ("Assets", "ativo total", 1.0),
    ("BPA", "1.01"): ("AssetsCurrent", "ativo circulante", 1.0),
    ("BPP", "2.01"): ("LiabilitiesCurrent", "passivo circulante", 1.0),
    ("BPP", "2.02.01"): ("LongTermDebtNoncurrent", "empr", 1.0),  # "Empréstimos e Financiamentos"
    ("BPP", "2.03"): ("StockholdersEquity", "patrim", 1.0),
    ("BPP", "2.03.05"): ("RetainedEarningsAccumulatedDeficit", "lucros/preju", 1.0),
    ("DRE", "3.01"): ("Revenues", "receita de venda", 1.0),
    ("DRE", "3.02"): ("CostOfRevenue", "custo dos bens", -1.0),  # CVM stores costs as negative
    ("DRE", "3.03"): ("GrossProfit", "resultado bruto", 1.0),
    ("DRE", "3.05"): ("EBIT", "resultado antes do resultado financeiro", 1.0),
    ("DRE", "3.11"): ("NetIncomeLoss", "lucro/preju", 1.0),
    ("DFC_MI", "6.01"): ("NetCashProvidedByUsedInOperatingActivities", "caixa l", 1.0),
    ("DFC_MD", "6.01"): ("NetCashProvidedByUsedInOperatingActivities", "caixa l", 1.0),
}

STATEMENT_FILES = ["BPA_con", "BPP_con", "DRE_con", "DFC_MI_con", "DFC_MD_con"]


def _strip_accents_lower(s: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )


def download_dfp_year(
    year: int, cache_path: str = "data/http_cache", cache_ttl: int = 180 * 86400
) -> Path:
    """Download (or reuse the cached copy of) one year's DFP zip and extract
    it to a local scratch directory, returning that directory's path."""
    session = requests_cache.CachedSession(cache_path, backend="sqlite", expire_after=cache_ttl)
    url = DFP_ZIP_URL.format(year=year)
    resp = session.get(url, timeout=120)
    resp.raise_for_status()
    extract_dir = Path("data") / "cvm_br" / str(year)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(extract_dir)
    return extract_dir


def _read_cvm_csv(path: Path) -> pd.DataFrame:
    # CD_CONTA/CNPJ_CIA must stay strings: a CD_CONTA column containing only
    # whole-number-looking codes in a given slice (e.g. a small test fixture,
    # or a company with no sub-account rows) can otherwise be inferred as
    # float64, turning "1" into "1.0" and silently breaking every CODE_MAP
    # lookup for that filer.
    return pd.read_csv(
        path, sep=";", encoding="latin1", decimal=".", low_memory=False,
        dtype={"CD_CONTA": str, "CNPJ_CIA": str},
    )


def load_filing_index(extract_dir: Path, year: int) -> pd.DataFrame:
    """The per-submission index file: (CNPJ, DT_REFER, VERSAO) -> DT_RECEB
    (the actual filing/receipt date — CVM's analogue of EDGAR's `filed`)."""
    df = _read_cvm_csv(extract_dir / f"dfp_cia_aberta_{year}.csv")
    df["DT_RECEB"] = pd.to_datetime(df["DT_RECEB"]).dt.date
    return df[["CNPJ_CIA", "DT_REFER", "VERSAO", "DT_RECEB"]]


def load_share_counts(extract_dir: Path, year: int) -> pd.DataFrame:
    """Shares outstanding = total capital shares (ON + PN) minus treasury
    shares, from the composicao_capital file (one row per company, no
    CD_CONTA — this file doesn't go through the generic code mapper)."""
    df = _read_cvm_csv(extract_dir / f"dfp_cia_aberta_composicao_capital_{year}.csv")
    df["shares_outstanding"] = df["QT_ACAO_TOTAL_CAP_INTEGR"] - df["QT_ACAO_TOTAL_TESOURO"]
    return df[["CNPJ_CIA", "DT_REFER", "VERSAO", "shares_outstanding"]]


def extract_company_facts(
    extract_dir: Path, year: int, cnpj: str, ticker: str, index: pd.DataFrame, shares: pd.DataFrame
) -> pd.DataFrame:
    """Pull one company's canonical facts out of one year's DFP dataset.

    Returns rows in the same schema as the US-GAAP ingester's output
    (extract_facts in ingest.py) so both can be inserted with one INSERT.
    """
    rows: list[dict] = []
    for stmt in STATEMENT_FILES:
        path = extract_dir / f"dfp_cia_aberta_{stmt}_{year}.csv"
        if not path.exists():
            continue
        df = _read_cvm_csv(path)
        df = df[df["CNPJ_CIA"] == cnpj]
        if df.empty:
            continue
        # Strip the trailing "_con"/"_ind" scope suffix to get the statement
        # code CODE_MAP is keyed on. A plain split("_")[0] would truncate
        # "DFC_MI_con" to "DFC", silently dropping every DFC_MI/DFC_MD match.
        stmt_code = stmt.removesuffix("_con").removesuffix("_ind")
        for _, r in df.iterrows():
            key = (stmt_code, str(r["CD_CONTA"]))
            mapped = CODE_MAP.get(key)
            if mapped is None:
                continue
            tag, expected_label, sign = mapped
            actual_label = _strip_accents_lower(str(r["DS_CONTA"]))
            if expected_label not in actual_label:
                # Bank/COSIF chart reuses this code for something else —
                # exclude rather than fabricate a wrong value (see module
                # docstring point 2).
                log.info(
                    "%s: CD_CONTA %s labeled %r (expected %r) — likely a "
                    "non-industrial chart of accounts, skipping this tag",
                    ticker, r["CD_CONTA"], r["DS_CONTA"], expected_label,
                )
                continue
            filed_row = index[
                (index["CNPJ_CIA"] == cnpj)
                & (index["DT_REFER"] == r["DT_REFER"])
                & (index["VERSAO"] == r["VERSAO"])
            ]
            if filed_row.empty:
                continue
            filed_date = filed_row["DT_RECEB"].iloc[0]
            fiscal_period_end = datetime.strptime(r["DT_FIM_EXERC"], "%Y-%m-%d").date()
            # DRE/DFC (income statement, cash flow) are DURATION facts and
            # carry DT_INI_EXERC; BPA/BPP (balance sheet) are INSTANT facts
            # and have no start date — mirrors the US-GAAP ingester's
            # start_date=None-for-instant-facts convention exactly, so
            # query.py's annual-duration filter (>=300 days) works
            # identically regardless of taxonomy.
            start_date = (
                datetime.strptime(r["DT_INI_EXERC"], "%Y-%m-%d").date()
                if "DT_INI_EXERC" in r and pd.notna(r["DT_INI_EXERC"])
                else None
            )
            rows.append(
                {
                    "cik": cnpj,
                    "ticker": ticker,
                    "tag": tag,
                    "fiscal_period_end": fiscal_period_end,
                    "start_date": start_date,
                    "filed_date": filed_date,
                    "value": float(r["VL_CONTA"]) * sign * 1000.0,  # ESCALA_MOEDA=MIL -> whole currency units
                    "unit": "BRL",
                    "form": "DFP",
                    "fy": fiscal_period_end.year,
                    "fp": "FY",
                    "taxonomy": "cvm-br",
                }
            )

    # Shares outstanding: separate flat file, one row per (CNPJ, DT_REFER, VERSAO).
    sh = shares[shares["CNPJ_CIA"] == cnpj]
    idx_this = index[index["CNPJ_CIA"] == cnpj]
    merged = sh.merge(idx_this, on=["CNPJ_CIA", "DT_REFER", "VERSAO"], how="inner")
    for _, r in merged.iterrows():
        fiscal_period_end = datetime.strptime(r["DT_REFER"], "%Y-%m-%d").date()
        rows.append(
            {
                "cik": cnpj,
                "ticker": ticker,
                "tag": "CommonStockSharesOutstanding",
                "fiscal_period_end": fiscal_period_end,
                "start_date": None,
                "filed_date": r["DT_RECEB"],
                "value": float(r["shares_outstanding"]),
                "unit": "shares",
                "form": "DFP",
                "fy": fiscal_period_end.year,
                "fp": "FY",
                "taxonomy": "cvm-br",
            }
        )

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = out.sort_values(["tag", "fiscal_period_end", "filed_date"])
    first_filing = out.groupby(["tag", "fiscal_period_end"], dropna=False)["filed_date"].transform("min")
    out["is_restatement"] = out["filed_date"] > first_filing
    return out


def run_cvm_ingest(
    tickers_cnpj: dict[str, str],
    years: list[int],
    db_path: str,
    cache_path: str = "data/http_cache",
) -> None:
    """Ingest CVM DFP data for a Brazil ticker->CNPJ crosswalk across the
    given years into the shared PIT database. Ticker namespaces never
    collide with US-GAAP tickers (e.g. "PETR4" vs "AAPL"), so both taxonomies
    coexist in the same pit_facts table without special-casing queries.
    """
    from pit_fundamentals.schema import connect, init_db

    con = connect(db_path)
    init_db(con)
    total = 0
    for year in years:
        log.info("Downloading CVM DFP data for %d ...", year)
        extract_dir = download_dfp_year(year, cache_path=cache_path)
        index = load_filing_index(extract_dir, year)
        shares = load_share_counts(extract_dir, year)
        for ticker, cnpj in tickers_cnpj.items():
            facts = extract_company_facts(extract_dir, year, cnpj, ticker, index, shares)
            if facts.empty:
                log.warning("%s (%s): no facts extracted for %d", ticker, cnpj, year)
                continue
            con.execute("DELETE FROM pit_facts WHERE cik = ? AND fy = ? AND taxonomy = 'cvm-br'", [cnpj, year])
            con.register("_staging_br", facts)
            con.execute(
                """INSERT INTO pit_facts
                   (cik, ticker, tag, fiscal_period_end, start_date, filed_date,
                    value, unit, form, fy, fp, is_restatement, taxonomy)
                   SELECT cik, ticker, tag, fiscal_period_end, start_date, filed_date,
                          value, unit, form, fy, fp, is_restatement, taxonomy
                   FROM _staging_br"""
            )
            con.unregister("_staging_br")
            total += len(facts)
            log.info("%s (%s): %d facts loaded for %d", ticker, cnpj, len(facts), year)
    con.close()
    log.info("CVM ingest complete: %d fact rows across %d tickers, %d years",
             total, len(tickers_cnpj), len(years))
