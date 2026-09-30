import { useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import LiveCapture from "@/components/LiveCapture";

export default function MobileSelfiePage() {
  const { token } = useParams<{ token: string }>();
  const [uploading, setUploading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function upload(file: File, frames: File[]) {
    if (!token) return;
    setUploading(true); setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      frames.forEach(frame => body.append("frames", frame));
      // This route uses a one-time capability, independent of account JWT refresh.
      const response = await fetch("/api/v1/idv/mobile-upload/" + encodeURIComponent(token), { method: "POST", body });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(typeof data.detail === "string" ? data.detail : "Upload failed. Generate a new link on your computer.");
      }
      setDone(true);
    } catch (err) { setError(err instanceof Error ? err.message : "Upload failed."); }
    finally { setUploading(false); }
  }
  return <main className="mx-auto max-w-md px-5 py-10">
    <div className="mb-6 flex items-center gap-3"><ShieldCheck className="text-primary" /><h1 className="text-xl font-bold">Secure selfie capture</h1></div>
    {done ? <div className="rounded-xl border border-emerald-500/30 p-6 text-center">
      <CheckCircle2 className="mx-auto mb-3 text-emerald-400" /><h2 className="font-semibold">Frames received</h2>
      <p className="mt-2 text-sm text-muted-foreground">Return to your computer to view the verification result.</p>
    </div> : <><LiveCapture onCapture={upload} isUploading={uploading} />
      {error && <p role="alert" className="mt-4 text-sm text-red-400">{error}</p>}</>}
  </main>;
}
