// Shared number/date formatting. One place, reused everywhere.
export const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(Math.round(n));

export const fmtMoney = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

export const fmtPct = (n: number, digits = 2) => `${(n * 100).toFixed(digits)}%`;

export const fmtDate = (iso: string) =>
  new Date(iso + (iso.length === 10 ? "T00:00:00Z" : "")).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    timeZone: "UTC",
  });
