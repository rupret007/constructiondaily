import { useCallback, useEffect, useState } from "react";
import {
  createPlanSet,
  fetchPlanSets,
  fetchPlanSheets,
  uploadPlanSheet,
} from "../services/preconstruction";
import type { PlanSet as PlanSetType, PlanSheet as PlanSheetType, Project } from "../types/api";
import { PlanSetList } from "./PlanSetList";
import { PlanSheetList } from "./PlanSheetList";

type AreaView = "sets" | "sheets";

type Props = {
  projectId: string;
  projects: Project[];
  selectedProjectId: string;
  onProjectChange: (projectId: string) => void;
  onOpenSheet: (sheetId: string, planSetId: string) => void;
  error: string;
  onClearError: () => void;
  onError: (message: string) => void;
};

export function PreconstructionDashboard({
  projectId,
  projects,
  selectedProjectId,
  onProjectChange,
  onOpenSheet,
  error,
  onClearError,
  onError,
}: Props) {
  const [planSets, setPlanSets] = useState<PlanSetType[]>([]);
  const [selectedPlanSetId, setSelectedPlanSetId] = useState<string>("");
  const [sheets, setSheets] = useState<PlanSheetType[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [createName, setCreateName] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);

  const loadPlanSets = useCallback(async () => {
    if (!projectId) {
      setPlanSets([]);
      setSelectedPlanSetId("");
      setSheets([]);
      return;
    }
    setLoading(true);
    try {
      const list = await fetchPlanSets(projectId);
      setPlanSets(list);
      if (selectedPlanSetId && !list.some((s) => s.id === selectedPlanSetId)) {
        setSelectedPlanSetId("");
        setSheets([]);
      }
    } catch (e) {
      onClearError();
      setPlanSets([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, selectedPlanSetId]);

  useEffect(() => {
    void loadPlanSets();
  }, [loadPlanSets]);

  const loadSheets = useCallback(async () => {
    if (!selectedPlanSetId) {
      setSheets([]);
      return;
    }
    setLoading(true);
    try {
      const list = await fetchPlanSheets(selectedPlanSetId);
      setSheets(list);
    } catch (e) {
      setSheets([]);
    } finally {
      setLoading(false);
    }
  }, [selectedPlanSetId]);

  useEffect(() => {
    void loadSheets();
  }, [loadSheets]);

  const handleCreatePlanSet = async () => {
    if (!projectId || !createName.trim()) return;
    onClearError();
    try {
      await createPlanSet({
        project: projectId,
        name: createName.trim(),
      });
      setCreateName("");
      setShowCreateForm(false);
      await loadPlanSets();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to create plan set.");
    }
  };

  const handleUploadSheet = async (file: File, title?: string) => {
    if (!selectedPlanSetId) return;
    setUploading(true);
    onClearError();
    try {
      await uploadPlanSheet(selectedPlanSetId, file, { title: title || file.name.replace(/\.pdf$/i, "") });
      await loadSheets();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to upload sheet.");
    } finally {
      setUploading(false);
    }
  };

  const selectedPlanSet = planSets.find((s) => s.id === selectedPlanSetId);

  return (
    <div className="layout">
      <section className="card preconstruction-sidebar">
        <h2>Preconstruction</h2>
        <div className="row">
          <select
            value={selectedProjectId}
            onChange={(e) => onProjectChange(e.target.value)}
            aria-label="Select project"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} — {p.name}
              </option>
            ))}
          </select>
        </div>
        {!projectId ? (
          <p className="empty-hint">Select a project to manage plan sets.</p>
        ) : (
          <>
            {showCreateForm ? (
              <div className="row">
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="Plan set name"
                  aria-label="Plan set name"
                />
                <button type="button" onClick={() => void handleCreatePlanSet()}>
                  Create
                </button>
                <button type="button" onClick={() => { setShowCreateForm(false); setCreateName(""); }}>
                  Cancel
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => setShowCreateForm(true)}>
                Create plan set
              </button>
            )}
            {loading && planSets.length === 0 ? (
              <p>Loading…</p>
            ) : (
              <PlanSetList
                planSets={planSets}
                selectedPlanSetId={selectedPlanSetId}
                onSelectPlanSet={setSelectedPlanSetId}
              />
            )}
          </>
        )}
      </section>
      <section className="card preconstruction-main">
        {!selectedPlanSetId ? (
          <p className="empty-hint">Select a plan set to view and upload sheets.</p>
        ) : (
          <>
            <h3>{selectedPlanSet?.name ?? "Plan set"}</h3>
            <PlanSheetList
              planSetId={selectedPlanSetId}
              sheets={sheets}
              loading={loading}
              uploading={uploading}
              onUpload={handleUploadSheet}
              onRefresh={loadSheets}
              onOpenSheet={(sheetId) => onOpenSheet(sheetId, selectedPlanSetId)}
            />
          </>
        )}
      </section>
    </div>
  );
}
