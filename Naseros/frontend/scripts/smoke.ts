import { formatAnomalyPct, formatSeverity, formatRange } from "../lib/formatters";
console.log("anomaly:", formatAnomalyPct(-42.5), "|", formatAnomalyPct(12), "|", formatAnomalyPct(NaN));
console.log("severity:", formatSeverity("extreme"), "|", formatSeverity("low"));
console.log("range:", formatRange("2023-06-01", "2024-05-01"));
