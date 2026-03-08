import { useEffect, useState } from "react";
import { countMutations } from "../offline/db";
import { flushMutationQueue } from "../offline/queue";

export function useOfflineSync() {
  const [isOnline, setIsOnline] = useState<boolean>(navigator.onLine);
  const [lastFlushedCount, setLastFlushedCount] = useState(0);
  const [queuedCount, setQueuedCount] = useState(0);

  useEffect(() => {
    const sync = async () => {
      setIsOnline(navigator.onLine);
      if (navigator.onLine) {
        const count = await flushMutationQueue();
        setLastFlushedCount(count);
      }
      setQueuedCount(await countMutations());
    };

    const onOnline = () => {
      void sync();
    };
    const onOffline = () => setIsOnline(false);
    const onQueueChanged = () => {
      void countMutations().then((count) => setQueuedCount(count));
    };

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    window.addEventListener("offline-queue-changed", onQueueChanged);
    void sync();

    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("offline-queue-changed", onQueueChanged);
    };
  }, []);

  return { isOnline, lastFlushedCount, queuedCount };
}
