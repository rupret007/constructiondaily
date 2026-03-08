type Props = {
  isOnline: boolean;
  lastFlushedCount: number;
  queuedCount: number;
};

export function OfflineBadge({ isOnline, lastFlushedCount, queuedCount }: Props) {
  return (
    <div className={`offline-badge ${isOnline ? "online" : "offline"}`}>
      {isOnline
        ? `Online${lastFlushedCount ? ` - synced ${lastFlushedCount} changes` : ""}${
            queuedCount ? ` (${queuedCount} pending)` : ""
          }`
        : `Offline - ${queuedCount} queued changes`}
    </div>
  );
}
