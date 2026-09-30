import { CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import type { ExtractedFields } from "@/types";

interface Props {
  passport: ExtractedFields;
  nationalId: ExtractedFields;
  drivingLicense?: ExtractedFields | null;
  userFullName?: string;
}

interface CompareRow {
  label: string;
  passportVal: string | null;
  idVal: string | null;
  licenseVal?: string | null;
  status: "match" | "mismatch" | "partial" | "missing" | "available" | "valid" | "expired";
}

function normalize(s: string | null | undefined): string {
  if (!s) return "";
  return s.normalize("NFKC").trim().toUpperCase().replace(/\s+/g, " ");
}

function canonicalDate(value: string): string {
  const text = normalize(value);
  if (/^\d{8}$/.test(text)) return text;
  const numeric = text.match(/^(\d{2})[./-](\d{2})[./-](\d{4})$/);
  if (numeric) return `${numeric[3]}${numeric[2]}${numeric[1]}`;
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) return `${iso[1]}${iso[2]}${iso[3]}`;
  const named = text.match(/^(\d{1,2})\s+([A-Z]+)\s+(\d{4})$/);
  if (named) {
    const month = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"].indexOf(named[2].slice(0, 3)) + 1;
    if (month) return `${named[3]}${String(month).padStart(2, "0")}${named[1].padStart(2, "0")}`;
  }
  return text;
}

