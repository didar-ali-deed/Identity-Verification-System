import { useResetVerification } from "@/api/idv";

export default function ResetVerificationButton({ applicationId, processing = false }: { applicationId: string; processing?: boolean }) {
  const reset = useResetVerification();
  const handleReset = async () => {
    if (!window.confirm("Delete this verification's documents, selfie, results and review history, and start again? Your account will be kept.")) return;
    try {
      await reset.mutateAsync(applicationId);
      window.location.assign("/idv");
    } catch {
      // The mutation error is displayed below.
    }
  };
  const detail = (reset.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail;
  return <div className="space-y-2">
    <button onClick={handleReset} disabled={processing || reset.isPending} className="px-3 py-2 text-sm border border-red-500/30 text-red-400 rounded-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">
      {reset.isPending ? "Resetting…" : "Reset verification"}
    </button>
    {processing && <p className="text-xs text-muted-foreground">Reset is available after processing finishes.</p>}
    {reset.isError && <p role="alert" className="text-xs text-red-400">{detail ?? "Reset failed. Please try again."}</p>}
  </div>;
}
