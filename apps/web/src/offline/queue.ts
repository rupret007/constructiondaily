import { addMutation, getMutations, removeMutation } from "./db";
import { apiRequest } from "../services/api";
import type { OfflineMutation } from "../types/api";

export async function enqueueMutation(mutation: Omit<OfflineMutation, "id" | "createdAt">) {
  const queued: OfflineMutation = {
    ...mutation,
    id: crypto.randomUUID(),
    createdAt: Date.now()
  };
  await addMutation(queued);
  window.dispatchEvent(new CustomEvent("offline-queue-changed"));
}

export async function flushMutationQueue(): Promise<number> {
  const mutations = await getMutations();
  let flushed = 0;
  for (const mutation of mutations.sort((a, b) => a.createdAt - b.createdAt)) {
    try {
      await apiRequest(mutation.endpoint, {
        method: mutation.method,
        body: JSON.stringify(mutation.payload)
      });
      await removeMutation(mutation.id);
      flushed += 1;
      window.dispatchEvent(new CustomEvent("offline-queue-changed"));
    } catch {
      // Stop processing to preserve ordering and retry later.
      break;
    }
  }
  return flushed;
}
