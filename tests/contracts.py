"""Contract checker for the dbt marts, model-output files and published JSON artefacts.

The specs in this module are the machine-readable form of CONTRACTS.md; a test keeps the two in
step. Any producer checks its output with one call and gets back a list of problems (empty means
the file follows the contract):

    from tests.contracts import check_mart, check_model_output, check_artefact
    problems = check_mart("fct_loan_month", path_to_parquet)

Parquet files are checked through DuckDB, so the real 75M-row loan-month mart is checked without
loading it into memory.
"""

import json
import math
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

SCHEMA_VERSION = "1.0"
SYNTHETIC_KEY = b"synthetic"  # Parquet file-metadata key set to b"true" on every fixture

# ---------------------------------------------------------------------------------------------
# Shared value sets
# ---------------------------------------------------------------------------------------------
DPD_BUCKETS = ["current", "dpd_30", "dpd_60", "dpd_90p", "reo", "unknown"]
SMA_CLASSES = ["standard_or_sma_0", "sma_1", "sma_2", "npa", "unknown"]
EXIT_TYPES = ["prepaid", "matured", "credit_event", "other_exit"]
AGE_BANDS = ["pre", "1_12", "13_24", "25_36", "37_60", "61_120", "121p"]
LTV_BANDS = ["le_60", "60_80", "80_90", "90_95", "gt_95", "missing"]
FICO_BANDS = ["lt_620", "620_659", "660_699", "700_739", "740_779", "ge_780", "missing"]
TERM_BANDS = ["le_180", "181_240", "gt_240"]
ECONOMIC_PERIODS = ["pre_crisis", "crisis", "recovery", "covid", "recent"]
SAMPLES = ["dev_train", "dev_test", "gap", "oot", "covid", "excluded"]
EXCLUSION_REASONS = ["harp", "indeterminate_exit", "window_incomplete"]
DEFAULT_TRIGGERS = ["dpd90", "reo", "credit_event_zbc"]
RESOLUTIONS = [
    "defect_settlement",
    "credit_event_loss",
    "paid_off",
    "other_exit",
    "cured_active",
    "open",
]
DISPOSITION_TYPES = [
    "third_party_sale",
    "short_sale_chargeoff",
    "reo_disposition",
    "whole_loan_sale",
    "paid_off",
]
ROLL_FROM = ["current", "dpd_30", "dpd_60", "dpd_90p", "reo"]
ROLL_TO = [
    "current",
    "dpd_30",
    "dpd_60",
    "dpd_90p",
    "reo",
    "unknown",
    "prepaid",
    "matured",
    "credit_event",
    "other_exit",
    "missing",
]
BEHAVIOUR_STATES = ["clean", "recent_dpd", "dpd_30", "dpd_60p", "default"]
STAGE_FLOOR_REASONS = [
    "default",
    "dpd30_backstop",
    "unknown_status",
    "forbearance",
    "assistance_plan",
    "cure_probation",
]
GRADES = ["A", "B", "C", "D", "E", "F", "G"]
SCENARIOS = ["final", "base", "adverse", "upside"]

