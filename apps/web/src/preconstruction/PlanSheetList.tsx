import { useRef, useState } from "react";
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
    <>
      <div className="row">
        <input
          type="text"
          placeholder="Sheet title (optional)"
          value={uploadTitle}
          onChange={(e) => setUploadTitle(e.target.value)}
          aria-label="Sheet title"
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          aria-label="Upload PDF"
          disabled={uploading}
        />
        <button type="button" onClick={() => void onRefresh()} disabled={loading}>
          Refresh
        </button>
      </div>
      {uploading && <p>Uploading…</p>}
      {uploadError && <p className="error-text">{uploadError}</p>}
      {loading && sheets.length === 0 ? (
        <p>Loading sheets…</p>
      ) : sheets.length === 0 ? (
        <p className="empty-hint">No sheets yet. Upload a PDF plan to get started.</p>
      ) : (
        <div className="report-list">
          {sheets.map((sheet) => (
            <div key={sheet.id} className="report-row report-row-sheet">
              <span>{sheet.title || sheet.sheet_number || sheet.id.slice(0, 8)}</span>
              <span>{sheet.parse_status}</span>
              <button type="button" onClick={() => onOpenSheet(sheet.id)}>
                Open
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
