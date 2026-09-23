"""House-price covariate and macro scenarios (VALIDATION_PLAN E6).

Source: FHFA House Price Index master file, https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv,
series hpi_type = traditional, hpi_flavor = purchase-only, frequency = monthly,
place_id = USA (United States), column index_sa (seasonally adjusted). Its location is read from
the VINTAGE_HPI_CSV environment variable; without it the scenarios are not run.

Months are integers: year * 12 + month - 1.
"""

import numpy as np
import pandas as pd

WEIGHTS = {"base": 0.60, "adverse": 0.25, "upside": 0.15}
SOURCE = "FHFA HPI, national (USA), purchase-only, monthly, seasonally adjusted (hpi_master.csv)"
LAG = 3


def load_hpi(path, cutoff_month: int) -> pd.Series:
    """Index level by month, up to the data cut-off."""
    df = pd.read_csv(path)
    df = df[
        (df.hpi_type == "traditional")
        & (df.hpi_flavor == "purchase-only")
        & (df.frequency == "monthly")
        & (df.place_id == "USA")
    ]
    s = pd.Series(df.index_sa.to_numpy(float), index=df.yr * 12 + df.period - 1).sort_index()
    return s[s.index <= cutoff_month]


def yoy(hpi: pd.Series) -> pd.Series:
    """12-month % change (as a fraction) ending in each month."""
    year_ago = pd.Series(hpi.to_numpy(), index=hpi.index + 12).reindex(hpi.index)
    return (hpi / year_ago - 1).dropna()


class Macro:
    """The lagged 12-month HPI change and the three scenario paths."""

    def __init__(self, hpi: pd.Series):
        self.chg = yoy(hpi)
        self.last = int(self.chg.index.max())
        self.base = float(self.chg.median())
        self.p90 = float(self.chg.quantile(0.9))
        adv_start = 2007 * 12
        self.adverse_path = self.chg.loc[adv_start : adv_start + 59].to_numpy()

    def x(self, month):
        """Covariate at a month: the 12-month change ending LAG months earlier (the last
        available value is carried forward past the end of the series)."""
        m = np.minimum(np.asarray(month) - LAG, self.last)
        return self.chg.reindex(m).to_numpy()

    def path(self, scenario: str, months: int) -> np.ndarray:
        """Scenario 12-month change for months 1..months after the reporting date."""
        out = np.full(months, self.base)
        if scenario == "adverse":
            k = min(months, len(self.adverse_path))
            out[:k] = self.adverse_path[:k]
        elif scenario == "upside":
            out[: min(months, 24)] = self.p90
        return out

    def x_paths(self, date_month: int, scenario: str, months: int) -> np.ndarray:
        """Covariate for projection months 1..months from a reporting date: months within the
        lag are already observed; later months take the scenario path shifted by the lag."""
        m = np.arange(1, months + 1)
        observed = self.x(date_month + m)
        scen = self.path(scenario, months)
        idx = np.clip(m - LAG - 1, 0, months - 1)
        return np.where(m <= LAG, observed, scen[idx])
