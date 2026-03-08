import { openDB } from "idb";
import type { OfflineMutation } from "../types/api";

const DB_NAME = "construction-daily-report-db";
const DB_VERSION = 1;
const STORE_MUTATIONS = "mutations";

export async function openOfflineDb() {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_MUTATIONS)) {
        db.createObjectStore(STORE_MUTATIONS, { keyPath: "id" });
      }
    }
  });
}

export async function addMutation(mutation: OfflineMutation): Promise<void> {
  const db = await openOfflineDb();
  await db.put(STORE_MUTATIONS, mutation);
}

export async function getMutations(): Promise<OfflineMutation[]> {
  const db = await openOfflineDb();
  return db.getAll(STORE_MUTATIONS);
}

export async function removeMutation(id: string): Promise<void> {
  const db = await openOfflineDb();
  await db.delete(STORE_MUTATIONS, id);
}

export async function countMutations(): Promise<number> {
  const db = await openOfflineDb();
  return db.count(STORE_MUTATIONS);
}
