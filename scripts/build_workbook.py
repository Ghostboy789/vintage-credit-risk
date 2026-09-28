"""Builds excel/vintage_ecl_workbook.xlsx from the published artefacts, with live formulas.

Illustrative research workbook on the Freddie Mac Single-Family Loan-Level sample
(non-commercial research use). Every number traces to artefacts/{pd_models,lgd_ead,ecl}.json;
nothing here is fabricated. Aggregates only (>= 10 loans per published cell), per
docs/DATA_LICENCE.md.

Run: python scripts/build_workbook.py
"""

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from config import VINTAGE_DATA_ROOT

REPO_ROOT = Path(__file__).resolve().parent.parent  # this checkout, not VINTAGE_DATA_ROOT:
# artefacts/*.json are committed here too, but marts_out/ (dim_loan.parquet) only exists in the
# main checkout, and the workbook itself belongs in THIS checkout's excel/ so it gets committed
# on this branch rather than written into the main checkout's working tree.
ARTEFACTS = REPO_ROOT / "artefacts"
OUT_PATH = REPO_ROOT / "excel" / "vintage_ecl_workbook.xlsx"

INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")  # pale yellow: hand-entered / pulled inputs
CALC_FILL = PatternFill("solid", fgColor="DDEBF7")  # pale blue: live-formula outputs
HEADER_FONT = Font(bold=True)
TITLE_FONT = Font(bold=True, size=13)
CAVEAT_FONT = Font(italic=True, size=9, color="7F7F7F")

LATEST_DATE = "2026-03-01"  # ecl.json's most recent reporting_date


def load(name):
    with open(ARTEFACTS / name, encoding="utf-8") as f:
        return json.load(f)


def add_defined_name(wb, name, ref):
    wb.defined_names[name] = DefinedName(name, attr_text=ref)


def write_row(ws, row, values, fill=None, bold=False):
    for col, val in enumerate(values, start=1):
        c = ws.cell(row=row, column=col, value=val)
        if fill:
            c.fill = fill
        if bold:
            c.font = HEADER_FONT
    return row + 1


