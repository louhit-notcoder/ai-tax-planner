export const inr = (v) => {
  if (v === null || v === undefined || isNaN(v)) return "₹0";
  return "₹" + Math.round(v).toLocaleString("en-IN");
};

export const inrShort = (v) => {
  if (!v) return "₹0";
  if (v >= 10000000) return "₹" + (v / 10000000).toFixed(2) + " Cr";
  if (v >= 100000) return "₹" + (v / 100000).toFixed(2) + " L";
  return "₹" + Math.round(v).toLocaleString("en-IN");
};

export const STATUS_LABELS = {
  not_started: "Not Started",
  parsing: "Parsing Files",
  provisional: "Provisional",
  under_review: "Awaiting Review",
  reconciled: "Reconciled (OK)",
  computed: "Computed from Approved Facts",
  approved: "CA Approved",
  locked: "Locked Snapshot",
  completed: "Completed",
};