function readableName(value: string | null | undefined): string | null {
  const text = value?.trim();
  if (!text || (text.match(/\p{L}/gu)?.length ?? 0) < 2 || !/^[\p{L}\p{M} '\-’.]+$/u.test(text)) return null;
  return text;
}

function validExpiry(value: string | null): string | null {
  const key = value ? canonicalDate(value) : "";
  if (!/^\d{8}$/.test(key)) return null;
  const year = Number(key.slice(0, 4)), month = Number(key.slice(4, 6)), day = Number(key.slice(6, 8));
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? key : null;
}

function tokenMatch(a: string, b: string): boolean {
  if (!a || !b) return false;
  const tokA = new Set(normalize(a).split(" ").filter(Boolean));
  const tokB = new Set(normalize(b).split(" ").filter(Boolean));
  const intersection = [...tokA].filter((t) => tokB.has(t));
  const union = new Set([...tokA, ...tokB]);
  return intersection.length / union.size >= 0.5;
}

function compareValues(
  a: string | null,
  b: string | null,
  exact = false
): "match" | "mismatch" | "partial" | "missing" {
  if (!a && !b) return "missing";
  if (!a || !b) return "missing";
  const na = exact ? canonicalDate(a) : normalize(a);
  const nb = exact ? canonicalDate(b) : normalize(b);
  if (na === nb) return "match";
  if (!exact && na !== nb && na.replace(/[IL]/g, "?") === nb.replace(/[IL]/g, "?")) return "partial";
  if (!exact && tokenMatch(na, nb)) return "partial";
  return "mismatch";
}

const STATUS_CONFIG = {
  valid: { icon: CheckCircle2, color: "text-emerald-400", bg: "", border: "", label: "Valid" },
  expired: { icon: XCircle, color: "text-red-400", bg: "", border: "", label: "Expired" },
  available: {
    icon: CheckCircle2,
    color: "text-muted-foreground",
    bg: "bg-muted/30",
    border: "border-border",
    label: "Read",
  },
  match: {
    icon: CheckCircle2,
    color: "text-emerald-400",
    bg: "bg-emerald-500/8",
    border: "border-emerald-500/20",
    label: "Match",
  },
  partial: {
    icon: AlertCircle,
    color: "text-amber-400",
    bg: "bg-amber-500/8",
    border: "border-amber-500/20",
    label: "Check OCR",
  },
  mismatch: {
    icon: XCircle,
    color: "text-red-400",
    bg: "bg-red-500/8",
    border: "border-red-500/20",
    label: "Mismatch",
  },
  missing: {
    icon: AlertCircle,
    color: "text-muted-foreground",
    bg: "bg-muted/30",
    border: "border-border",
    label: "Missing",
  },
};

export default function DocumentCompare({ passport, nationalId, drivingLicense, userFullName }: Props) {
  passport = { ...passport, full_name: readableName(passport.full_name), nationality: readableName(passport.nationality) };
  nationalId = { ...nationalId, full_name: readableName(nationalId.full_name), nationality: readableName(nationalId.nationality) };
  // Legacy CNIC uploads stored Country of Stay in nationality. Preserve the text
  // while keeping residence separate from citizenship.
  const idCountry = nationalId.country_of_stay || (normalize(nationalId.nationality) === "PAKISTAN" ? nationalId.nationality : null);
  const idNationality = idCountry ? null : nationalId.nationality;
  const canonicalNationality = (value: string | null) => ["PAK", "PAKISTAN", "PAKISTANI"].includes(normalize(value)) ? "PAK" : value;
  const expiryDates = [passport.expiry_date, nationalId.expiry_date, ...(drivingLicense ? [drivingLicense.expiry_date] : [])].map(validExpiry);
  const today = new Date();
  const todayKey = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, "0")}${String(today.getDate()).padStart(2, "0")}`;
  const expiryStatus = expiryDates.some(value => value && value < todayKey)
    ? "expired" : expiryDates.every(Boolean) ? "valid" : "missing";
  const rows: CompareRow[] = [
    {
      label: "Full Name",
      passportVal: passport.full_name,
      idVal: nationalId.full_name,
      licenseVal: drivingLicense?.full_name,
      status: compareValues(passport.full_name, nationalId.full_name),
    },
    {
      label: "Date of Birth",
      passportVal: passport.dob,
      idVal: nationalId.dob,
      licenseVal: drivingLicense?.dob,
      status: compareValues(passport.dob, nationalId.dob, true),
    },
    {
      label: "Gender",
      passportVal: passport.gender,
      idVal: nationalId.gender,
      licenseVal: drivingLicense?.gender,
      status: compareValues(passport.gender, nationalId.gender),
    },
    {
      label: idCountry ? "Nationality / Country of Stay" : "Nationality",
      passportVal: passport.nationality,
      idVal: idCountry || idNationality,
      licenseVal: drivingLicense?.nationality,
      status: idCountry ? "available" : compareValues(canonicalNationality(passport.nationality), canonicalNationality(idNationality)),
    },
    {
      label: "Expiry Date",
      passportVal: passport.expiry_date,
      idVal: nationalId.expiry_date,
      licenseVal: drivingLicense?.expiry_date,
      status: expiryStatus,
    },
  ];

  if (userFullName) {
    const profileChecks = [compareValues(userFullName, passport.full_name), compareValues(userFullName, nationalId.full_name)];
    rows.unshift({
      label: "Name vs Profile",
      passportVal: passport.full_name,
      idVal: nationalId.full_name,
      licenseVal: drivingLicense?.full_name,
      status: profileChecks.includes("mismatch") ? "mismatch" : profileChecks.includes("missing") ? "missing" : profileChecks.includes("partial") ? "partial" : "match",
    });
  }

  const mismatches = rows.filter((r) => r.status === "mismatch").length;
  const partials = rows.filter((r) => r.status === "partial").length;
  const matches = rows.filter((r) => r.status === "match").length;
  const missing = rows.filter((r) => r.status === "missing").length;

  return (
    <div className="space-y-4">
      {userFullName && <p className="text-xs text-muted-foreground">Profile name: {userFullName}</p>}
      {/* Summary badges */}
      <div className="flex gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 rounded-full px-3 py-1 text-xs font-semibold">
          <CheckCircle2 className="h-3.5 w-3.5" />
          {matches} matching
        </div>
        {partials > 0 && (
          <div className="flex items-center gap-1.5 bg-amber-500/10 text-amber-400 border border-amber-500/25 rounded-full px-3 py-1 text-xs font-semibold">
            <AlertCircle className="h-3.5 w-3.5" />
            {partials} partial
          </div>
        )}
        {mismatches > 0 && (
          <div className="flex items-center gap-1.5 bg-red-500/10 text-red-400 border border-red-500/25 rounded-full px-3 py-1 text-xs font-semibold">
            <XCircle className="h-3.5 w-3.5" />
            {mismatches} mismatch
          </div>
        )}
      </div>

      {/* Comparison table */}
      <div className="border border-border rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-muted/40 border-b border-border">
              <th className="text-left px-3 py-2.5 font-semibold text-muted-foreground uppercase tracking-wider w-24">Field</th>
              <th className="text-left px-3 py-2.5 font-semibold text-muted-foreground uppercase tracking-wider">Passport</th>
              <th className="text-left px-3 py-2.5 font-semibold text-muted-foreground uppercase tracking-wider">National ID</th>
              {drivingLicense && (
                <th className="text-left px-3 py-2.5 font-semibold text-muted-foreground uppercase tracking-wider">License</th>
              )}
              <th className="text-left px-3 py-2.5 font-semibold text-muted-foreground uppercase tracking-wider w-20">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => {
              const cfg = STATUS_CONFIG[row.status];
              const Icon = cfg.icon;
              return (
                <tr
                  key={row.label}
                  className={row.status === "mismatch" ? "bg-red-500/5" : ""}
                >
                  <td className="px-3 py-2.5 text-muted-foreground font-medium whitespace-nowrap">{row.label}</td>
                  <td
                    className="px-3 py-2.5 text-foreground font-mono"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {row.passportVal ?? <span className="text-muted-foreground">—</span>}
                  </td>
                  <td
                    className="px-3 py-2.5 text-foreground font-mono"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {row.idVal ?? <span className="text-muted-foreground">—</span>}
                  </td>
                  {drivingLicense && (
                    <td
                      className="px-3 py-2.5 text-foreground font-mono"
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {row.licenseVal ?? <span className="text-muted-foreground">—</span>}
                    </td>
                  )}
                  <td className="px-3 py-2.5">
                    <span className={`flex items-center gap-1 font-semibold ${cfg.color}`}>
                      <Icon className="h-3 w-3" />
                      {row.label === "Nationality / Country of Stay" && row.status === "available" ? "Not compared" : cfg.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted-foreground">Expiry dates are checked separately for each document and may differ. Valid means the extracted date has not passed. Nationality describes citizenship; Country of Stay describes residence and is not compared as nationality.</p>

      {missing > 0 && (
        <div className="text-xs text-amber-400 bg-amber-500/8 rounded-xl px-4 py-3 border border-amber-500/20">
          Some fields could not be read reliably. Missing OCR data is not an identity mismatch.
          Use a clear, straight image showing the whole document and its MRZ, without glare.
          Continuing may require manual review.
        </div>
      )}
      {partials > 0 && <p className="text-xs text-amber-400">Similar names were read differently. Check the extracted text against your documents; this is not a verified match.</p>}
      {mismatches > 0 && (
        <div className="flex items-start gap-2 text-xs text-amber-400 bg-amber-500/8 rounded-xl px-4 py-3 border border-amber-500/20">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            Some fields don&apos;t match between your documents. The verification pipeline will flag these for review.
            You can still proceed.
          </span>
        </div>
      )}
    </div>
  );
}