def autosize(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_inputs_sheet(wb, pd_models, lgd_ead, ecl, note_rate_pct, note_rate_n):
    ws = wb.active
    ws.title = "Inputs"
    ws["A1"] = "Vintage ECL workbook -- Inputs"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "US mortgages (Freddie Mac Single-Family Loan-Level sample, non-commercial research). "
        "Illustrative: demonstrates a portfolio-lifecycle IFRS 9 workflow, not a production model "
        "or regulatory submission."
    )
    ws["A2"].font = CAVEAT_FONT
    ws.merge_cells("A2:H2")
    ws["A3"] = (
        "Every number below is pulled from the project's published artefacts (pd_models.json, "
        "lgd_ead.json, ecl.json). Yellow cells are pulled inputs; blue cells are live formulas."
    )
    ws["A3"].font = CAVEAT_FONT
    ws.merge_cells("A3:H3")

    row = 5
    # --- PD term structure by grade (from ecl.json pd_term_structure) ---
    ws.cell(row=row, column=1, value="PD term structure by grade").font = HEADER_FONT
    row += 1
    row = write_row(ws, row, ["grade", "year", "marginal_pd", "cumulative_pd"], bold=True)
    pd_term_start = row
    for r in pd_models_term_rows(ecl):
        values = [r["grade"], r["year"], r["marginal_pd"]["value"], r["cumulative_pd"]["value"]]
        row = write_row(ws, row, values, fill=INPUT_FILL)
    pd_term_end = row - 1
    add_defined_name(wb, "PD_TERM_GRADE", f"Inputs!$A${pd_term_start}:$A${pd_term_end}")
    add_defined_name(wb, "PD_TERM_YEAR", f"Inputs!$B${pd_term_start}:$B${pd_term_end}")
    add_defined_name(wb, "PD_TERM_CUM", f"Inputs!$D${pd_term_start}:$D${pd_term_end}")
    row += 1

    # --- LGD by segment (overall + LTV band, from lgd_ead.json) ---
    ws.cell(row=row, column=1, value="LGD by segment (economic, net of MI)").font = HEADER_FONT
    row += 1
    row = write_row(ws, row, ["dimension", "segment", "lgd_economic", "n"], bold=True)
    lgd_start = row
    for seg in lgd_ead["lgd_segments"]:
        if seg["dimension"] in ("overall", "ltv_band"):
            lgd = seg["lgd_economic"]
            values = [seg["dimension"], seg["segment"], lgd["value"], lgd["n"]]
            row = write_row(ws, row, values, fill=INPUT_FILL)
    lgd_end = row - 1
    add_defined_name(wb, "LGD_SEGMENT", f"Inputs!$B${lgd_start}:$B${lgd_end}")
    add_defined_name(wb, "LGD_VALUE", f"Inputs!$C${lgd_start}:$C${lgd_end}")
    lgd_overall_row = next(
        r for r in range(lgd_start, lgd_end + 1) if ws.cell(row=r, column=1).value == "overall"
    )
    add_defined_name(wb, "LGD_OVERALL", f"Inputs!$C${lgd_overall_row}")
    row += 1

    # --- Discount rate ---
    ws.cell(row=row, column=1, value="Discount rate").font = HEADER_FONT
    row += 1
    ws.cell(row=row, column=1, value="Portfolio weighted-average note rate (real, aggregate)")
    c = ws.cell(row=row, column=2, value=note_rate_pct / 100)
    c.number_format = "0.000%"
    c.fill = INPUT_FILL
    add_defined_name(wb, "DISCOUNT_RATE", f"Inputs!$B${row}")
    ws.cell(row=row, column=3, value=f"n = {note_rate_n:,} loans, weighted by original UPB")
    ws.cell(row=row, column=3).font = CAVEAT_FONT
    row += 1
    ws.cell(row=row, column=1, value=(
        "The published ECL discounts each loan at its own note rate (CONTRACTS.md: "
        "discount_factor = (1+note_rate_pct/1200)^-months_to_resolution). The portfolio average "
        "above is used only in this workbook's illustrative sensitivity table, not in the "
        "reconciled ECL totals on the ECL sheet."
    )).font = CAVEAT_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    row += 2

    # --- Stage rules ---
    ws.cell(row=row, column=1, value="IFRS 9 stage rules").font = HEADER_FONT
    row += 1
    ws.cell(row=row, column=1, value="Stage 1: performing")
    row += 1
    ws.cell(row=row, column=1, value="Stage 2: 30+ days past due, or PD deterioration ratio >=")
    c = ws.cell(row=row, column=2, value=ecl["sicr"]["ratio_threshold"])
    c.fill = INPUT_FILL
    add_defined_name(wb, "SICR_RATIO", f"Inputs!$B${row}")
    ws.cell(row=row, column=3, value="or absolute PD increase >=")
    c = ws.cell(row=row, column=4, value=ecl["sicr"]["absolute_threshold"])
    c.number_format = "0.0%"
    c.fill = INPUT_FILL
    add_defined_name(wb, "SICR_ABSOLUTE", f"Inputs!$D${row}")
    row += 1
    ws.cell(row=row, column=1, value="Stage 3: defaulted")
    row += 2

    # --- Scenario weights ---
    ws.cell(row=row, column=1, value="Scenario weights").font = HEADER_FONT
    row += 1
    ws.cell(row=row, column=1, value=f"Source: {ecl['scenarios']['source']}").font = CAVEAT_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    row += 1
    row = write_row(ws, row, ["scenario", "weight"], bold=True)
    scen_start = row
    for s in ecl["scenarios"]["weights"]:
        c1 = ws.cell(row=row, column=1, value=s["scenario"])
        c1.fill = INPUT_FILL
        c2 = ws.cell(row=row, column=2, value=s["weight"])
        c2.number_format = "0%"
        c2.fill = INPUT_FILL
        row += 1
    scen_end = row - 1
    add_defined_name(wb, "SCENARIO_WEIGHT", f"Inputs!$B${scen_start}:$B${scen_end}")

    autosize(ws, [46, 14, 16, 16, 14, 10, 40, 10])
    return {
        "pd_term_rows": (pd_term_start, pd_term_end),
        "lgd_rows": (lgd_start, lgd_end),
    }


