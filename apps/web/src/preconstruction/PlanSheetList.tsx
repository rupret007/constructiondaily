import { useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { PlanSheet } from "../types/api";

type Props = {
  planSetId: string;
  sheets: PlanSheet[];
  loading: boolean;
  uploading: boolean;
  onUpload: (file: File, title?: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  onOpenSheet: (sheetId: string) => void;
};

export function PlanSheetList({
  sheets,
  loading,
  uploading,
  onUpload,
  onRefresh,
  onOpenSheet,
}: Props) {
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError("");
    try {
      await onUpload(file, uploadTitle.trim() || undefined);
      setUploadTitle("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="text"
          placeholder="Sheet title (optional)"
          value={uploadTitle}
          onChange={(e) => setUploadTitle(e.target.value)}
          aria-label="Sheet title"
          className="min-w-[160px] flex-1"
        />
        <label className="flex min-h-11 min-w-[44px] cursor-pointer items-center justify-center rounded-md border border-input bg-secondary px-4 py-2 text-sm font-medium text-secondary-foreground hover:bg-secondary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 has-[:disabled]:pointer-events-none has-[:disabled]:opacity-50">
          <span className="sr-only">Upload plan file</span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.dxf,.dwg,application/pdf,application/dxf,application/x-dxf,application/acad,image/vnd.dwg"
            onChange={handleFileChange}
            className="hidden"
            disabled={uploading}
          />
          {uploading ? "Uploading..." : "Upload Plan"}
        </label>
        <Button type="button" variant="outline" onClick={() => void onRefresh()} disabled={loading}>
          Refresh
        </Button>
      </div>
      {uploadError && (
        <Alert variant="destructive">{uploadError}</Alert>
      )}
      {loading && sheets.length === 0 ? (
        <p className="text-sm text-muted-foreground">Loading sheets...</p>
      ) : sheets.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Add plan sheets (PDF, DXF, DWG) to start.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {sheets.map((sheet) => (
            <div
              key={sheet.id}
              className={cn(
                "flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-muted/40 px-3 py-2"
              )}
            >
              <span className="font-medium text-foreground">
                {sheet.title || sheet.sheet_number || sheet.id.slice(0, 8)}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{sheet.file_type.toUpperCase()}</span>
                <span className="text-xs text-muted-foreground">{sheet.parse_status}</span>
                <Button type="button" size="sm" onClick={() => onOpenSheet(sheet.id)}>
                  Open
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
