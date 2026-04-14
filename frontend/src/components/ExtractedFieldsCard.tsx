import { CheckCircle2, AlertCircle } from "lucide-react";
import type { ExtractedFields } from "@/types";

interface Props {
  fields: ExtractedFields;
  docType: "passport" | "national_id" | "drivers_license";
}

const FIELD_LABELS: Record<string, string> = {
  full_name: "Full Name",
  dob: "Date of Birth",
  document_number: "Document Number",
  expiry_date: "Expiry Date",
  nationality: "Nationality",
  gender: "Gender",
  national_id_number: "National ID Number",
  father_name: "Father's Name",
  place_of_birth: "Place of Birth",
  issuing_authority: "Issuing Authority",
};

const PASSPORT_FIELDS = [
  "full_name",
  "dob",
  "document_number",
  "expiry_date",
  "nationality",
  "gender",
  "place_of_birth",
  "issuing_authority",
];

const ID_FIELDS = [
  "full_name",
  "father_name",
  "dob",
  "national_id_number",
  "expiry_date",
  "nationality",
  "gender",
];

export default function ExtractedFieldsCard({ fields, docType }: Props) {
  const fieldKeys = docType === "passport" ? PASSPORT_FIELDS : ID_FIELDS;

  const presentFields = fieldKeys.filter(
    (k) => fields[k as keyof ExtractedFields] != null && fields[k as keyof ExtractedFields] !== ""
  );
  const missingFields = fieldKeys.filter(
    (k) => !fields[k as keyof ExtractedFields]
  );

  const confidence = (key: string): number =>
    fields.confidences?.[key] ?? fields.confidences?.[`${key}_mrz_valid`] ?? -1;

  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
        <span className="text-sm font-semibold text-emerald-300">
          Document scanned — {presentFields.length} of {fieldKeys.length} fields extracted
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {presentFields.map((key) => {
          const value = fields[key as keyof ExtractedFields] as string;
          const conf = confidence(key);
          return (
            <div
              key={key}
              className="bg-card rounded-lg border border-border px-3 py-2"
            >
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-0.5">
                {FIELD_LABELS[key] ?? key}
              </p>
              <p
                className="text-sm font-medium text-foreground break-all"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {value}
              </p>
              {conf >= 0 && (
                <div className="mt-1.5 h-1 rounded-full bg-muted">
                  <div
                    className={`h-1 rounded-full transition-all ${
                      conf >= 0.85 ? "bg-emerald-500" : conf >= 0.6 ? "bg-amber-500" : "bg-red-400"
                    }`}
                    style={{ width: `${Math.round(conf * 100)}%` }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {missingFields.length > 0 && (
        <div className="flex items-start gap-2 text-xs text-amber-400 bg-amber-500/8 rounded-lg px-3 py-2.5 border border-amber-500/20">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            Could not read:{" "}
            <span className="font-medium">
              {missingFields.map((k) => FIELD_LABELS[k] ?? k).join(", ")}
            </span>
            . Ensure the document is flat, well-lit and fully in frame.
          </span>
        </div>
      )}
    </div>
  );
}