def pd_models_term_rows(ecl):
    # Deterministic order: grade A..G, year ascending -- matches ecl.json's own emission order,
    # sorted defensively so the workbook doesn't depend on artefact row order.
    grade_order = {g: i for i, g in enumerate("ABCDEFG")}
    return sorted(
        ecl["pd_term_structure"], key=lambda r: (grade_order.get(r["grade"], 99), r["year"])
    )


EXAMPLE_LOAN = {
    "fico": 705,
    "ltv_pct": 82,
    "dti_pct": 33,
    "rate_spread_pct": 0.15,
    "channel": "R",
    "property_type": "SF",
    "term_band": "181_240",
}

NUMERIC_FEATURES = ["fico", "ltv_pct", "dti_pct", "rate_spread_pct"]
CATEGORICAL_FEATURES = ["channel", "property_type", "term_band"]


def build_scorecard_sheet(wb, pd_models):
    ws = wb.create_sheet("Scorecard")
    ws["A1"] = "Scorecard -- points table and one worked example"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        f"{pd_models['scaling']['pd_label']}. Base score {pd_models['scaling']['base_score']}, "
        f"base odds {pd_models['scaling']['base_odds']}:1, PDO {pd_models['scaling']['pdo']}. "
        "Lookup uses INDEX/MATCH (not XLOOKUP), for compatibility with older Excel."
    )
    ws["A2"].font = CAVEAT_FONT
    ws.merge_cells("A2:H2")

    row = 4
    ws.cell(row=row, column=1, value="Points table").font = HEADER_FONT
    row += 1
    row = write_row(
        ws, row,
        ["feature", "bin", "lower", "match_key", "points"],
        bold=True,
    )
    table_start = row
    feature_ranges = {}
    for feat in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        rows = [
            p for p in pd_models["points_table"]
            if p["feature"] == feat and not p["is_missing_bin"]
        ]
        if feat in NUMERIC_FEATURES:
            rows = sorted(rows, key=lambda r: (r["lower"] is not None, r["lower"]))
            start = row
            for r in rows:
                lower = -1e15 if r["lower"] is None else r["lower"]
                write_row(ws, row, [feat, r["bin"], lower, "", r["points"]], fill=INPUT_FILL)
                row += 1
            end = row - 1
            feature_ranges[feat] = ("lower", start, end)
        else:
            start = row
            for r in rows:
                key = r["categories"][0] if r["categories"] else ""
                write_row(ws, row, [feat, r["bin"], "", key, r["points"]], fill=INPUT_FILL)
                row += 1
            end = row - 1
            feature_ranges[feat] = ("key", start, end)
    table_end = row - 1
    for feat, (kind, start, end) in feature_ranges.items():
        col = "C" if kind == "lower" else "D"
        rng = f"Scorecard!${col}${start}:${col}${end}"
        add_defined_name(wb, f"{feat.upper()}_{kind.upper()}", rng)
        add_defined_name(wb, f"{feat.upper()}_POINTS", f"Scorecard!$E${start}:$E${end}")
    row += 1

    # --- Grade cut-offs (ascending score_min, so MATCH type 1 works) ---
    ws.cell(row=row, column=1, value="Grades (ascending score)").font = HEADER_FONT
    row += 1
    row = write_row(ws, row, ["grade", "score_min", "pd_low", "pd_high"], bold=True)
    grade_start = row
    grades_asc = sorted(
        pd_models["grades"], key=lambda g: (g["score_min"] is None, g["score_min"] or -1e15)
    )
    for g in grades_asc:
        score_min = -1e15 if g["score_min"] is None else g["score_min"]
        write_row(ws, row, [g["grade"], score_min, g["pd_low"], g["pd_high"]], fill=INPUT_FILL)
        row += 1
    grade_end = row - 1
    add_defined_name(wb, "GRADE_SCORE_MIN", f"Scorecard!$B${grade_start}:$B${grade_end}")
    add_defined_name(wb, "GRADE_LETTER", f"Scorecard!$A${grade_start}:$A${grade_end}")
    row += 1

    # --- Worked example ---
    ws.cell(row=row, column=1, value="Example loan").font = HEADER_FONT
    row += 1
    example_rows = {}
    for feat in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        ws.cell(row=row, column=1, value=feat)
        c = ws.cell(row=row, column=2, value=EXAMPLE_LOAN[feat])
        c.fill = INPUT_FILL
        kind, start, end = feature_ranges[feat]
        match_col = "C" if kind == "lower" else "D"
        match_range = f"Scorecard!${match_col}${start}:${match_col}${end}"
        match_type = 1 if kind == "lower" else 0
        pts_range = f"Scorecard!$E${start}:$E${end}"
        formula = f"=INDEX({pts_range},MATCH(B{row},{match_range},{match_type}))"
        c2 = ws.cell(row=row, column=3, value=formula)
        c2.fill = CALC_FILL
        example_rows[feat] = row
        row += 1
    score_row = row
    ws.cell(row=row, column=1, value="Total score")
    sum_range = ",".join(f"C{r}" for r in example_rows.values())
    c = ws.cell(row=row, column=3, value=f"=SUM({sum_range})")
    c.fill = CALC_FILL
    c.font = HEADER_FONT
    row += 1
    ws.cell(row=row, column=1, value="Grade")
    c = ws.cell(
        row=row, column=3,
        value=f"=INDEX(GRADE_LETTER,MATCH(C{score_row},GRADE_SCORE_MIN,1))",
    )
    c.fill = CALC_FILL
    c.font = HEADER_FONT

    add_defined_name(wb, "EXAMPLE_SCORE", f"Scorecard!$C${score_row}")
    autosize(ws, [16, 22, 14, 14, 10])
    return table_start, table_end


