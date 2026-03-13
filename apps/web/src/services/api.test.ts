import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";

describe("apiRequest", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    document.cookie = "";
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("reuses csrfToken returned by the session endpoint for later writes", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ authenticated: false, csrfToken: "session-token-123" }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

    global.fetch = fetchMock as typeof fetch;

    await apiRequest("/auth/session/");
    await apiRequest("/preconstruction/sets/", {
      method: "POST",
      body: JSON.stringify({ project: "p1", name: "Set A" }),
    });

    const secondCallHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers as HeadersInit);
    expect(secondCallHeaders.get("X-CSRFToken")).toBe("session-token-123");
  });
});
