import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

interface Step {
  title: string;
  description: string;
}

interface StepWizardProps {
  steps: Step[];
  currentStep: number;
}

export default function StepWizard({ steps, currentStep }: StepWizardProps) {
  return (
    <nav className="mb-8">
      <ol className="flex items-center">
        {steps.map((step, index) => (
          <li
            key={step.title}
            className={cn(
              "flex items-center",
              index < steps.length - 1 && "flex-1",
            )}
          >
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium border-2 shrink-0",
                  index < currentStep
                    ? "bg-primary border-primary text-primary-foreground"
                    : index === currentStep
                      ? "border-primary text-primary bg-white"
                      : "border-border text-muted-foreground bg-white",
                )}
              >
                {index < currentStep ? (
                  <Check className="h-4 w-4" />
                ) : (
                  index + 1
                )}
              </div>
              <div className="hidden sm:block">
                <p
                  className={cn(
                    "text-sm font-medium",
                    index <= currentStep
                      ? "text-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  {step.title}
                </p>
                <p className="text-xs text-muted-foreground">
                  {step.description}
                </p>
              </div>
            </div>
            {index < steps.length - 1 && (
              <div
                className={cn(
                  "flex-1 h-0.5 mx-4",
                  index < currentStep ? "bg-primary" : "bg-border",
                )}
              />
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
