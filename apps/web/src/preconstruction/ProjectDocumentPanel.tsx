import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  fetchProjectDocuments,
  projectDocumentFileUrl,
  uploadProjectDocument,
} from "../services/preconstruction";
import type { ProjectDocument } from "../types/api";

type Props = {
  projectId: string;
  planSetId?: string;
  planSetName?: string | null;
};

const DOCUMENT_TYPE_LABELS: Record<ProjectDocument["document_type"], string> = {
  spec: "Specification",
  addendum: "Addendum",
  rfi: "RFI",
  submittal: "Submittal",
  vendor: "Vendor",
  scope: "Scope",
  other: "Other",
};

export function ProjectDocumentPanel({ projectId, planSetId, planSetName }: Props) {
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [documentType, setDocumentType] = useState<ProjectDocument["document_type"]>("spec");
  const [scopeMode, setScopeMode] = useState<"project" | "plan_set">(planSetId ? "plan_set" : "project");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setScopeMode(planSetId ? "plan_set" : "project");
  }, [planSetId]);

  const loadDocuments = useCallback(async () => {
    if (!projectId) {
      setDocuments([]);
      return;
    }
    setLoading(true);
    try {
      const list = await fetchProjectDocuments(projectId, {
        planSetId,
        scopedToPlanSet: Boolean(planSetId),
      });
      setDocuments(list);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project documents.");
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, planSetId]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !projectId) {
      return;
    }
    setUploading(true);
    try {
      await uploadProjectDocument(projectId, file, {
        document_type: documentType,
        title: title.trim() || undefined,
        plan_set: planSetId && scopeMode === "plan_set" ? planSetId : null,
      });
      setTitle("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload project document.");
    } finally {
      setUploading(false);
    }
  };

  const helperText = useMemo(() => {
    if (planSetId && planSetName) {
      return `Showing project-wide documents plus documents scoped to ${planSetName}.`;
    }
    return "Upload project-wide specs, addenda, RFIs, submittals, or vendor docs for grounded copilot answers.";
  }, [planSetId, planSetName]);

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Project Documents</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{helperText}</p>
        {error ? <Alert variant="destructive">{error}</Alert> : null}
        <div className="flex flex-wrap gap-2">
          <select
            value={documentType}
            onChange={(event) => setDocumentType(event.target.value as ProjectDocument["document_type"])}
            aria-label="Document type"
            className="flex h-11 min-h-[44px] rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {Object.entries(DOCUMENT_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {planSetId ? (
            <select
              value={scopeMode}
              onChange={(event) => setScopeMode(event.target.value as "project" | "plan_set")}
              aria-label="Document scope"
              className="flex h-11 min-h-[44px] rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option value="plan_set">Selected plan set</option>
              <option value="project">Project-wide</option>
            </select>
          ) : null}
          <Input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Document title (optional)"
            aria-label="Document title"
            className="min-w-[200px] flex-1"
          />
          <label className="flex min-h-11 min-w-[44px] cursor-pointer items-center justify-center rounded-md border border-input bg-secondary px-4 py-2 text-sm font-medium text-secondary-foreground hover:bg-secondary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 has-[:disabled]:pointer-events-none has-[:disabled]:opacity-50">
            <span className="sr-only">Upload project document</span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
              onChange={handleFileChange}
              className="hidden"
              disabled={uploading}
            />
            {uploading ? "Uploading..." : "Upload Document"}
          </label>
          <Button type="button" variant="outline" onClick={() => void loadDocuments()} disabled={loading}>
            Refresh
          </Button>
        </div>
        {loading && documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">Loading documents...</p>
        ) : documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No project documents in scope yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {documents.map((document) => {
              const scopeLabel = document.plan_set
                ? planSetId && document.plan_set === planSetId && planSetName
                  ? planSetName
                  : "Plan set document"
                : "Project-wide";
              return (
                <div
                  key={document.id}
                  className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-muted/40 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-foreground">{document.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {DOCUMENT_TYPE_LABELS[document.document_type]} · {scopeLabel} · {document.parse_status}
                      {document.page_count ? ` · ${document.page_count} page${document.page_count === 1 ? "" : "s"}` : ""}
                    </p>
                    {document.parse_error ? (
                      <p className="text-xs text-destructive">{document.parse_error}</p>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => window.open(projectDocumentFileUrl(document.id), "_blank", "noopener,noreferrer")}
                  >
                    Open
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
