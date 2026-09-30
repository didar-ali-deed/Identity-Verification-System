import { useEffect, useRef, useState } from "react";
import { Camera, Loader2, RotateCcw } from "lucide-react";

interface Props { onCapture: (file: File, frames: File[]) => void; isUploading: boolean }

export default function LiveCapture({ onCapture, isUploading }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mountedRef = useRef(true);
  const previewRef = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photos, setPhotos] = useState<File[]>([]);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      streamRef.current?.getTracks().forEach(track => track.stop());
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
  }, []);

  async function startCamera() {
    setError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Use HTTPS or localhost to access your camera.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: "user", width: 640, height: 480 } });
      if (!mountedRef.current) { stream.getTracks().forEach(track => track.stop()); return; }
      streamRef.current?.getTracks().forEach(track => track.stop());
      streamRef.current = stream;
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
      setReady(true);
    } catch (err) { setError(err instanceof Error ? err.message : "Camera access failed."); }
  }

  async function capture() {
    const video = videoRef.current;
    if (!video?.videoWidth || busy) return;
    setBusy(true);
    setError(null);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth; canvas.height = video.videoHeight;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Camera capture unavailable.");
      const files: File[] = [];
      for (let i = 0; i < 3; i++) {
        if (!mountedRef.current) return;
        context.drawImage(video, 0, 0);
        const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
          value => value ? resolve(value) : reject(new Error("Could not capture frame.")), "image/jpeg", 0.9,
        ));
        files.push(new File([blob], `selfie-${i + 1}.jpg`, { type: "image/jpeg" }));
        if (i < 2) await new Promise(resolve => setTimeout(resolve, 500));
      }
      setPhotos(files);
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      previewRef.current = URL.createObjectURL(files[0]);
      setPreview(previewRef.current);
    } catch (err) { setError(err instanceof Error ? err.message : "Capture failed."); }
    finally { if (mountedRef.current) setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <div className="relative overflow-hidden rounded-xl border border-border bg-black aspect-[4/3]">
        <video ref={videoRef} muted playsInline autoPlay className={`h-full w-full object-cover ${photos.length ? "hidden" : ""}`} aria-label="Live camera preview" />
        {photos.length > 0 && preview && <img src={preview} alt="Captured selfie preview" className="h-full w-full object-cover" />}
        {!ready && <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">Your camera starts when you choose Enable camera.</div>}
      </div>
      <p className="text-xs text-muted-foreground">Face the camera in good light. We capture three frames over one second for passive liveness checks.</p>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <div className="flex flex-wrap gap-3">
        {!ready ? <button type="button" onClick={startCamera} className="rounded-lg bg-primary px-4 py-2 text-sm text-white">Enable camera</button>
          : !photos.length ? <button type="button" onClick={capture} disabled={busy || isUploading} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Camera size={16} />}{busy ? "Capturing…" : "Capture frames"}</button>
          : <><button type="button" disabled={isUploading} onClick={() => setPhotos([])} className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm"><RotateCcw size={16} />Retake</button>
            <button type="button" disabled={isUploading} onClick={() => onCapture(photos[0], photos.slice(1))} className="rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50">{isUploading ? "Uploading…" : "Submit three frames"}</button></>}
      </div>
    </div>
  );
}