# ---------------------------------------------------------------------------------------------
# Parquet specs: column -> (type, nullable) or (type, nullable, allowed values)
# Types: string, int, float, bool, date.
# ---------------------------------------------------------------------------------------------
MARTS: dict[str, dict] = {
    "dim_date": {
        "key": ["month"],
        "columns": {
            "month": ("date", False),
            "year": ("int", False),
            "quarter": ("int", False, [1, 2, 3, 4]),
            "year_quarter": ("string", False),
            "is_quarter_end": ("bool", False),
            "economic_period": ("string", False, ECONOMIC_PERIODS),
            "market_rate_pct": ("float", True),
            "market_rate_carried_forward": ("bool", False),
        },
    },
    "dim_loan": {
        "key": ["loan_id"],
        "columns": {
            "loan_id": ("string", False),
            "vintage_year": ("int", False),
            "vintage_quarter": ("string", False),
            "first_payment_date": ("date", False),
            "maturity_date": ("date", False),
            "original_upb": ("float", False),
            "original_loan_term": ("int", False),
            "term_band": ("string", False, TERM_BANDS),
            "note_rate_pct": ("float", False),
            "rate_spread_pct": ("float", True),
            "fico": ("int", True),
            "fico_band": ("string", False, FICO_BANDS),
            "ltv_pct": ("int", True),
            "ltv_band": ("string", False, LTV_BANDS),
            "cltv_pct": ("int", True),
            "dti_pct": ("int", True),
            "mi_pct": ("int", True),
            "number_of_units": ("int", True),
            "occupancy_status": ("string", True, ["P", "S", "I"]),
            "channel": ("string", True, ["R", "B", "C", "T"]),
            "loan_purpose": ("string", True, ["P", "C", "N"]),
            "property_type": ("string", True, ["SF", "PU", "CO", "MH", "CP"]),
            "property_state": ("string", False),
            "first_time_homebuyer": ("string", True, ["Y", "N"]),
            "number_of_borrowers": ("int", True),
            "super_conforming": ("bool", False),
            "harp_flag": ("bool", False),
            "last_period": ("date", False),
            "terminal_zero_balance_code": ("int", True, [1, 2, 3, 9, 15, 16, 96]),
            "exit_type": ("string", True, EXIT_TYPES),
            "defect_settlement_date": ("date", True),
        },
    },
    "fct_loan_month": {
        "key": ["loan_id", "period"],
        "columns": {
            "loan_id": ("string", False),
            "period": ("date", False),
            "vintage_year": ("int", False),
            "months_on_book": ("int", False),
            "age_band": ("string", False, AGE_BANDS),
            "current_upb": ("float", False),
            "interest_bearing_upb": ("float", True),
            "non_interest_bearing_upb": ("float", True),
            "current_rate_pct": ("float", True),
            "rate_incentive_pct": ("float", True),
            "dpd_status_raw": ("string", True),
            "dpd_bucket": ("string", False, DPD_BUCKETS),
            "sma_class": ("string", False, SMA_CLASSES),
            "forbearance_flag": ("bool", False),
            "assistance_plan": ("string", True, ["F", "R", "T"]),
            "payment_deferral": ("bool", False),
            "modified": ("bool", False),
            "eltv_pct": ("int", True),
            "default_exempt": ("bool", False),
            "default_trigger": ("bool", False),
            "is_first_default_month": ("bool", False),
            "in_default": ("bool", False),
            "is_cure_month": ("bool", False),
            "at_risk_at_start": ("bool", False),
            "recent_dpd30_12m": ("bool", False),
            "zero_balance_code": ("int", True, [1, 2, 3, 9, 15, 16, 96]),
            "exit_type": ("string", True, EXIT_TYPES),
            "removal_upb": ("float", True),
        },
    },
    "fct_default_events": {
        "key": ["loan_id", "definition"],
        "columns": {
            "loan_id": ("string", False),
            "definition": ("string", False, ["primary", "naive"]),
            "vintage_year": ("int", False),
            "default_period": ("date", False),
            "default_months_on_book": ("int", False),
            "default_trigger": ("string", False, DEFAULT_TRIGGERS),
            "ead": ("float", False),
            "forbearance_before_default": ("bool", False),
            "cure_period": ("date", True),
            "resolution": ("string", False, RESOLUTIONS),
            "resolution_period": ("date", True),
            "defect_settlement_date": ("date", True),
        },
    },
    "fct_loss_events": {
        "key": ["loan_id"],
        "columns": {
            "loan_id": ("string", False),
            "vintage_year": ("int", False),
            "default_period": ("date", False),
            "disposition_period": ("date", False),
            "months_to_resolution": ("int", False),
            "zero_balance_code": ("int", False, [1, 2, 3, 9, 15]),
            "disposition_type": ("string", False, DISPOSITION_TYPES),
            "ltv_band": ("string", False, LTV_BANDS),
            "property_state": ("string", False),
            "note_rate_pct": ("float", False),
            "ead": ("float", False),
            "removal_upb": ("float", False),
            "net_sales_proceeds": ("float", False),
            "mi_recoveries": ("float", False),
            "non_mi_recoveries": ("float", False),
            "legal_costs": ("float", False),
            "maintenance_and_preservation_costs": ("float", False),
            "taxes_and_insurance": ("float", False),
            "miscellaneous_expenses": ("float", False),
            "total_expenses": ("float", False),
            "delinquent_accrued_interest": ("float", False),
            "freddie_actual_loss": ("float", True),
            "computed_loss": ("float", False),
            "net_recovery": ("float", False),
            "discount_factor": ("float", False),
            "lgd_economic": ("float", False),
            "lgd_undiscounted": ("float", False),
            "lgd_gross_of_mi": ("float", False),
            "in_lgd_sample": ("bool", False),
        },
    },
    "fct_vintage_curve": {
        "key": ["vintage_quarter", "months_on_book"],
        "columns": {
            "vintage_year": ("int", False),
            "vintage_quarter": ("string", False),
            "months_on_book": ("int", False),
            "n_loans": ("int", False),
            "original_upb_total": ("float", False),
            "n_at_risk": ("int", False),
            "n_defaults": ("int", False),
            "cum_defaults": ("int", False),
            "cum_default_rate": ("float", False),
            "n_prepaid": ("int", False),
            "cum_prepaid": ("int", False),
            "net_loss": ("float", False),
            "cum_net_loss": ("float", False),
            "cum_loss_rate": ("float", False),
            "upb_outstanding": ("float", False),
            "fully_observed": ("bool", False),
        },
    },
    "fct_roll_rates": {
        "key": ["period", "vintage_year", "from_bucket", "from_forbearance", "to_state"],
        "columns": {
            "period": ("date", False),
            "vintage_year": ("int", False),
            "from_bucket": ("string", False, ROLL_FROM),
            "from_forbearance": ("bool", False),
            "to_state": ("string", False, ROLL_TO),
            "n_loans": ("int", False),
            "upb": ("float", False),
            "n_from": ("int", False),
            "roll_rate": ("float", False),
        },
    },
    "fct_scorecard_base": {
        "key": ["loan_id"],
        "columns": {
            "loan_id": ("string", False),
            "vintage_year": ("int", False),
            "vintage_quarter": ("string", False),
            "sample": ("string", False, SAMPLES),
            "exclusion_reason": ("string", True, EXCLUSION_REASONS),
            "default_12m": ("int", True, [0, 1]),
            "default_12m_naive": ("int", True, [0, 1]),
            "default_months_on_book": ("int", True),
            "prepaid_12m": ("bool", False),
            "fico": ("int", True),
            "ltv_pct": ("int", True),
            "cltv_pct": ("int", True),
            "dti_pct": ("int", True),
            "mi_pct": ("int", True),
            "rate_spread_pct": ("float", True),
            "note_rate_pct": ("float", False),
            "original_upb": ("float", False),
            "original_loan_term": ("int", False),
            "term_band": ("string", False, TERM_BANDS),
            "loan_purpose": ("string", True, ["P", "C", "N"]),
            "occupancy_status": ("string", True, ["P", "S", "I"]),
            "property_type": ("string", True, ["SF", "PU", "CO", "MH", "CP"]),
            "number_of_units": ("int", True),
            "channel": ("string", True, ["R", "B", "C", "T"]),
            "first_time_homebuyer": ("string", True, ["Y", "N"]),
            "super_conforming": ("bool", False),
            "number_of_borrowers": ("int", True),
            "property_state": ("string", False),
        },
    },
    "fct_stage_inputs": {
        "key": ["loan_id", "reporting_date"],
        "columns": {
            "loan_id": ("string", False),
            "reporting_date": ("date", False),
            "vintage_year": ("int", False),
            "months_on_book": ("int", False),
            "age_band": ("string", False, AGE_BANDS),
            "remaining_term": ("int", False),
            "current_upb": ("float", False),
            "interest_bearing_upb": ("float", True),
            "non_interest_bearing_upb": ("float", True),
            "note_rate_pct": ("float", False),
            "current_rate_pct": ("float", True),
            "rate_incentive_pct": ("float", True),
            "dpd_bucket": ("string", False, DPD_BUCKETS),
            "forbearance_flag": ("bool", False),
            "assistance_plan": ("string", True, ["F", "R", "T"]),
            "in_default": ("bool", False),
            "cured_within_6m": ("bool", False),
            "recent_dpd30_12m": ("bool", False),
            "modified": ("bool", False),
            "behaviour_state": ("string", False, BEHAVIOUR_STATES),
            "stage_floor": ("int", False, [1, 2, 3]),
            "stage_floor_reason": ("string", True, STAGE_FLOOR_REASONS),
            "ltv_band": ("string", False, LTV_BANDS),
            "eltv_pct": ("int", True),
            "property_state": ("string", False),
            "defaulted_before": ("bool", False),
            "default_next_12m": ("bool", True),
            "prepaid_next_12m": ("bool", True),
        },
    },
    "metrics_monthly": {
        "key": ["period"],
        "columns": {
            "period": ("date", False),
            "n_active_loans": ("int", False),
            "total_upb": ("float", False),
            "n_dpd30p": ("int", False),
            "upb_dpd30p": ("float", False),
            "n_dpd90p": ("int", False),
            "upb_dpd90p": ("float", False),
            "n_at_risk_start": ("int", False),
            "n_new_defaults": ("int", False),
            "n_prepaid": ("int", False),
            "upb_prepaid": ("float", False),
            "n_credit_event_exits": ("int", False),
            "net_loss": ("float", False),
            "delinquency_rate_30p": ("float", True),
            "delinquency_rate_90p": ("float", True),
            "default_rate": ("float", True),
            "loss_rate": ("float", True),
        },
    },
    "fct_ecl": {
        "key": ["reporting_date", "scenario", "grade", "stage"],
        "columns": {
            "reporting_date": ("date", False),
            "scenario": ("string", False, SCENARIOS),
            "grade": ("string", False, GRADES),
            "stage": ("int", False, [1, 2, 3]),
            "n_loans": ("int", False),
            "ead": ("float", False),
            "ecl": ("float", False),
            "in_sample": ("bool", False),
        },
    },
}

