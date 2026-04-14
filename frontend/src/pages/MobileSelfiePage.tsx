import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Camera, CheckCircle2, XCircle, Loader2, Upload } from "lucide-react";
import api from "@/api/client";

type PageState = "idle" | "uploading" | "success" | "error";

export default function MobileSelfiePage() {
  const { token } = useParams<{ token: string }>();
  const inputRef = useRef<HTMLInputElement>(null);
  const [pageState, setPageState] = useState<PageState>("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [preview, setPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreview(url);
  };

  const handleUpload = async () => {
    if (!selectedFile || !token) return;
    setPageState("uploading");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      await api.post(`/idv/mobile-upload/${token}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPageState("success");
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        "Upload failed. The link may have expired.";
      setErrorMsg(msg);
      setPageState("error");
    }
  };

  const handleRetake = () => {
    setPreview(null);
    setSelectedFile(null);
    setPageState("idle");
    if (inputRef.current) inputRef.current.value = "";
  };

  // ── Success ──────────────────────────────────────────────────────────────────
  if (pageState === "success") {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-6">
        <div className="w-full max-w-sm text-center space-y-4">
          <CheckCircle2 className="h-16 w-16 text-emerald-400 mx-auto" />
          <h1 className="text-xl font-bold text-foreground">Selfie Uploaded</h1>
          <p className="text-sm text-muted-foreground">
            Your selfie has been securely submitted. You can close this page and
            return to your computer to continue.
          </p>
        </div>
      </div>
    );
  }

  // ── Error ────────────────────────────────────────────────────────────────────
  if (pageState === "error") {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-6">
        <div className="w-full max-w-sm text-center space-y-4">
          <XCircle className="h-16 w-16 text-red-400 mx-auto" />
          <h1 className="text-xl font-bold text-foreground">Upload Failed</h1>
          <p className="text-sm text-muted-foreground">{errorMsg}</p>
          <button
            onClick={handleRetake}
            className="px-6 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // ── Main ─────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
            <Camera className="h-6 w-6 text-primary" />
          </div>
          <h1 className="text-xl font-bold text-foreground">Take a Selfie</h1>
          <p className="text-sm text-muted-foreground">
            Use your front camera for best results. Make sure your face is clearly visible.
          </p>
        </div>

        {/* Preview / capture area */}
        {preview ? (
          <div className="space-y-3">
            <div className="rounded-2xl overflow-hidden border border-border aspect-[3/4]">
              <img src={preview} alt="Preview" className="w-full h-full object-cover" />
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleRetake}
                disabled={pageState === "uploading"}
                className="flex-1 py-3 bg-muted text-secondary-foreground rounded-xl text-sm font-semibold border border-border hover:bg-accent transition-colors disabled:opacity-50"
              >
                Retake
              </button>
              <button
                onClick={handleUpload}
                disabled={pageState === "uploading"}
                className="flex-1 py-3 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {pageState === "uploading" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Uploading…
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4" />
                    Submit Selfie
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Hidden file input — capture="user" opens front camera on mobile */}
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              capture="user"
              onChange={handleFileChange}
              className="hidden"
              id="selfie-input"
            />
            <label
              htmlFor="selfie-input"
              className="flex flex-col items-center justify-center gap-3 w-full py-12 rounded-2xl border-2 border-dashed border-border bg-muted/20 hover:bg-muted/40 transition-colors cursor-pointer"
            >
              <Camera className="h-10 w-10 text-muted-foreground" />
              <div className="text-center">
                <p className="text-sm font-semibold text-foreground">Open Camera</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Tap to take or choose a photo
                </p>
              </div>
            </label>
          </div>
        )}

        <p className="text-xs text-muted-foreground text-center">
          This link is single-use and expires in 10 minutes.
        </p>
      </div>
    </div>
  );
}
