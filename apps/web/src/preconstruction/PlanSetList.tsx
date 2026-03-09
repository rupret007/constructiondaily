import type { PlanSet } from "../types/api";

type Props = {
  planSets: PlanSet[];
  selectedPlanSetId: string;
  onSelectPlanSet: (id: string) => void;
};

export function PlanSetList({ planSets, selectedPlanSetId, onSelectPlanSet }: Props) {
  if (planSets.length === 0) {
    return (
      <p className="empty-hint">No plan sets yet. Create one to get started.</p>
    );
  }
  return (
    <div className="report-list">
      {planSets.map((set) => (
        <button
          key={set.id}
          type="button"
          className={`report-row ${selectedPlanSetId === set.id ? "selected" : ""}`}
          onClick={() => onSelectPlanSet(set.id)}
        >
          <span>{set.name}</span>
          <span>{set.status}</span>
        </button>
      ))}
    </div>
  );
}
