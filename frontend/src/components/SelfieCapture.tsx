import { useRef, useState, useCallback, useEffect } from "react";
import Webcam from "react-webcam";
import { QRCodeSVG } from "qrcode.react";
import { Camera, RotateCcw, Upload, Loader2, Smartphone, CheckCircle2, Copy, Check } from "lucide-react";
import { useGetMobileSelfieToken, useIDVStatus } from "@/api/idv";

interface SelfieCaptureProps {
  onCapture: (file: File) => void;
  isUploading: boolean;
  applicationId: string;
}

type Mode = "webcam" | "phone";

export default function SelfieCapture({ onCapture, isUploading }: SelfieCaptureProps) {
  const webcamRef = useRef<Webcam>(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("webcam");
  const [mobileToken, setMobileToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const completedRef = useRef(false);

  const getToken = useGetMobileSelfieToken();

  // Poll IDV status in phone mode to detect when selfie lands
  const { data: idvStatus } = useIDVStatus({
    enabled: mode === "phone" && !!mobileToken,
    refetchInterval: 3000,
    staleTime: 0,
  });

  // Derive completion from polled data — no setState in effect
  const mobileComplete =
    mode === "phone" &&
    !!mobileToken &&
    idvStatus?.face_match_score !== null &&
    idvStatus?.face_match_score !== undefined;

  // Fire onCapture once when phone selfie is confirmed
  useEffect(() => {
    if (!mobileComplete || completedRef.current) return;
    completedRef.current = true;
    const placeholder = new File([], "selfie-from-phone.jpg", { type: "image/jpeg" });
    setTimeout(() => onCapture(placeholder), 1500);
  }, [mobileComplete, onCapture]);

  const handleSwitchToPhone = async () => {
    setMode("phone");
    if (!mobileToken) {
      try {
        const result = await getToken.mutateAsync();
        setMobileToken(result.token);
      } catch {
        // token fetch failed — stay in phone mode, show retry
      }
    }
  };

  const mobileUrl = mobileToken
    ? `${window.location.origin}/m/${mobileToken}`
    : null;

  const handleCopy = async () => {
    if (!mobileUrl) return;
    await navigator.clipboard.writeText(mobileUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const capture = useCallback(() => {
    const imageSrc = webcamRef.current?.getScreenshot();
    if (imageSrc) setPhoto(imageSrc);
  }, []);

  const retake = () => setPhoto(null);

  const handleUpload = () => {
    if (!photo) return;
    const [header, data] = photo.split(",");
    const mimeMatch = header.match(/:(.*?);/);
    if (!mimeMatch) return;
    const mime = mimeMatch[1];
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const file = new File([bytes], "selfie.jpg", { type: mime });
    onCapture(file);
  };

  // ── Phone mode ──────────────────────────────────────────────────────────────
  if (mode === "phone") {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-widest">
            Phone Camera
          </label>
          <button
            onClick={() => setMode("webcam")}
            className="text-xs text-primary hover:text-primary/80 transition-colors"
          >
            Use Webcam Instead
          </button>
        </div>

        {mobileComplete ? (
          <div className="border border-emerald-500/30 rounded-xl p-8 text-center bg-emerald-500/5">
            <CheckCircle2 className="h-10 w-10 text-emerald-400 mx-auto mb-3" />
            <p className="text-sm font-semibold text-foreground">Selfie Received</p>
            <p className="text-xs text-muted-foreground mt-1">
              Your selfie was uploaded from your phone. Advancing…
            </p>
          </div>
        ) : getToken.isPending ? (
          <div className="border border-border rounded-xl p-8 text-center bg-muted/20">
            <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">Generating secure link…</p>
          </div>
        ) : getToken.isError || !mobileToken ? (
          <div className="border border-border rounded-xl p-8 text-center bg-muted/20 space-y-3">
            <p className="text-sm text-foreground">Failed to generate phone link.</p>
            <button
              onClick={handleSwitchToPhone}
              className="text-xs text-primary hover:text-primary/80 underline"
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="border border-border rounded-xl p-6 bg-card flex flex-col items-center gap-4">
              {/* QR code on white bg for best scan contrast */}
              <div className="bg-white rounded-lg p-3">
                <QRCodeSVG value={mobileUrl!} size={180} />
              </div>

              <div className="text-center space-y-1">
                <p className="text-sm font-medium text-foreground">
                  Scan with your phone
                </p>
                <p className="text-xs text-muted-foreground">
                  Open the camera on your phone and point it at this QR code.
                  Then take a selfie — this page will update automatically.
                </p>
              </div>

              {/* Copyable URL fallback */}
              <div className="flex items-center gap-2 w-full bg-muted/40 rounded-lg px-3 py-2 border border-border">
                <span className="flex-1 text-xs text-muted-foreground font-mono truncate">
                  {mobileUrl}
                </span>
                <button
                  onClick={handleCopy}
                  className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                  title="Copy link"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
            </div>

            {/* Polling indicator */}
            <div className="flex items-center gap-2 justify-center text-xs text-muted-foreground">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
              </span>
              Waiting for selfie from phone…
            </div>

            <p className="text-xs text-muted-foreground text-center">
              Link expires in 10 minutes. For best results, take the selfie in good lighting.
            </p>
          </div>
        )}
      </div>
    );
  }

  // ── Webcam mode — camera error state ────────────────────────────────────────
  if (cameraError) {
    return (
      <div className="space-y-4">
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-widest">
          Take a Selfie
        </label>
        <div className="border border-border rounded-xl p-8 text-center bg-muted/30 space-y-3">
          <Camera className="h-10 w-10 text-muted-foreground mx-auto" />
          <div>
            <p className="text-sm text-foreground font-medium">Camera not available</p>
            <p className="text-xs text-muted-foreground mt-1">{cameraError}</p>
          </div>
          <button
            onClick={handleSwitchToPhone}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg text-sm font-semibold hover:bg-primary/90 transition-colors btn-glow"
          >
            <Smartphone className="h-4 w-4" />
            Use Phone Camera Instead
          </button>
        </div>
      </div>
    );
  }

  // ── Webcam mode — normal ─────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-widest">
          Take a Selfie
        </label>
        <button
          onClick={handleSwitchToPhone}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors"
        >
          <Smartphone className="h-3.5 w-3.5" />
          Use Phone Instead
        </button>
      </div>

      <div className="border border-border rounded-xl overflow-hidden bg-black relative">
        {!photo ? (
          <div className="relative">
            <Webcam
              ref={webcamRef}
              audio={false}
              screenshotFormat="image/jpeg"
              screenshotQuality={0.9}
              videoConstraints={{ width: 640, height: 480, facingMode: "user" }}
              onUserMediaError={(err) => {
                setCameraError(typeof err === "string" ? err : "Camera access denied");
              }}
              className="w-full"
            />
            {/* Face guide overlay */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div
                className="w-48 h-60 rounded-full"
                style={{
                  border: "2px solid rgba(59, 130, 246, 0.6)",
                  boxShadow: "0 0 0 2000px rgba(4, 13, 26, 0.35)",
                }}
              />
            </div>
          </div>
        ) : (
          <img src={photo} alt="Captured selfie" className="w-full" />
        )}
      </div>

      <div className="flex gap-3">
        {!photo ? (
          <button
            onClick={capture}
            disabled={isUploading}
            className="flex-1 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 flex items-center justify-center gap-2 cursor-pointer border-none btn-glow transition-all"
          >
            <Camera className="h-4 w-4" />
            Capture Photo
          </button>
        ) : (
          <>
            <button
              onClick={retake}
              disabled={isUploading}
              className="flex-1 py-2.5 bg-muted text-secondary-foreground rounded-xl text-sm font-semibold hover:bg-accent flex items-center justify-center gap-2 cursor-pointer border border-border transition-all"
            >
              <RotateCcw className="h-4 w-4" />
              Retake
            </button>
            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="flex-1 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer border-none btn-glow transition-all"
            >
              {isUploading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Upload Selfie
            </button>
          </>
        )}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        Position your face within the oval guide. Ensure good lighting and a clear view.
      </p>
    </div>
  );
}
