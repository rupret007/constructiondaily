import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  createPlanSet,
  fetchPlanSets,
  fetchPlanSheets,
  uploadPlanSheet,
} from "../services/preconstruction";
import type { PlanSet as PlanSetType, PlanSheet as PlanSheetType, Project } from "../types/api";
import { PreconstructionCopilotPanel } from "./PreconstructionCopilotPanel";
import { ProjectDocumentPanel } from "./ProjectDocumentPanel";
import { PlanSetList } from "./PlanSetList";
import { PlanSheetList } from "./PlanSheetList";

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
      onError(e instanceof Error ? e.message : "Failed to load plan sets.");
      setPlanSets([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, selectedPlanSetId, onError]);

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
      onError(e instanceof Error ? e.message : "Failed to load plan sheets.");
      setSheets([]);
    } finally {
      setLoading(false);
    }
  }, [selectedPlanSetId, onError]);

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
      await uploadPlanSheet(selectedPlanSetId, file, { title: title || file.name.replace(/\.(pdf|dxf|dwg)$/i, "") });
      await loadSheets();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to upload sheet.");
    } finally {
      setUploading(false);
    }
  };

  const selectedPlanSet = planSets.find((s) => s.id === selectedPlanSetId);
  const selectedProject = projects.find((project) => project.id === selectedProjectId);

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-[minmax(0,40%)_1fr]">
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>Preconstruction</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="precon-project" className="text-sm font-medium text-foreground">
              Project
            </label>
            <select
              id="precon-project"
              value={selectedProjectId}
              onChange={(e) => onProjectChange(e.target.value)}
              aria-label="Select project"
              className="flex h-11 min-h-[44px] w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} - {p.name}
                </option>
              ))}
            </select>
          </div>
          {!projectId ? (
            <p className="text-sm text-muted-foreground">Select a project to manage plan sets.</p>
          ) : (
            <>
              {showCreateForm ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    type="text"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    placeholder="Plan set name"
                    aria-label="Plan set name"
                    className="min-w-[180px] flex-1"
                  />
                  <Button type="button" onClick={() => void handleCreatePlanSet()}>
                    Create
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setShowCreateForm(false);
                      setCreateName("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <Button type="button" onClick={() => setShowCreateForm(true)}>
                  Create plan set
                </Button>
              )}
              {loading && planSets.length === 0 ? (
                <p className="text-sm text-muted-foreground">Loading...</p>
              ) : (
                <PlanSetList
                  planSets={planSets}
                  selectedPlanSetId={selectedPlanSetId}
                  onSelectPlanSet={setSelectedPlanSetId}
                />
              )}
            </>
          )}
        </CardContent>
      </Card>
      <div className="space-y-6">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>{selectedPlanSet?.name ?? "Plan set"}</CardTitle>
          </CardHeader>
          <CardContent>
            {!selectedPlanSetId ? (
              <p className="text-sm text-muted-foreground">
                Select a plan set to view and upload sheets.
              </p>
            ) : (
              <PlanSheetList
                planSetId={selectedPlanSetId}
                sheets={sheets}
                loading={loading}
                uploading={uploading}
                onUpload={handleUploadSheet}
                onRefresh={loadSheets}
                onOpenSheet={(sheetId) => onOpenSheet(sheetId, selectedPlanSetId)}
              />
            )}
          </CardContent>
        </Card>
        {projectId ? (
          <ProjectDocumentPanel
            projectId={projectId}
            planSetId={selectedPlanSetId || undefined}
            planSetName={selectedPlanSet?.name}
          />
        ) : null}
        {projectId && selectedProject ? (
          <PreconstructionCopilotPanel
            projectId={projectId}
            projectLabel={`${selectedProject.code} - ${selectedProject.name}`}
            planSetId={selectedPlanSetId || undefined}
            planSetName={selectedPlanSet?.name}
          />
        ) : null}
      </div>
    </div>
  );
}
