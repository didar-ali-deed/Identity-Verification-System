import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { useGetMobileSelfieToken, useIDVStatus } from "@/api/idv";
import LiveCapture from "./LiveCapture";

interface Props {
  onCapture: (file: File, frames?: File[]) => void;
  isUploading: boolean;
  applicationId: string;
}

export default function SelfieCapture({ onCapture, isUploading, applicationId }: Props) {
  const [mode, setMode] = useState<"webcam" | "phone">("webcam");
  const [token, setToken] = useState<string | null>(null);
  const completed = useRef(false);
  const getToken = useGetMobileSelfieToken();
  const { data: status } = useIDVStatus({
    enabled: mode === "phone" && !!token, refetchInterval: 2000, staleTime: 0,
  });
  const received = status?.id === applicationId && status.selfie_uploaded;
  useEffect(() => {
    if (!received || completed.current) return;
    const timer = setTimeout(() => {
      completed.current = true;
      onCapture(new File([], "selfie-from-phone.jpg", { type: "image/jpeg" }));
    }, 500);
    return () => clearTimeout(timer);
  }, [received, onCapture]);

  async function phone() {
    setMode("phone");
    setToken(null);
    try { setToken((await getToken.mutateAsync()).token); } catch { /* Error shown below. */ }
  }

  return <div className="space-y-4">
    <div className="flex gap-3">
      <button type="button" onClick={() => setMode("webcam")} aria-pressed={mode === "webcam"} className="rounded-lg border border-border px-4 py-2 text-sm">Webcam</button>
      <button type="button" onClick={phone} disabled={getToken.isPending} aria-pressed={mode === "phone"} className="rounded-lg border border-border px-4 py-2 text-sm">Use phone</button>
    </div>
    {mode === "webcam" ? <LiveCapture onCapture={onCapture} isUploading={isUploading} />
      : received ? <div className="rounded-xl border border-emerald-500/30 p-6 text-center"><CheckCircle2 className="mx-auto mb-3 text-emerald-400" />Selfie frames received. Continuing…</div>
      : getToken.isPending ? <Loader2 className="animate-spin" aria-label="Generating phone link" />
      : token ? <div className="rounded-xl border border-border p-6 space-y-4">
        <div className="mx-auto w-fit rounded-xl bg-white p-4"><QRCodeSVG value={window.location.origin + "/m/" + token} size={180} /></div>
        <p className="text-center text-sm text-muted-foreground">Scan with your phone to capture three selfie frames. This single-use link expires after 10 minutes.</p>
        <p className="text-xs text-muted-foreground">For a phone, open this application through an HTTPS address reachable from both devices. A localhost link only works on this computer.</p>
        <button type="button" onClick={phone} className="text-sm text-primary">Generate a new link</button>
      </div> : <p role="alert" className="text-sm text-red-400">Could not create the phone link. Try again.</p>}
  </div>;
}
