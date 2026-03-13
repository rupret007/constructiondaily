import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProjectDocumentPanel } from "./ProjectDocumentPanel";

const fetchProjectDocuments = vi.fn();
const uploadProjectDocument = vi.fn();

vi.mock("../services/preconstruction", () => ({
  fetchProjectDocuments: (...args: unknown[]) => fetchProjectDocuments(...args),
  uploadProjectDocument: (...args: unknown[]) => uploadProjectDocument(...args),
  projectDocumentFileUrl: (documentId: string) => `/api/preconstruction/documents/${documentId}/file/`,
}));

describe("ProjectDocumentPanel", () => {
  beforeEach(() => {
    fetchProjectDocuments.mockReset();
    uploadProjectDocument.mockReset();
  });

  it("loads scoped documents and renders them", async () => {
    fetchProjectDocuments.mockResolvedValue([
      {
        id: "doc-1",
        project: "project-1",
        plan_set: "set-1",
        title: "Door Hardware Spec",
        document_type: "spec",
        original_filename: "door-spec.pdf",
        storage_key: "project_documents/project-1/set-1/doc.pdf",
        mime_type: "application/pdf",
        file_extension: "pdf",
        size_bytes: 1000,
        page_count: 2,
        parse_status: "parsed",
        parse_error: "",
        created_at: "2026-03-13T12:00:00Z",
        updated_at: "2026-03-13T12:00:00Z",
      },
    ]);

    render(
      <ProjectDocumentPanel
        projectId="project-1"
        planSetId="set-1"
        planSetName="Pricing Set"
      />
    );

    expect(fetchProjectDocuments).toHaveBeenCalledWith("project-1", {
      planSetId: "set-1",
      scopedToPlanSet: true,
    });
    expect(await screen.findByText("Door Hardware Spec")).toBeInTheDocument();
    expect(screen.getByText(/showing project-wide documents plus documents scoped to pricing set/i)).toBeInTheDocument();
  });

  it("uploads a selected plan-set document and reloads the list", async () => {
    fetchProjectDocuments
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "doc-2",
          project: "project-1",
          plan_set: "set-1",
          title: "RFI 12",
          document_type: "rfi",
          original_filename: "rfi-12.txt",
          storage_key: "project_documents/project-1/set-1/rfi-12.txt",
          mime_type: "text/plain",
          file_extension: "txt",
          size_bytes: 200,
          page_count: 1,
          parse_status: "parsed",
          parse_error: "",
          created_at: "2026-03-13T12:00:00Z",
          updated_at: "2026-03-13T12:00:00Z",
        },
      ]);
    uploadProjectDocument.mockResolvedValue({
      id: "doc-2",
      project: "project-1",
      plan_set: "set-1",
      title: "RFI 12",
      document_type: "rfi",
      original_filename: "rfi-12.txt",
      storage_key: "project_documents/project-1/set-1/rfi-12.txt",
      mime_type: "text/plain",
      file_extension: "txt",
      size_bytes: 200,
      page_count: 1,
      parse_status: "parsed",
      parse_error: "",
      created_at: "2026-03-13T12:00:00Z",
      updated_at: "2026-03-13T12:00:00Z",
    });

    render(
      <ProjectDocumentPanel
        projectId="project-1"
        planSetId="set-1"
        planSetName="Pricing Set"
      />
    );

    await userEvent.selectOptions(screen.getByLabelText(/document type/i), "rfi");
    await userEvent.type(screen.getByLabelText(/document title/i), "RFI 12");
    const fileInput = screen.getByLabelText(/upload project document/i);
    await userEvent.upload(fileInput, new File(["RFI answer text"], "rfi-12.txt", { type: "text/plain" }));

    expect(uploadProjectDocument).toHaveBeenCalledWith(
      "project-1",
      expect.any(File),
      {
        document_type: "rfi",
        title: "RFI 12",
        plan_set: "set-1",
      }
    );
    expect(await screen.findByText("RFI 12")).toBeInTheDocument();
  });
});
