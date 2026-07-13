"""Tests for the Brazil/CVM taxonomy adapter.

Fixtures mirror the REAL CVM Dados Abertos CSV structure verified against
actual 2023 DFP filings (column names, delimiter, sign conventions, and the
bank/COSIF code-collision case) — see cvm_br_client.py's module docstring
for the real-world example (Banco do Brasil's CD_CONTA "1.01" meaning "Caixa
e Equivalentes de Caixa" instead of "Ativo Circulante").
"""

from datetime import date

import pandas as pd
import pytest

from pit_fundamentals.cvm_br_client import CODE_MAP, extract_company_facts
from pit_fundamentals.query import get_fact_as_of
from pit_fundamentals.schema import connect, init_db

INDUSTRIAL_CNPJ = "11.111.111/0001-11"
BANK_CNPJ = "22.222.222/0001-22"


def _write_cvm_csv(path, rows: list[dict]):
    pd.DataFrame(rows).to_csv(path, sep=";", index=False, encoding="latin1")


def _bpa_row(cnpj, dt_refer, versao, ordem, dt_fim, cd_conta, ds_conta, valor):
    return dict(
        CNPJ_CIA=cnpj, DT_REFER=dt_refer, VERSAO=versao, DENOM_CIA="TESTCO",
        CD_CVM="000001", GRUPO_DFP="DF Consolidado - Balanço Patrimonial Ativo",
        MOEDA="REAL", ESCALA_MOEDA="MIL", ORDEM_EXERC=ordem, DT_FIM_EXERC=dt_fim,
        CD_CONTA=cd_conta, DS_CONTA=ds_conta, VL_CONTA=valor, ST_CONTA_FIXA="S",
    )


@pytest.fixture
def cvm_dir(tmp_path):
    """A minimal, real-shaped CVM extract directory for one fiscal year,
    with an industrial filer (classified balance sheet) and a bank filer
    (COSIF chart reusing the same codes for different accounts)."""
    year = 2023
    d = tmp_path

    # Index file: industrial has ONE filing; bank has a restated (VERSAO 2)
    # filing with a different receipt date — the real-world restatement case.
    _write_cvm_csv(
        d / f"dfp_cia_aberta_{year}.csv",
        [
            dict(CNPJ_CIA=INDUSTRIAL_CNPJ, DT_REFER="2023-12-31", VERSAO=1, DENOM_CIA="TESTCO",
                 CD_CVM="1", CATEG_DOC="DFP", ID_DOC=1, DT_RECEB="2024-02-01", LINK_DOC="x"),
            dict(CNPJ_CIA=BANK_CNPJ, DT_REFER="2023-12-31", VERSAO=1, DENOM_CIA="TESTBANK",
                 CD_CVM="2", CATEG_DOC="DFP", ID_DOC=2, DT_RECEB="2024-02-01", LINK_DOC="x"),
            dict(CNPJ_CIA=BANK_CNPJ, DT_REFER="2023-12-31", VERSAO=2, DENOM_CIA="TESTBANK",
                 CD_CVM="2", CATEG_DOC="DFP", ID_DOC=3, DT_RECEB="2024-04-15", LINK_DOC="x"),
        ],
    )

    # BPA_con: industrial has a proper classified balance sheet (current +
    # prior year). Bank's "1.01" is labeled "Caixa e Equivalentes de Caixa"
    # (cash), NOT "Ativo Circulante" — the real COSIF collision — across
    # both of its filed versions, with the restated version reporting a
    # different total assets figure.
    _write_cvm_csv(
        d / f"dfp_cia_aberta_BPA_con_{year}.csv",
        [
            _bpa_row(INDUSTRIAL_CNPJ, "2023-12-31", 1, "ÚLTIMO", "2023-12-31", "1", "Ativo Total", 1000.0),
            _bpa_row(INDUSTRIAL_CNPJ, "2023-12-31", 1, "PENÚLTIMO", "2022-12-31", "1", "Ativo Total", 900.0),
            _bpa_row(INDUSTRIAL_CNPJ, "2023-12-31", 1, "ÚLTIMO", "2023-12-31", "1.01", "Ativo Circulante", 400.0),
            _bpa_row(INDUSTRIAL_CNPJ, "2023-12-31", 1, "PENÚLTIMO", "2022-12-31", "1.01", "Ativo Circulante", 350.0),
            _bpa_row(BANK_CNPJ, "2023-12-31", 1, "ÚLTIMO", "2023-12-31", "1", "Ativo Total", 5000.0),
            _bpa_row(BANK_CNPJ, "2023-12-31", 1, "ÚLTIMO", "2023-12-31", "1.01", "Caixa e Equivalentes de Caixa", 200.0),
            _bpa_row(BANK_CNPJ, "2023-12-31", 2, "ÚLTIMO", "2023-12-31", "1", "Ativo Total", 5100.0),
            _bpa_row(BANK_CNPJ, "2023-12-31", 2, "ÚLTIMO", "2023-12-31", "1.01", "Caixa e Equivalentes de Caixa", 210.0),
        ],
    )
    # BPP_con/DRE_con/DFC_MI_con files are simply absent for this fixture —
    # extract_company_facts skips statement files that don't exist, exactly
    # as it would for a real filer missing one of the DFP sub-documents.

    _write_cvm_csv(
        d / f"dfp_cia_aberta_composicao_capital_{year}.csv",
        [
            dict(CNPJ_CIA=INDUSTRIAL_CNPJ, DT_REFER="2023-12-31", VERSAO=1, DENOM_CIA="TESTCO",
                 QT_ACAO_ORDIN_CAP_INTEGR=100, QT_ACAO_PREF_CAP_INTEGR=0, QT_ACAO_TOTAL_CAP_INTEGR=100,
                 QT_ACAO_ORDIN_TESOURO=0, QT_ACAO_PREF_TESOURO=0, QT_ACAO_TOTAL_TESOURO=10),
        ],
    )
    return d