# Files written by the modelling code into models_out/ and read by other code (and, for
# ecl_results, loaded back into the warehouse as the source of fct_ecl).
MODEL_OUTPUTS: dict[str, dict] = {
    "loan_scores": {
        "key": ["loan_id"],
        "columns": {
            "loan_id": ("string", False),
            "sample": ("string", False, SAMPLES),
            "model_id": ("string", False),
            "score": ("int", True),
            "pd_12m": ("float", True),
            "grade": ("string", True, GRADES),
            "reason_1": ("string", True),
            "reason_2": ("string", True),
            "reason_3": ("string", True),
        },
    },
    "ecl_results": MARTS["fct_ecl"],
}

# ---------------------------------------------------------------------------------------------
# JSON artefact specs. Leaf types: "str", "int", "float", "bool", "date" (YYYY-MM-DD),
# "metric", "enum:a|b|c"; a trailing "?" allows null. A list spec [x] means a list of x.
# Keys are exact: missing and unexpected keys are both errors.
# ---------------------------------------------------------------------------------------------
RAG = "enum:green|amber|red"
RULE_RESULT = "enum:PASS|FAIL|AMBER|INSUFFICIENT|NOT_RUN|pending"
PASS_RULES = [{"rule_id": "str", "result": RULE_RESULT, "evidence": "str"}]
GRADE = "enum:" + "|".join(GRADES)
DEFINITION = "enum:primary|naive"
SECONDARY_OOT_SAMPLES = ["oot_2017_2019", "oot_2022_2024"]
DISCRIM_SAMPLE = "enum:dev_train|dev_test|oot|covid|oot_and_covid|" + "|".join(
    SECONDARY_OOT_SAMPLES
)
CALIB_SAMPLE = "enum:dev_test|oot|covid|oot_and_covid|" + "|".join(SECONDARY_OOT_SAMPLES)
STAGE2_REASONS = [r for r in STAGE_FLOOR_REASONS if r != "default"] + ["pd_deterioration"]

