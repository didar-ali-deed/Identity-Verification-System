import { Link } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import {
  FileCheck,
  Shield,
  Clock,
  CheckCircle2,
  LayoutDashboard,
  ArrowRight,
  ScanLine,
  Fingerprint,
  Lock,
} from "lucide-react";

const steps = [
  { step: "01", title: "Upload Document", desc: "Passport, national ID, or driver's license", icon: FileCheck },
  { step: "02", title: "Take Selfie", desc: "Live photo for face matching", icon: Fingerprint },
  { step: "03", title: "AI Processing", desc: "OCR, face match, and fraud detection", icon: ScanLine },
  { step: "04", title: "Verification", desc: "Admin reviews and final decision", icon: CheckCircle2 },
];

export default function Home() {
  const { user } = useAuthStore();

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold text-primary uppercase tracking-widest mb-1">
            Identity Verification
          </p>
          <h1 className="text-3xl font-bold text-foreground">
            Welcome, {user?.full_name?.split(" ")[0]}
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Manage your identity verification from this dashboard
          </p>
        </div>
        <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground bg-muted border border-border rounded-full px-3 py-1.5">
          <Lock className="h-3 w-3 text-primary" />
          Encrypted &amp; Secure
        </div>
      </div>

      {/* Action cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <Link
          to="/idv"
          className="group block p-6 bg-card border border-border rounded-xl no-underline card-hover relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 w-24 h-24 bg-primary/5 rounded-full -translate-y-8 translate-x-8 group-hover:bg-primary/10 transition-colors" />
          <FileCheck className="h-9 w-9 text-primary mb-4" />
          <h2 className="text-base font-semibold text-foreground">Start Verification</h2>
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
            Submit your identity documents for verification
          </p>
          <div className="flex items-center gap-1 mt-4 text-xs text-primary font-medium">
            Get started <ArrowRight className="h-3 w-3" />
          </div>
        </Link>

        <Link
          to="/idv/status"
          className="group block p-6 bg-card border border-border rounded-xl no-underline card-hover relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 w-24 h-24 bg-warning/5 rounded-full -translate-y-8 translate-x-8 group-hover:bg-warning/10 transition-colors" />
          <Clock className="h-9 w-9 text-warning mb-4" />
          <h2 className="text-base font-semibold text-foreground">Check Status</h2>
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
            View the progress of your IDV application
          </p>
          <div className="flex items-center gap-1 mt-4 text-xs text-warning font-medium">
            View status <ArrowRight className="h-3 w-3" />
          </div>
        </Link>

        <div className="p-6 bg-card border border-border rounded-xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-24 h-24 bg-success/5 rounded-full -translate-y-8 translate-x-8" />
          <CheckCircle2 className="h-9 w-9 text-success mb-4" />
          <h2 className="text-base font-semibold text-foreground">Security First</h2>
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
            Your data is encrypted and processed securely
          </p>
          <div className="flex items-center gap-1 mt-4 text-xs text-success font-medium">
            <Lock className="h-3 w-3" /> AES-256 encrypted
          </div>
        </div>

        {user?.role === "admin" && (
          <Link
            to="/admin"
            className="group block p-6 bg-card border border-primary/20 rounded-xl no-underline card-hover relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-24 h-24 bg-primary/5 rounded-full -translate-y-8 translate-x-8 group-hover:bg-primary/10 transition-colors" />
            <LayoutDashboard className="h-9 w-9 text-primary mb-4" />
            <h2 className="text-base font-semibold text-foreground">Admin Dashboard</h2>
            <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
              Review and manage IDV applications
            </p>
            <div className="flex items-center gap-1 mt-4 text-xs text-primary font-medium">
              Open dashboard <ArrowRight className="h-3 w-3" />
            </div>
          </Link>
        )}
      </div>

      {/* How it works */}
      <div className="bg-card border border-border rounded-xl p-6 sm:p-8">
        <div className="flex items-center gap-3 mb-6">
          <Shield className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">How Identity Verification Works</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 sm:gap-6">
          {steps.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.step} className="relative">
                <div className="flex flex-col items-center text-center">
                  <div className="relative mb-3">
                    <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                      <Icon className="h-5 w-5 text-primary" />
                    </div>
                    <span
                      className="absolute -top-2 -right-2 text-[10px] font-bold text-primary/60"
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {item.step}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-foreground">{item.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{item.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
