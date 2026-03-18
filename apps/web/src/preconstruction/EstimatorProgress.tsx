import { Button } from "@/components/ui/button";

export type EstimatorProgressStep = {
  step: number;
  label: string;
  done: boolean;
  current?: boolean;
};

type Props = {
  title: string;
  steps: EstimatorProgressStep[];
  nextAction?: {
    label: string;
    onClick: () => void;
    disabled?: boolean;
  };
};

function StepMark({ done, current }: { done: boolean; current?: boolean }) {
  if (done) {
    return (
      <span aria-hidden className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-300">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </span>
    );
  }

  if (current) {
    return (
      <span aria-hidden className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary">
        <span className="text-sm font-semibold leading-none">→</span>
      </span>
    );
  }

  return (
    <span aria-hidden className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-border bg-card/40" />
  );
}

export function EstimatorProgress({ title, steps, nextAction }: Props) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      </div>
      <ol className="space-y-1">
        {steps.map((s) => (
          <li key={s.step} className="flex items-start gap-2">
            <StepMark done={s.done} current={s.current} />
            <div className="min-w-0">
              <div className="text-xs font-medium text-foreground/90">
                Step {s.step}: {s.label}
              </div>
            </div>
          </li>
        ))}
      </ol>
      {nextAction ? (
        <div>
          <Button type="button" onClick={nextAction.onClick} disabled={nextAction.disabled}>
            {nextAction.label}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