ENVELOPE = {
    "schema_version": "str",
    "artefact": "str",
    "synthetic": "bool",
    "generated_at": "str",
    "data_cutoff": "date",
    "code_version": "str",
    "suppressed_cells": "int",
}

ARTEFACTS: dict[str, dict] = {
    "portfolio": {
        **ENVELOPE,
        "summary": {
            "n_loans": "metric",
            "n_loan_months": "metric",
            "original_upb_total": "metric",
            "n_defaults_primary": "metric",
            "n_defaults_naive": "metric",
            "net_loss_total": "metric",
        },
        "comparable_months_on_book": "int",
        "vintage_curves": [
            {
                "vintage_year": "int",
                "vintage_quarter": "str",
                "months_on_book": "int",
                "fully_observed": "bool",
                "cum_default_rate": "metric",
                "cum_loss_rate": "metric",
            }
        ],
        "vintage_curves_annual": [
            {
                "vintage_year": "int",
                "months_on_book": "int",
                "fully_observed": "bool",
                "cum_default_rate": "metric",
                "cum_loss_rate": "metric",
            }
        ],
        "roll_rates": [
            {
                "period_group": "enum:all|" + "|".join(ECONOMIC_PERIODS),
                "from_bucket": "enum:" + "|".join(ROLL_FROM),
                "to_state": "enum:" + "|".join(ROLL_TO),
                "rate": "metric",
            }
        ],
        "roll_cure_rates": [
            {
                "period_group": "enum:all|" + "|".join(ECONOMIC_PERIODS),
                "from_bucket": "enum:dpd_30|dpd_60|dpd_90p",
                "rate": "metric",
            }
        ],
        "default_cure_rates": [
            {"default_year": "int", "cure_12m": "metric", "cure_ever": "metric"}
        ],
        "sma": [
            {
                "period": "date",
                "sma_class": "enum:" + "|".join(SMA_CLASSES),
                "upb": "metric",
                "share": "metric",
            }
        ],
        "prepayment": [{"period": "date", "cpr": "metric"}],
        "loss_drivers": [
            {
                "dimension": "str",
                "segment": "str",
                "default_rate": "metric",
                "loss_rate": "metric",
            }
        ],
        "default_definition_effect": [
            {
                "vintage_year": "int",
                "defaults_12m_primary": "metric",
                "defaults_12m_naive": "metric",
            }
        ],
        "reconciliation": [
            {
                "rule_id": "enum:R1|R2|R3|R4|R7|R8",
                "n_checked": "int",
                "n_outside_tolerance": "int",
                "max_abs_difference": "float",
            }
        ],
        "pass_rules": PASS_RULES,
    },
    "pd_models": {
        **ENVELOPE,
        "model_id": "str",
        "samples": [
            {
                "sample": "enum:" + "|".join(SAMPLES),
                "vintages": ["int"],
                "n_loans": "metric",
                "default_rate": "metric",
            }
        ],
        "exclusions": [
            {
                "reason": "enum:" + "|".join(EXCLUSION_REASONS),
                "sample_before_exclusion": "enum:dev_train|dev_test|gap|oot|covid|out_of_scope",
                "zero_balance_code": "int?",
                "n_loans": "metric",
            }
        ],
        "d1a": [
            {
                "sample": "enum:all|" + "|".join(SAMPLES),
                "modified_before_default": "metric",
                "primary_defaults": "metric",
                "ratio": "metric",
            }
        ],
        "scaling": {
            "base_score": "int",
            "base_odds": "float",
            "pdo": "int",
            "factor": "float",
            "offset": "float",
            "intercept": "float",
            "pd_label": "str",
        },
        "features": [
            {
                "feature": "str",
                "iv": "metric",
                "selected": "bool",
                "drop_reason": "str?",
                "coefficient": "float?",
            }
        ],
        "points_table": [
            {
                "feature": "str",
                "bin": "str",
                "lower": "float?",
                "upper": "float?",
                "categories": ["str"],
                "is_missing_bin": "bool",
                "woe": "float",
                "points": "int",
                "default_rate_dev_train": "metric",
            }
        ],
        "grades": [
            {
                "grade": GRADE,
                "pd_low": "float",
                "pd_high": "float",
                "score_min": "int?",
                "score_max": "int?",
                "merged_into": GRADE + "?",
            }
        ],
        "discrimination": [
            {
                "sample": DISCRIM_SAMPLE,
                "definition": DEFINITION,
                "model": "enum:champion|challenger",
                "auc": "metric",
                "gini": "metric",
                "ks": "metric",
            }
        ],
        "calibration": [
            {
                "sample": CALIB_SAMPLE,
                "definition": DEFINITION,
                "grade": GRADE,
                "n": "int",
                "mean_pd": "float",
                "realised_rate": "metric",
                "result": "enum:PASS|FAIL|INSUFFICIENT",
            }
        ],
        "calibration_in_the_large": [
            {
                "sample": CALIB_SAMPLE,
                "definition": DEFINITION,
                "mean_pd": "float",
                "realised_rate": "metric",
                "ratio": "metric",
            }
        ],
        "gini_drop": [
            {"definition": DEFINITION, "relative": "metric", "absolute": "metric", "rag": RAG}
        ],
        "fairness_sensitivity": [
            {
                "feature": "enum:number_of_borrowers|first_time_homebuyer",
                "in_model": "bool",
                "iv": "metric",
                "gini_dev_test_with": "metric",
                "gini_dev_test_without": "metric",
            }
        ],
        "challenger": {
            "status": "enum:not_run|run",
            "confirm_passed": "bool?",
            "delta_gini_oot": "metric?",
            "promotion_recommended": "bool?",
            "criteria": [{"criterion": "str", "met": "bool"}],
            "shap_global": [{"feature": "str", "mean_abs_shap": "float"}],
        },
        "oot_scoring": {"calls": "int", "scored_at": "str?"},
        "pass_rules": PASS_RULES,
    },
    "monitoring": {
        **ENVELOPE,
        "model_id": "str",
        "thresholds": {"stable_below": "float", "red_above": "float"},
        "score_psi": [{"comparison": "str", "n_bins": "int", "psi": "metric", "rag": RAG}],
        "csi": [{"feature": "str", "comparison": "str", "csi": "metric", "rag": RAG}],
    },
    "lgd_ead": {
        **ENVELOPE,
        "ead": {"ccf_applied": "bool", "mean_ead": "metric"},
        "lgd_segments": [
            {
                "dimension": "enum:overall|ltv_band|property_state|disposition_type|default_year",
                "segment": "str",
                "lgd_economic": "metric",
                "lgd_gross_of_mi": "metric",
                "lgd_undiscounted": "metric",
            }
        ],
        "downturn_lgd": [{"ltv_band": "str", "lgd_gross_of_mi": "metric"}],
        "resolution_mix": [
            {
                "default_year": "int",
                "resolution": "enum:" + "|".join(RESOLUTIONS),
                "n_defaults": "int",
                "share": "metric",
            }
        ],
        "sensitivities": [
            {
                "name": "enum:zero_loss_exclusions|open_workouts_p90",
                "status": "enum:run|not_needed",
                "lgd_economic": "metric?",
                "delta_vs_primary": "float?",
            }
        ],
        "lgd_distribution": {"share_above_1": "metric", "share_below_0": "metric"},
        "reconciliation": {
            "computed_vs_actual_within_1usd": "metric",
            "expenses_within_1usd": "metric",
        },
        "lgd_model": {"status": "enum:not_run|run", "used_in_ecl": "bool", "delta_mae": "metric?"},
        "pass_rules": PASS_RULES,
    },
    "ecl": {
        **ENVELOPE,
        "scenarios": {
            "used": "bool",
            "source": "str?",
            "weights": [{"scenario": "enum:base|adverse|upside", "weight": "float"}],
        },
        "sicr": {"ratio_threshold": "float", "absolute_threshold": "float"},
        "by_date": [
            {
                "reporting_date": "date",
                "in_sample": "bool",
                "stage": "enum:1|2|3",
                "grade": GRADE,
                "n_loans": "int",
                "ead": "metric",
                "ecl": "metric",
                "coverage": "metric",
            }
        ],
        "scenario_totals": [
            {
                "reporting_date": "date",
                "scenario": "enum:" + "|".join(SCENARIOS),
                "ecl": "metric",
            }
        ],
        "stage_migration": [
            {
                "from_date": "date",
                "to_date": "date",
                "from_stage": "enum:1|2|3",
                "to_stage": "enum:1|2|3|exited",
                "n": "int",
                "share": "metric",
            }
        ],
        "pd_term_structure": [
            {
                "grade": GRADE,
                "year": "int",
                "marginal_pd": "metric",
                "cumulative_pd": "metric",
            }
        ],
        "backtest": [
            {
                "reporting_date": "date",
                "grade": GRADE,
                "n": "int",
                "predicted_pd": "float",
                "realised_rate": "metric",
                "binomial_low": "float",
                "binomial_high": "float",
                "vasicek_low": "float",
                "vasicek_high": "float",
                "rag": RAG,
                "covid_affected": "bool",
            }
        ],
        "prepayment_backtest": [
            {
                "reporting_date": "date",
                "grade": GRADE,
                "n": "int",
                "predicted_rate": "float",
                "realised_rate": "metric",
            }
        ],
        "stage2_drivers": [
            {
                "reporting_date": "date",
                "reason": "enum:" + "|".join(STAGE2_REASONS),
                "n_loans": "int",
                "share_of_stage2": "metric",
            }
        ],
        "cured_population": [
            {
                "reporting_date": "date",
                "n_loans": "int",
                "ead": "metric",
                "ecl": "metric",
            }
        ],
        "hazard_inputs": {
            "market_rate_carried_forward_months": "int",
            "loan_months_without_market_rate": "int",
        },
        "pass_rules": PASS_RULES,
    },
    "capital": {
        **ENVELOPE,
        "status": "enum:not_run|run",
        "parameters": {
            "correlation": "float",
            "confidence": "float",
            "pd_floor": "float",
            "lgd_floor": "float",
            "lgd_basis": "str",
        },
        "reporting_date": "date?",
        "by_grade": [
            {
                "grade": GRADE,
                "n_loans": "int",
                "ead": "metric",
                "pd": "metric",
                "lgd": "metric",
                "k": "metric",
                "rwa": "metric",
                "capital": "metric",
                "ecl": "metric",
            }
        ],
        "totals": {"ead": "metric?", "rwa": "metric?", "capital": "metric?", "ecl": "metric?"},
        "limits": ["str"],
    },
}

