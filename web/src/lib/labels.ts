// Plain names for scorecard features and Freddie Mac category codes.
const FEATURES: Record<string, string> = {
  fico: "Credit score",
  ltv_pct: "Loan-to-value (%)",
  cltv_pct: "Combined LTV (%)",
  dti_pct: "Debt-to-income (%)",
  mi_pct: "Mortgage insurance (%)",
  rate_spread_pct: "Rate vs market (pp)",
  original_upb: "Loan amount ($)",
  term_band: "Term",
  loan_purpose: "Purpose",
  occupancy_status: "Occupancy",
  property_type: "Property type",
  number_of_units: "Units",
  channel: "Channel",
  first_time_homebuyer: "First-time buyer",
  super_conforming: "Super-conforming",
};

const CATEGORIES: Record<string, Record<string, string>> = {
  term_band: { le_180: "15 years or less", "181_240": "15–20 years", gt_240: "Over 20 years" },
  property_type: { SF: "Single-family", PU: "Planned development", CO: "Condo", MH: "Manufactured", CP: "Co-op" },
  channel: { R: "Retail", B: "Broker", C: "Correspondent", T: "Third party (unspecified)" },
  occupancy_status: { P: "Primary", S: "Second home", I: "Investor" },
  loan_purpose: { P: "Purchase", C: "Cash-out refi", N: "No-cash-out refi", R: "Refi (unspecified)" },
};

export const featureLabel = (f: string) => FEATURES[f] ?? f.replace(/_/g, " ");
export const categoryLabel = (f: string, c: string) => CATEGORIES[f]?.[c] ?? c;

/** A bin as a reader sees it: "Unknown", the plain category names, or the numeric range. */
export const binText = (f: string, b: { is_missing_bin: boolean; categories: string[]; bin: string }) =>
  b.is_missing_bin ? "Unknown" : b.categories.length ? b.categories.map((c) => categoryLabel(f, c)).join(", ") : b.bin;
