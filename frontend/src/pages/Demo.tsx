import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ShieldCheck, FlaskConical } from "lucide-react";
import PipelineBreakdown from "@/components/PipelineBreakdown";
import { demoResult, scenarios } from "@/data/demo";
import type { Scenario } from "@/data/demo";

export default function Demo() {
  const [scenario, setScenario] = useState<Scenario>("approved");
  const result = demoResult(scenario);
  const selected = scenarios.find(item => item.id === scenario)!;
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link to="/demo" className="flex items-center gap-3 font-bold text-xl"><ShieldCheck className="text-primary" /> IDV Verify</Link>
          <Link to="/login" className="flex items-center gap-2 text-sm text-primary">Open application <ArrowRight size={16} /></Link>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 max-w-3xl">
          <p className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-primary"><FlaskConical size={16} /> Interactive showcase</p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-5xl">Every decision has evidence.</h1>
          <p className="mt-4 text-muted-foreground leading-relaxed">Explore an identity verification workflow from document acceptance to a clear decision. Switch scenarios to see how missing evidence and hard rules change the outcome.</p>
        </div>
        <div className="mb-8 rounded-xl border border-primary/25 bg-primary/5 p-4 text-sm" role="note">
          <strong>Synthetic demo.</strong> All identities and scores are illustrative fixtures. This page runs locally in your browser; it performs no identity verification and accepts no personal documents.
        </div>
        <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
          <aside>
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-muted-foreground">Choose a scenario</h2>
            <div className="space-y-3" role="group" aria-label="Verification scenarios">
              {scenarios.map(item => (
                <button key={item.id} aria-pressed={scenario === item.id} onClick={() => setScenario(item.id)}
                  className={`w-full rounded-xl border p-4 text-left transition-colors ${scenario === item.id ? "border-primary bg-primary/10" : "border-border bg-card hover:border-primary/50"}`}>
                  <span className="block text-sm font-semibold">{item.title}</span>
                  <span className="mt-2 block text-xs leading-relaxed text-muted-foreground">{item.description}</span>
                </button>
              ))}
            </div>
            <div className="mt-6 rounded-xl border border-border p-4">
              <p className="text-xs font-semibold text-muted-foreground uppercase">Sample applicant</p>
              <p className="mt-2 font-semibold">Alex Sample</p>
              <p className="mt-1 text-xs text-muted-foreground">Passport + national ID + 3 selfie frames</p>
              <p className="mt-4 text-xs leading-relaxed text-muted-foreground">A strong aggregate score never overrides failed liveness or an identity mismatch.</p>
            </div>
          </aside>
          <section aria-label="Verification evidence" aria-live="polite">
            <div className="mb-5"><h2 className="text-xl font-semibold">{selected.title}</h2><p className="mt-1 text-sm text-muted-foreground">{selected.description}</p></div>
            <PipelineBreakdown key={scenario} result={result} />
          </section>
        </div>
      </main>
      <footer className="mx-auto max-w-7xl px-6 py-8 text-xs text-muted-foreground">Research and demonstration software. Model scores require calibration before operational use.</footer>
    </div>
  );
}