METRIC_KEYS = {"value", "ci_low", "ci_high", "n", "ci_method"}

# Publication rule (VALIDATION_PLAN section 12): no published cell may describe 1 to 9 loans.
MIN_CELL = 10
CELL_COUNT_KEYS = ("n", "n_loans", "n_defaults")
SUPPRESSED = "none: suppressed, fewer than 10 loans"


# ---------------------------------------------------------------------------------------------
# Parquet checks
# ---------------------------------------------------------------------------------------------
def _arrow_kind(t) -> str:
    import pyarrow.types as pt

    if pt.is_string(t) or pt.is_large_string(t):
        return "string"
    if pt.is_boolean(t):
        return "bool"
    if pt.is_integer(t):
        return "int"
    if pt.is_floating(t):
        return "float"
    if pt.is_date32(t):
        return "date"
    return str(t)


def _sql_literal(v) -> str:
    return f"'{v}'" if isinstance(v, str) else str(v)


def check_parquet(spec: dict, path) -> list[str]:
    """Check one Parquet file against a spec from MARTS or MODEL_OUTPUTS."""
    path = Path(path)
    if not path.exists():
        return [f"{path.name}: file not found"]
    problems = []
    schema = pq.read_schema(path)
    actual = {f.name: _arrow_kind(f.type) for f in schema}
    expected = spec["columns"]
    for col, (typ, *_rest) in expected.items():
        if col not in actual:
            problems.append(f"{path.name}: missing column {col}")
        elif actual[col] != typ:
            problems.append(f"{path.name}: column {col} is {actual[col]}, contract says {typ}")
    for col in actual:
        if col not in expected:
            problems.append(f"{path.name}: unexpected column {col}")
    if problems:
        return problems

    src = f"read_parquet('{path.resolve().as_posix()}')"
    con = duckdb.connect()
    try:
        keys = ", ".join(spec["key"])
        dupes = con.execute(
            f"SELECT count(*) FROM (SELECT {keys} FROM {src} GROUP BY ALL HAVING count(*) > 1)"
        ).fetchone()[0]
        if dupes:
            problems.append(f"{path.name}: {dupes} duplicate key(s) on ({keys})")
        for col, (_typ, nullable, *allowed) in expected.items():
            if not nullable:
                nulls = con.execute(f"SELECT count(*) FROM {src} WHERE {col} IS NULL").fetchone()[0]
                if nulls:
                    problems.append(f"{path.name}: {nulls} null(s) in non-null column {col}")
            if allowed:
                values = ", ".join(_sql_literal(v) for v in allowed[0])
                bad = con.execute(
                    f"SELECT DISTINCT {col} FROM {src} WHERE {col} IS NOT NULL "
                    f"AND {col} NOT IN ({values}) LIMIT 5"
                ).fetchall()
                if bad:
                    problems.append(
                        f"{path.name}: {col} has values outside the contract: {[b[0] for b in bad]}"
                    )
    finally:
        con.close()
    return problems