def test_industrial_filer_maps_assets_and_current_assets(cvm_dir):
    from pit_fundamentals.cvm_br_client import load_filing_index, load_share_counts

    index = load_filing_index(cvm_dir, 2023)
    shares = load_share_counts(cvm_dir, 2023)
    facts = extract_company_facts(cvm_dir, 2023, INDUSTRIAL_CNPJ, "TEST3", index, shares)

    assets = facts[(facts["tag"] == "Assets") & (facts["fiscal_period_end"] == date(2023, 12, 31))]
    assert assets["value"].iloc[0] == 1_000_000.0  # MIL scale -> whole currency units
    current = facts[(facts["tag"] == "AssetsCurrent") & (facts["fiscal_period_end"] == date(2023, 12, 31))]
    assert current["value"].iloc[0] == 400_000.0
    prior_assets = facts[(facts["tag"] == "Assets") & (facts["fiscal_period_end"] == date(2022, 12, 31))]
    assert prior_assets["value"].iloc[0] == 900_000.0
    shares_row = facts[facts["tag"] == "CommonStockSharesOutstanding"]
    assert shares_row["value"].iloc[0] == 90.0  # 100 issued - 10 treasury


def test_bank_cosif_collision_excludes_mislabeled_current_assets(cvm_dir):
    """The load-bearing safety check: a bank's CD_CONTA '1.01' means 'Caixa
    e Equivalentes de Caixa', not 'Ativo Circulante' — must NOT be mapped to
    AssetsCurrent just because the code matches the industrial template."""
    from pit_fundamentals.cvm_br_client import load_filing_index, load_share_counts

    index = load_filing_index(cvm_dir, 2023)
    shares = load_share_counts(cvm_dir, 2023)
    facts = extract_company_facts(cvm_dir, 2023, BANK_CNPJ, "TESTB4", index, shares)

    # Assets (code "1", label matches) is accepted...
    assert (facts["tag"] == "Assets").any()
    # ...but AssetsCurrent must never appear for this bank at all.
    assert not (facts["tag"] == "AssetsCurrent").any()


