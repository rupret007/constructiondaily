import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../offline/db", () => ({
  countMutations: vi.fn(),
}));

vi.mock("../offline/queue", () => ({
  flushMutationQueue: vi.fn(),
}));

import { countMutations } from "../offline/db";
import { flushMutationQueue } from "../offline/queue";
import { useOfflineSync } from "./useOfflineSync";

describe("useOfflineSync", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: true,
    });
    vi.mocked(countMutations).mockResolvedValue(0);
    vi.mocked(flushMutationQueue).mockResolvedValue(1);
  });

  it("increments the flush id even when consecutive syncs flush the same number of changes", async () => {
    const { result } = renderHook(() => useOfflineSync());

    await waitFor(() => expect(result.current.lastFlushId).toBe(1));
    expect(result.current.lastFlushedCount).toBe(1);

    act(() => {
      window.dispatchEvent(new Event("online"));
    });

    await waitFor(() => expect(result.current.lastFlushId).toBe(2));
    expect(result.current.lastFlushedCount).toBe(1);
  });
});