def check_mart(name: str, path) -> list[str]:
    if name not in MARTS:
        return [f"{name}: not a mart in the contract"]
    return check_parquet(MARTS[name], path)


def check_model_output(name: str, path) -> list[str]:
    if name not in MODEL_OUTPUTS:
        return [f"{name}: not a model output in the contract"]
    return check_parquet(MODEL_OUTPUTS[name], path)


def parquet_is_synthetic(path) -> bool:
    meta = pq.read_schema(path).metadata or {}
    return meta.get(SYNTHETIC_KEY) == b"true"


# ---------------------------------------------------------------------------------------------
# JSON checks
# ---------------------------------------------------------------------------------------------
def _small_cell(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool) and 0 < n < MIN_CELL


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check_metric(v, where: str) -> list[str]:
    if not isinstance(v, dict):
        return [f"{where}: expected a metric object"]
    if set(v) != METRIC_KEYS:
        return [f"{where}: metric keys must be exactly {sorted(METRIC_KEYS)}, got {sorted(v)}"]
    out = []
    value, lo, hi, n, method = v["value"], v["ci_low"], v["ci_high"], v["n"], v["ci_method"]
    if not (isinstance(n, int) and not isinstance(n, bool) and n >= 0):
        out.append(f"{where}.n: must be a non-negative integer")
    elif _small_cell(n):
        out.append(f"{where}.n: {n} describes fewer than {MIN_CELL} loans (suppress or merge)")
    if not isinstance(method, str) or not method:
        out.append(f"{where}.ci_method: must be a non-empty string")
        return out
    if value is not None and not _is_number(value):
        out.append(f"{where}.value: must be a finite number or null")
    if (lo is None) != (hi is None):
        out.append(f"{where}: ci_low and ci_high must both be set or both be null")
    elif lo is None:
        if not method.startswith("none:"):
            out.append(
                f"{where}: no interval, so ci_method must start with 'none:' and give the reason"
            )
    else:
        if not (_is_number(lo) and _is_number(hi)):
            out.append(f"{where}: interval bounds must be finite numbers")
        elif value is None:
            out.append(f"{where}: an interval needs a value")
        elif not (lo - 1e-9 <= value <= hi + 1e-9):
            out.append(f"{where}: value {value} outside its interval [{lo}, {hi}]")
    return out