def test_bank_restatement_pit_gating(cvm_dir):
    """The bank refiled (VERSAO 2) with a different Assets figure and a
    later DT_RECEB — get_fact_as_of must return the original before that
    date and the restated value after, exactly like the EDGAR case."""
    from pit_fundamentals.cvm_br_client import load_filing_index, load_share_counts

    index = load_filing_index(cvm_dir, 2023)
    shares = load_share_counts(cvm_dir, 2023)
    facts = extract_company_facts(cvm_dir, 2023, BANK_CNPJ, "TESTB4", index, shares)

    db = cvm_dir / "test.duckdb"
    con = connect(db)
    init_db(con)
    con.register("_f", facts)
    con.execute(
        """INSERT INTO pit_facts
           (cik, ticker, tag, fiscal_period_end, start_date, filed_date, value,
            unit, form, fy, fp, is_restatement, taxonomy)
           SELECT cik, ticker, tag, fiscal_period_end, start_date, filed_date, value,
                  unit, form, fy, fp, is_restatement, taxonomy FROM _f"""
    )
    con.close()

    fpe = date(2023, 12, 31)
    before = get_fact_as_of("TESTB4", "Assets", date(2024, 3, 1), fpe, db)
    after = get_fact_as_of("TESTB4", "Assets", date(2024, 5, 1), fpe, db)
    assert before == 5_000_000.0
    assert after == 5_100_000.0


def test_code_map_signs_cost_of_revenue_negative():
    """CVM stores DRE cost lines as negative values; the map must flip the
    sign so downstream gross_profit()/scores.py conventions (COGS positive)
    hold regardless of source taxonomy."""
    tag, _, sign = CODE_MAP[("DRE", "3.02")]
    assert tag == "CostOfRevenue"
    assert sign == -1.0


def test_code_map_prefers_direct_ebit_tag():
    tag, label, _ = CODE_MAP[("DRE", "3.05")]
    assert tag == "EBIT"
    assert "resultado antes do resultado financeiro" in label


def test_dfc_mi_statement_code_maps_operating_cash_flow(tmp_path):
    """Regression test for a real bug caught during manual verification:
    stmt.split("_")[0] on "DFC_MI_con" truncates to "DFC", which never
    matches CODE_MAP's ("DFC_MI", "6.01") key, silently dropping cash-flow
    facts for every filer. The statement code must be recovered by
    stripping the "_con"/"_ind" suffix, not by splitting on the first "_"."""
    d = tmp_path
    year = 2023
    _write_cvm_csv(
        d / f"dfp_cia_aberta_{year}.csv",
        [dict(CNPJ_CIA=INDUSTRIAL_CNPJ, DT_REFER="2023-12-31", VERSAO=1, DENOM_CIA="TESTCO",
              CD_CVM="1", CATEG_DOC="DFP", ID_DOC=1, DT_RECEB="2024-02-01", LINK_DOC="x")],
    )
    pd.DataFrame(
        [
            dict(CNPJ_CIA=INDUSTRIAL_CNPJ, DT_REFER="2023-12-31", VERSAO=1, DENOM_CIA="TESTCO",
                 CD_CVM="1", GRUPO_DFP="DF Consolidado - DFC (Método Indireto)", MOEDA="REAL",
                 ESCALA_MOEDA="MIL", ORDEM_EXERC="ÚLTIMO", DT_INI_EXERC="2023-01-01",
                 DT_FIM_EXERC="2023-12-31", CD_CONTA="6.01",
                 DS_CONTA="Caixa Líquido Atividades Operacionais", VL_CONTA=50.0, ST_CONTA_FIXA="S"),
        ]
    ).to_csv(d / f"dfp_cia_aberta_DFC_MI_con_{year}.csv", sep=";", index=False, encoding="latin1")
    pd.DataFrame(
        [dict(CNPJ_CIA=INDUSTRIAL_CNPJ, DT_REFER="2023-12-31", VERSAO=1, DENOM_CIA="TESTCO",
              QT_ACAO_ORDIN_CAP_INTEGR=1, QT_ACAO_PREF_CAP_INTEGR=0, QT_ACAO_TOTAL_CAP_INTEGR=1,
              QT_ACAO_ORDIN_TESOURO=0, QT_ACAO_PREF_TESOURO=0, QT_ACAO_TOTAL_TESOURO=0)]
    ).to_csv(d / f"dfp_cia_aberta_composicao_capital_{year}.csv", sep=";", index=False, encoding="latin1")

    from pit_fundamentals.cvm_br_client import load_filing_index, load_share_counts

    index = load_filing_index(d, year)
    shares = load_share_counts(d, year)
    facts = extract_company_facts(d, year, INDUSTRIAL_CNPJ, "TEST3", index, shares)
    cfo = facts[facts["tag"] == "NetCashProvidedByUsedInOperatingActivities"]
    assert len(cfo) == 1
    assert cfo["value"].iloc[0] == 50_000.0
    assert cfo["start_date"].iloc[0] == date(2023, 1, 1)
