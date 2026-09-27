// Shared number/date formatting. One place, reused everywhere.
export const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(Math.round(n));

export const fmtMoney = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

// Full-precision fmtMoney doesn't fit a mobile KPI tile once totals run into the billions (a
// portfolio-wide RWA or capital figure). Scale to the nearest of B/M/K, matching Overview's KPIs.
export const fmtMoneyCompact = (n: number) => {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return fmtMoney(n);
};

export const fmtPct = (n: number, digits = 2) => `${(n * 100).toFixed(digits)}%`;

export const fmtDate = (iso: string) =>
  new Date(iso + (iso.length === 10 ? "T00:00:00Z" : "")).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    timeZone: "UTC",
  });