def _check(spec, v, where: str) -> list[str]:
    if isinstance(spec, dict):
        if not isinstance(v, dict):
            return [f"{where}: expected an object"]
        out = [f"{where}: missing key {k}" for k in spec if k not in v]
        out += [
            f"{where}.{k}: {v[k]} describes fewer than {MIN_CELL} loans (suppress or merge)"
            for k in CELL_COUNT_KEYS
            if spec.get(k) == "int" and _small_cell(v.get(k))
        ]
        out += [f"{where}: unexpected key {k}" for k in v if k not in spec]
        for k in spec:
            if k in v:
                out += _check(spec[k], v[k], f"{where}.{k}")
        return out
    if isinstance(spec, list):
        if not isinstance(v, list):
            return [f"{where}: expected a list"]
        out = []
        for i, item in enumerate(v):
            out += _check(spec[0], item, f"{where}[{i}]")
        return out
    nullable = spec.endswith("?")
    kind = spec.rstrip("?")
    if v is None:
        return [] if nullable else [f"{where}: must not be null"]
    if kind == "metric":
        return _check_metric(v, where)
    if kind.startswith("enum:"):
        allowed = kind[5:].split("|")
        return (
            []
            if str(v) in allowed and not isinstance(v, bool)
            else [f"{where}: {v!r} not one of {allowed}"]
        )
    ok = {
        "str": isinstance(v, str),
        "int": isinstance(v, int) and not isinstance(v, bool),
        "float": _is_number(v),
        "bool": isinstance(v, bool),
        "date": isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-",
    }.get(kind)
    if ok is None:
        return [f"{where}: unknown spec type {kind}"]
    return [] if ok else [f"{where}: expected {kind}, got {v!r}"]


