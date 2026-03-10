import { Alert } from "@/components/ui/alert";

type Props = {
  isOnline: boolean;
  lastFlushedCount: number;
  queuedCount: number;
};

export function OfflineBadge({ isOnline, lastFlushedCount, queuedCount }: Props) {
  const message = isOnline
    ? `Online${lastFlushedCount ? ` - synced ${lastFlushedCount} changes` : ""}${
        queuedCount ? ` (${queuedCount} pending)` : ""
      }`
    : `Offline - ${queuedCount} queued changes`;

  return (
    <Alert
      variant={isOnline ? "success" : "destructive"}
      className="mb-4"
    >
      {message}
    </Alert>
  );
}