def build_ecl_sheet(wb, ecl):
    ws = wb.create_sheet("ECL")
    ws["A1"] = f"ECL by grade x stage -- reporting date {LATEST_DATE}"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Aggregates only (every row is >= 10 loans). ECL and coverage are the published "
        "portfolio-level figures, loaded here and aggregated with live formulas (SUMIF). "
        "Confidence intervals reflect parameter uncertainty only (from repeated parameter draws), "
        "not model or sampling uncertainty."
    )
    ws["A2"].font = CAVEAT_FONT
    ws.merge_cells("A2:I2")

    row = 4
    headers = ["grade", "stage", "n_loans", "ead", "ecl", "ecl_ci_low", "ecl_ci_high", "coverage"]
    row = write_row(ws, row, headers, bold=True)
    data_start = row
    rows = [r for r in ecl["by_date"] if r["reporting_date"] == LATEST_DATE]
    rows = sorted(rows, key=lambda r: (r["grade"], r["stage"]))
    for r in rows:
        for col, val in enumerate(
            [r["grade"], r["stage"], r["n_loans"], r["ead"]["value"], r["ecl"]["value"],
             r["ecl"]["ci_low"], r["ecl"]["ci_high"]],
            start=1,
        ):
            c = ws.cell(row=row, column=col, value=val)
            c.fill = INPUT_FILL
        cov_formula = f"=E{row}/D{row}"
        c = ws.cell(row=row, column=8, value=cov_formula)
        c.number_format = "0.0000%"
        c.fill = CALC_FILL
        row += 1
    data_end = row - 1
    add_defined_name(wb, "ECL_GRADE", f"ECL!$A${data_start}:$A${data_end}")
    add_defined_name(wb, "ECL_STAGE", f"ECL!$B${data_start}:$B${data_end}")
    add_defined_name(wb, "ECL_EAD", f"ECL!$D${data_start}:$D${data_end}")
    add_defined_name(wb, "ECL_VALUE", f"ECL!$E${data_start}:$E${data_end}")
    row += 1

    # --- Totals: 12-month ECL (stage 1) and lifetime ECL (stage 2+3), by formula ---
    ws.cell(row=row, column=1, value="Portfolio totals").font = HEADER_FONT
    row += 1
    total_ead_row = row
    ws.cell(row=row, column=1, value="Total EAD")
    ws.cell(row=row, column=3, value="=SUM(ECL_EAD)").fill = CALC_FILL
    row += 1
    ecl_12m_row = row
    ws.cell(row=row, column=1, value="12-month ECL (stage 1)")
    c = ws.cell(row=row, column=3, value='=SUMIF(ECL_STAGE,"1",ECL_VALUE)')
    c.fill = CALC_FILL
    row += 1
    ecl_lifetime_row = row
    ws.cell(row=row, column=1, value="Lifetime ECL (stage 2 + 3)")
    lifetime_formula = '=SUMIF(ECL_STAGE,"2",ECL_VALUE)+SUMIF(ECL_STAGE,"3",ECL_VALUE)'
    c = ws.cell(row=row, column=3, value=lifetime_formula)
    c.fill = CALC_FILL
    row += 1
    total_ecl_row = row
    ws.cell(row=row, column=1, value="Total ECL")
    c = ws.cell(row=row, column=3, value=f"=C{ecl_12m_row}+C{ecl_lifetime_row}")
    c.fill = CALC_FILL
    c.font = HEADER_FONT
    row += 1
    coverage_row = row
    ws.cell(row=row, column=1, value="Portfolio coverage ratio")
    c = ws.cell(row=row, column=3, value=f"=C{total_ecl_row}/C{total_ead_row}")
    c.number_format = "0.0000%"
    c.fill = CALC_FILL
    row += 2

    add_defined_name(wb, "TOTAL_EAD", f"ECL!$C${total_ead_row}")
    add_defined_name(wb, "ECL_12M", f"ECL!$C${ecl_12m_row}")
    add_defined_name(wb, "ECL_LIFETIME", f"ECL!$C${ecl_lifetime_row}")
    add_defined_name(wb, "TOTAL_ECL", f"ECL!$C${total_ecl_row}")

    # --- Sensitivity table: illustrative LGD x PD multipliers on total ECL ---
    sens_title = ws.cell(row=row, column=1, value="Sensitivity: total ECL under LGD/PD multipliers")
    sens_title.font = HEADER_FONT
    row += 1
    ws.cell(row=row, column=1, value=(
        "Illustrative overlay only (Total ECL x PD multiplier x LGD multiplier). Not a re-run of "
        "the hazard/LGD model, and not part of the reconciled totals above."
    )).font = CAVEAT_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    row += 1
    mults = [0.8, 1.0, 1.2]
    header_row = row
    ws.cell(row=row, column=1, value="PD mult \\ LGD mult")
    for j, lm in enumerate(mults, start=2):
        ws.cell(row=row, column=j, value=lm).font = HEADER_FONT
    row += 1
    for pm in mults:
        ws.cell(row=row, column=1, value=pm).font = HEADER_FONT
        for j, lm in enumerate(mults, start=2):
            col_letter = get_column_letter(j)
            formula = f"=TOTAL_ECL*{pm}*{col_letter}${header_row}"
            c = ws.cell(row=row, column=j, value=formula)
            c.fill = CALC_FILL
        row += 1

    autosize(ws, [24, 10, 12, 16, 16, 16, 16, 16])
    return {
        "total_ecl_row": total_ecl_row,
        "ecl_12m_row": ecl_12m_row,
        "ecl_lifetime_row": ecl_lifetime_row,
        "coverage_row": coverage_row,
        "total_ead_row": total_ead_row,
    }