def check_artefact(name: str, obj) -> list[str]:
    """Check an artefact dict (or a path to its JSON file) against ARTEFACTS[name]."""
    if name not in ARTEFACTS:
        return [f"{name}: not an artefact in the contract"]
    if isinstance(obj, (str, Path)):
        obj = json.loads(Path(obj).read_text(encoding="utf-8"))
    problems = _check(ARTEFACTS[name], obj, name)
    if isinstance(obj, dict):
        if obj.get("artefact") != name:
            problems.append(f"{name}.artefact: must be {name!r}")
        if obj.get("schema_version") != SCHEMA_VERSION:
            problems.append(f"{name}.schema_version: must be {SCHEMA_VERSION!r}")
    return problems


def metric(value, ci_low=None, ci_high=None, n=0, ci_method=None) -> dict:
    """Build a metric object. Without an interval, ci_method must say why ('none: ...')."""
    if ci_method is None:
        ci_method = "none: population count, not an estimate" if ci_low is None else "unspecified"
    return {"value": value, "ci_low": ci_low, "ci_high": ci_high, "n": n, "ci_method": ci_method}


def suppress_small_cells(obj) -> int:
    """Apply the small-cell rule to an artefact in place; return the number of cells suppressed.

    A metric with 1 to 9 loans becomes a null value with the reason in ci_method, and a list row
    whose n, n_loans or n_defaults is 1 to 9 is removed. Store the result in suppressed_cells.
    """
    count = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and set(v) == METRIC_KEYS and _small_cell(v["n"]):
                obj[k] = metric(None, n=0, ci_method=SUPPRESSED)
                count += 1
            else:
                count += suppress_small_cells(v)
    elif isinstance(obj, list):
        keep = [
            x
            for x in obj
            if not (isinstance(x, dict) and any(_small_cell(x.get(k)) for k in CELL_COUNT_KEYS))
        ]
        count += len(obj) - len(keep)
        obj[:] = keep
        for x in obj:
            count += suppress_small_cells(x)
    return count
