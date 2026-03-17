import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProjectDocumentPanel } from "./ProjectDocumentPanel";

const fetchProjectDocuments = vi.fn();
const uploadProjectDocument = vi.fn();

vi.mock("../services/preconstruction", () => ({
  fetchProjectDocuments: (...args: unknown[]) => fetchProjectDocuments(...args),
  uploadProjectDocument: (...args: unknown[]) => uploadProjectDocument(...args),
  projectDocumentFileUrl: (documentId: string) => `/api/preconstruction/documents/${documentId}/file/`,
}));

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

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

  it("disables downloads for documents that did not parse", async () => {
    fetchProjectDocuments.mockResolvedValue([
      {
        id: "doc-3",
        project: "project-1",
        plan_set: null,
        title: "Broken Spec",
        document_type: "spec",
        original_filename: "broken-spec.pdf",
        storage_key: "project_documents/project-1/project/quarantine/broken-spec.pdf",
        mime_type: "application/pdf",
        file_extension: "pdf",
        size_bytes: 512,
        page_count: 0,
        parse_status: "failed",
        parse_error: "Synthetic parser failure",
        created_at: "2026-03-13T12:00:00Z",
        updated_at: "2026-03-13T12:00:00Z",
      },
    ]);

    render(<ProjectDocumentPanel projectId="project-1" />);

    expect(await screen.findByText("Broken Spec")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /unavailable/i })).toBeDisabled();
  });

  it("clears stale documents and ignores old responses when scope changes", async () => {
    const secondLoad = createDeferred<
      Array<{
        id: string;
        project: string;
        plan_set: string | null;
        title: string;
        document_type: "spec";
        original_filename: string;
        storage_key: string;
        mime_type: string;
        file_extension: string;
        size_bytes: number;
        page_count: number;
        parse_status: "parsed";
        parse_error: string;
        created_at: string;
        updated_at: string;
      }>
    >();
    fetchProjectDocuments
      .mockResolvedValueOnce([
        {
          id: "doc-4",
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
      ])
      .mockImplementationOnce(() => secondLoad.promise);

    const { rerender } = render(
      <ProjectDocumentPanel
        projectId="project-1"
        planSetId="set-1"
        planSetName="Pricing Set"
      />
    );

    expect(await screen.findByText("Door Hardware Spec")).toBeInTheDocument();

    rerender(<ProjectDocumentPanel projectId="project-2" />);

    await waitFor(() => expect(screen.queryByText("Door Hardware Spec")).not.toBeInTheDocument());

    secondLoad.resolve([
      {
        id: "doc-5",
        project: "project-2",
        plan_set: null,
        title: "Project Two Spec",
        document_type: "spec",
        original_filename: "project-two.pdf",
        storage_key: "project_documents/project-2/project/project-two.pdf",
        mime_type: "application/pdf",
        file_extension: "pdf",
        size_bytes: 1000,
        page_count: 1,
        parse_status: "parsed",
        parse_error: "",
        created_at: "2026-03-13T12:00:00Z",
        updated_at: "2026-03-13T12:00:00Z",
      },
    ]);

    expect(await screen.findByText("Project Two Spec")).toBeInTheDocument();
  });
});
