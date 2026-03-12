import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./db", () => ({
  addMutation: vi.fn(),
  getMutations: vi.fn(),
  removeMutation: vi.fn(),
}));

vi.mock("../services/api", async () => {
  const actual = await vi.importActual<typeof import("../services/api")>("../services/api");
  return {
    ...actual,
    apiRequest: vi.fn(),
  };
});

import { getMutations, removeMutation } from "./db";
import { ApiRequestError, apiRequest } from "../services/api";
import { flushMutationQueue } from "./queue";
import type { OfflineMutation } from "../types/api";

function queuedMutation(id: string, createdAt: number): OfflineMutation {
  return {
    id,
    method: "POST",
    endpoint: `/reports/daily/${id}/reject/`,
    payload: { reason: "value", revision: 1 },
    createdAt,
  };
}

describe("flushMutationQueue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("drops non-retryable 4xx mutation and continues flushing remaining queue", async () => {
    const first = queuedMutation("a", 1);
    const second = queuedMutation("b", 2);
    vi.mocked(getMutations).mockResolvedValue([first, second]);
    vi.mocked(apiRequest)
      .mockRejectedValueOnce(new ApiRequestError("Validation failed.", 400))
      .mockResolvedValueOnce(undefined);
    vi.mocked(removeMutation).mockResolvedValue(undefined);

    const flushed = await flushMutationQueue();

    expect(flushed).toBe(1);
    expect(apiRequest).toHaveBeenCalledTimes(2);
    expect(removeMutation).toHaveBeenNthCalledWith(1, "a");
    expect(removeMutation).toHaveBeenNthCalledWith(2, "b");
  });

  it("stops queue flush on retryable/server errors to preserve ordering", async () => {
    const first = queuedMutation("a", 1);
    const second = queuedMutation("b", 2);
    vi.mocked(getMutations).mockResolvedValue([first, second]);
    vi.mocked(apiRequest).mockRejectedValueOnce(new ApiRequestError("Server error.", 503));

    const flushed = await flushMutationQueue();

    expect(flushed).toBe(0);
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(removeMutation).not.toHaveBeenCalled();
  });

  it("keeps auth failures in queue so they can retry after re-authentication", async () => {
    const first = queuedMutation("a", 1);
    const second = queuedMutation("b", 2);
    vi.mocked(getMutations).mockResolvedValue([first, second]);
    vi.mocked(apiRequest).mockRejectedValueOnce(new ApiRequestError("Unauthorized.", 401));

    const flushed = await flushMutationQueue();

    expect(flushed).toBe(0);
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(removeMutation).not.toHaveBeenCalled();
  });
});
