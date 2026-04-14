import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FileCheck, CheckCircle2, Loader2, SkipForward, ScanLine } from "lucide-react";
import DocumentUpload from "@/components/DocumentUpload";
import SelfieCapture from "@/components/SelfieCapture";
import ExtractedFieldsCard from "@/components/ExtractedFieldsCard";
import DocumentCompare from "@/components/DocumentCompare";
import {
  useCreateApplication,
  useUploadDocument,
  useUploadSelfie,
  useIDVStatus,
  useDocumentOCR,
} from "@/api/idv";
import { useAuthStore } from "@/stores/authStore";
import type { ExtractedFields } from "@/types";

const STEP_PASSPORT   = 0;
const STEP_NATIONAL_ID = 1;
const STEP_DRIVING    = 2;
const STEP_COMPARE    = 3;
const STEP_SELFIE     = 4;
const STEP_DONE       = 5;

const STEP_LABELS = [
  { title: "Passport",   description: "Required" },
  { title: "National ID", description: "Required" },
  { title: "Driving Lic", description: "Optional" },
  { title: "Review",     description: "Cross-check" },
  { title: "Selfie",     description: "Face match" },
  { title: "Complete",   description: "Submitted" },
];

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-1 mb-8 overflow-x-auto pb-1">
      {STEP_LABELS.map((s, i) => (
        <div key={i} className="flex items-center gap-1 shrink-0">
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
              i < current
                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25"
                : i === current
                  ? "bg-primary/15 text-primary border border-primary/30 step-active"
                  : "bg-muted text-muted-foreground border border-border"
            }`}
          >
            {i < current ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <span
                className="w-4 h-4 flex items-center justify-center"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {i + 1}
              </span>
            )}
            <span className="hidden sm:inline">{s.title}</span>
          </div>
          {i < STEP_LABELS.length - 1 && (
            <div
              className={`h-px w-3 sm:w-5 ${
                i < current ? "bg-emerald-500/40" : "bg-border"
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function ScanningBanner({ docLabel }: { docLabel: string }) {
  return (
    <div className="flex items-center gap-3 p-4 bg-blue-500/8 border border-blue-500/20 rounded-xl text-sm text-blue-300 relative overflow-hidden">
      <div className="scan-sweep" />
      <ScanLine className="h-5 w-5 shrink-0 text-blue-400" />
      <div className="flex-1">
        <p className="font-semibold">Scanning {docLabel}…</p>
        <p className="text-xs text-blue-400/70 mt-0.5">
          Extracting fields — usually 15–30 seconds on first run
        </p>
      </div>
      <Loader2 className="h-4 w-4 animate-spin shrink-0 text-blue-400" />
    </div>
  );
}

export default function IDVSubmission() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const [step, setStep]               = useState(STEP_PASSPORT);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [error, setError]             = useState<string | null>(null);
  const [appCreated, setAppCreated]   = useState(false); // guard against double-create

  const [passportDocId, setPassportDocId] = useState<string | null>(null);
  const [idDocId, setIdDocId]             = useState<string | null>(null);
  const [licenseDocId, setLicenseDocId]   = useState<string | null>(null);

  const [passportFields, setPassportFields] = useState<ExtractedFields | null>(null);
  const [idFields, setIdFields]             = useState<ExtractedFields | null>(null);
  const [licenseFields, setLicenseFields]   = useState<ExtractedFields | null>(null);

  const createApp      = useCreateApplication();
  const uploadDocument = useUploadDocument();
  const uploadSelfie   = useUploadSelfie();
  const { data: existingApp } = useIDVStatus();

  const passportOCR = useDocumentOCR(passportDocId, !passportFields);
  const idOCR       = useDocumentOCR(idDocId, !idFields);
  const licenseOCR  = useDocumentOCR(licenseDocId, !licenseFields);

  useEffect(() => {
    if (passportOCR.data?.ocr_ready && passportOCR.data.extracted_fields && !passportFields) {
      setPassportFields(passportOCR.data.extracted_fields);
    }
  }, [passportOCR.data, passportFields]);

  useEffect(() => {
    if (idOCR.data?.ocr_ready && idOCR.data.extracted_fields && !idFields) {
      setIdFields(idOCR.data.extracted_fields);
    }
  }, [idOCR.data, idFields]);

  useEffect(() => {
    if (licenseOCR.data?.ocr_ready && licenseOCR.data.extracted_fields && !licenseFields) {
      setLicenseFields(licenseOCR.data.extracted_fields);
    }
  }, [licenseOCR.data, licenseFields]);

  // Auto-create or reuse existing application — guarded against double-fire
  useEffect(() => {
    if (existingApp === undefined) return; // still loading
    if (appCreated) return; // already handled

    if (existingApp && ["pending", "error"].includes(existingApp.status)) {
      setApplicationId(existingApp.id);
      setAppCreated(true);
      return;
    }
    if (existingApp && !["approved", "rejected"].includes(existingApp.status)) {
      navigate("/idv/status");
      return;
    }
    // No existing app (or existing is approved/rejected) — create new
    if (!applicationId) {
      setAppCreated(true); // set before mutate to prevent re-trigger
      createApp.mutate(undefined, {
        onSuccess: (data) => setApplicationId(data.id),
        onError: (err) => {
          const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
          if (typeof detail === "string" && detail.includes("already have")) return;
          setError(typeof detail === "string" ? detail : "Failed to start verification");
        },
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingApp]);

  const handleDocumentUpload = async (
    file: File,
    docType: "passport" | "national_id" | "drivers_license",
  ) => {
    if (!applicationId) return;
    setError(null);
    try {
      const result = await uploadDocument.mutateAsync({ file, docType, applicationId });
      if (docType === "passport") {
        setPassportDocId(result.id);
        setStep(STEP_NATIONAL_ID);
      } else if (docType === "national_id") {
        setIdDocId(result.id);
        setStep(STEP_DRIVING);
      } else {
        setLicenseDocId(result.id);
        setStep(STEP_COMPARE);
      }
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Upload failed. Please try again.");
    }
  };

  const handleSelfie = async (file: File) => {
    if (!applicationId) return;
    setError(null);
    // Phone-mode placeholder: selfie was already uploaded from the phone
    if (file.size === 0) {
      setStep(STEP_DONE);
      return;
    }
    try {
      await uploadSelfie.mutateAsync({ file, applicationId });
      setStep(STEP_DONE);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to upload selfie");
    }
  };

  if (createApp.isPending && !applicationId) {
    return (
      <div className="max-w-2xl mx-auto flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Page header */}
      <div className="flex items-center gap-3 mb-7">
        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0">
          <FileCheck className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-foreground">Identity Verification</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Upload your documents to verify your identity
          </p>
        </div>
      </div>

      <StepBar current={step} />

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="bg-card border border-border rounded-xl p-6 shadow-lg space-y-5">

        {/* Step 0: Passport */}
        {step === STEP_PASSPORT && (
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold text-foreground">Upload Your Passport</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Place the photo page flat in good lighting. All text and photo must be clearly visible.
              </p>
            </div>
            <DocumentUpload
              onFileSelected={(f) => handleDocumentUpload(f, "passport")}
              isUploading={uploadDocument.isPending}
              label="Passport Photo Page"
            />
          </div>
        )}

        {/* Step 1: National ID */}
        {step === STEP_NATIONAL_ID && (
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold text-foreground">Upload Your National ID</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Upload the front of your CNIC, Emirates ID, or equivalent national identity card.
              </p>
            </div>
            {!passportFields && passportDocId ? (
              <ScanningBanner docLabel="passport" />
            ) : passportFields ? (
              <ExtractedFieldsCard fields={passportFields} docType="passport" />
            ) : null}
            <div className={passportDocId ? "border-t border-border pt-4" : ""}>
              <DocumentUpload
                onFileSelected={(f) => handleDocumentUpload(f, "national_id")}
                isUploading={uploadDocument.isPending}
                label="National ID (Front)"
              />
            </div>
          </div>
        )}

        {/* Step 2: Driving License (optional) */}
        {step === STEP_DRIVING && (
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold text-foreground">
                Driving License{" "}
                <span className="text-xs font-normal text-muted-foreground">(optional)</span>
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                Adding a driving license improves your verification score.
              </p>
            </div>
            {!idFields && idDocId ? (
              <ScanningBanner docLabel="national ID" />
            ) : idFields ? (
              <ExtractedFieldsCard fields={idFields} docType="national_id" />
            ) : null}
            <div className="border-t border-border pt-4 space-y-3">
              <DocumentUpload
                onFileSelected={(f) => handleDocumentUpload(f, "drivers_license")}
                isUploading={uploadDocument.isPending}
                label="Driving License"
              />
              <button
                onClick={() => setStep(STEP_COMPARE)}
                disabled={uploadDocument.isPending}
                className="w-full py-2 border border-border rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center justify-center gap-2 cursor-pointer bg-transparent disabled:opacity-50 transition-colors"
              >
                <SkipForward className="h-4 w-4" />
                Skip — I don&apos;t have a driving license
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Cross-document comparison */}
        {step === STEP_COMPARE && (
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold text-foreground">Document Review</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Review the data extracted from your documents before proceeding to your selfie.
              </p>
            </div>
            {!passportFields && passportDocId && <ScanningBanner docLabel="passport" />}
            {!idFields && idDocId && <ScanningBanner docLabel="national ID" />}
            {!licenseFields && licenseDocId && <ScanningBanner docLabel="driving license" />}

            {passportFields && idFields ? (
              <>
                <DocumentCompare
                  passport={passportFields}
                  nationalId={idFields}
                  drivingLicense={licenseFields}
                  userFullName={user?.full_name}
                />
                <button
                  onClick={() => setStep(STEP_SELFIE)}
                  className="w-full py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 cursor-pointer border-none btn-glow transition-all"
                >
                  Continue to selfie
                </button>
              </>
            ) : (
              <div className="text-center py-8 text-sm text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2 text-primary" />
                Waiting for document analysis to complete…
              </div>
            )}
          </div>
        )}

        {/* Step 4: Selfie */}
        {step === STEP_SELFIE && (
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold text-foreground">Take a Selfie</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Your face will be compared against your passport and national ID photos.
                Face the camera directly in good lighting.
              </p>
            </div>
            <SelfieCapture
              onCapture={handleSelfie}
              isUploading={uploadSelfie.isPending}
              applicationId={applicationId ?? ""}
            />
          </div>
        )}

        {/* Step 5: Done */}
        {step === STEP_DONE && (
          <div className="text-center py-10 space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center mx-auto">
              <CheckCircle2 className="h-8 w-8 text-emerald-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-foreground">Submission Complete</h2>
              <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto leading-relaxed">
                All documents and your selfie have been received. The AI verification pipeline
                is now running — document liveness, field extraction, face matching, and scoring.
              </p>
            </div>
            <button
              onClick={() => navigate("/idv/status")}
              className="px-6 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 cursor-pointer border-none btn-glow transition-all"
            >
              View Verification Status
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