def build_summary_sheet(wb, ecl_rows_range):
    ws = wb.create_sheet("Summary")
    ws["A1"] = "Summary"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "US mortgages (Freddie Mac sample, non-commercial research). Illustrative workbook; "
        "the ECL intervals shown reflect parameter uncertainty only, not model or sampling risk."
    )
    ws["A2"].font = CAVEAT_FONT
    ws.merge_cells("A2:F2")

    row = 4
    ws.cell(row=row, column=1, value="Total EAD")
    ws.cell(row=row, column=2, value="=TOTAL_EAD").fill = CALC_FILL
    row += 1
    ws.cell(row=row, column=1, value="12-month ECL (stage 1)")
    ws.cell(row=row, column=2, value="=ECL_12M").fill = CALC_FILL
    row += 1
    ws.cell(row=row, column=1, value="Lifetime ECL (stage 2 + 3)")
    ws.cell(row=row, column=2, value="=ECL_LIFETIME").fill = CALC_FILL
    row += 1
    ws.cell(row=row, column=1, value="Total ECL")
    ws.cell(row=row, column=2, value="=TOTAL_ECL").fill = CALC_FILL
    row += 1
    ws.cell(row=row, column=1, value="Coverage ratio")
    c = ws.cell(row=row, column=2, value="=TOTAL_ECL/TOTAL_EAD")
    c.number_format = "0.0000%"
    c.fill = CALC_FILL
    row += 2

    # --- Stage mix (EAD by stage), for the chart ---
    ws.cell(row=row, column=1, value="Stage mix (EAD)").font = HEADER_FONT
    row += 1
    chart_header_row = row
    row = write_row(ws, row, ["stage", "ead"], bold=True)
    chart_start = row
    for stage in ("1", "2", "3"):
        ws.cell(row=row, column=1, value=f"Stage {stage}")
        c = ws.cell(row=row, column=2, value=f'=SUMIF(ECL_STAGE,"{stage}",ECL_EAD)')
        c.fill = CALC_FILL
        row += 1
    chart_end = row - 1

    chart = BarChart()
    chart.type = "col"
    chart.title = "Stage mix (EAD)"
    chart.y_axis.title = "EAD (USD)"
    data = Reference(ws, min_col=2, min_row=chart_header_row, max_row=chart_end)
    cats = Reference(ws, min_col=1, min_row=chart_start, max_row=chart_end)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws.add_chart(chart, "D4")

    autosize(ws, [26, 20])


def main():
    pd_models = load("pd_models.json")
    lgd_ead = load("lgd_ead.json")
    ecl = load("ecl.json")

    # Real, aggregate weighted-average note rate (n well above the 10-loan floor), computed from
    # marts_out/dim_loan.parquet for the Inputs sheet's discount-rate assumption.
    import duckdb

    con = duckdb.connect()
    dim_loan_path = VINTAGE_DATA_ROOT / "marts_out" / "dim_loan.parquet"
    n, wavg = con.execute(
        "select count(*) n, sum(note_rate_pct*original_upb)/sum(original_upb) as wavg "
        f"from read_parquet('{dim_loan_path.as_posix()}') "
        "where note_rate_pct is not null and original_upb is not null"
    ).fetchone()

    wb = Workbook()
    build_inputs_sheet(wb, pd_models, lgd_ead, ecl, wavg, n)
    build_scorecard_sheet(wb, pd_models)
    ecl_info = build_ecl_sheet(wb, ecl)
    build_summary_sheet(wb, ecl_info)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_PATH)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
