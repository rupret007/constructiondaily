import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PlanSet } from "../types/api";

type Props = {
  planSets: PlanSet[];
  selectedPlanSetId: string;
  onSelectPlanSet: (id: string) => void;
};

export function PlanSetList({ planSets, selectedPlanSetId, onSelectPlanSet }: Props) {
  if (planSets.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No plan sets yet. Create one to get started.</p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {planSets.map((set) => (
        <Button
          key={set.id}
          type="button"
          variant={selectedPlanSetId === set.id ? "default" : "outline"}
          className={cn(
            "h-auto min-h-11 justify-between py-3 text-left font-normal",
            selectedPlanSetId === set.id ? "ring-2 ring-ring ring-offset-2" : ""
          )}
          onClick={() => onSelectPlanSet(set.id)}
        >
          <span>{set.name}</span>
          <span className="text-xs opacity-90">{set.status}</span>
        </Button>
      ))}
    </div>
  );
}
