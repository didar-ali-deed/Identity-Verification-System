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
  status: "match" | "mismatch" | "partial" | "missing";
}

function normalize(s: string | null | undefined): string {
  if (!s) return "";
  return s.trim().toUpperCase().replace(/\s+/g, " ");
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
  const na = normalize(a);
  const nb = normalize(b);
  if (na === nb) return "match";
  if (!exact && tokenMatch(na, nb)) return "partial";
  return "mismatch";
}

const STATUS_CONFIG = {
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
    label: "Partial",
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
      label: "Nationality",
      passportVal: passport.nationality,
      idVal: nationalId.nationality,
      licenseVal: drivingLicense?.nationality,
      status: compareValues(passport.nationality, nationalId.nationality),
    },
    {
      label: "Expiry Date",
      passportVal: passport.expiry_date,
      idVal: nationalId.expiry_date,
      licenseVal: drivingLicense?.expiry_date,
      status: "missing" as const,
    },
  ];

  if (userFullName) {
    rows.unshift({
      label: "Name vs Profile",
      passportVal: userFullName,
      idVal: passport.full_name,
      licenseVal: nationalId.full_name,
      status: compareValues(userFullName, passport.full_name),
    });
  }

  const mismatches = rows.filter((r) => r.status === "mismatch").length;
  const partials = rows.filter((r) => r.status === "partial").length;
  const matches = rows.filter((r) => r.status === "match").length;

  return (
    <div className="space-y-4">
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
                      {cfg.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

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
