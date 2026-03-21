"use client";

import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function SessionExpiryMonitor() {
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const handleExpiry = () => {
      setExpired(true);
    };

    window.addEventListener("session:expired", handleExpiry);
    return () => window.removeEventListener("session:expired", handleExpiry);
  }, []);

  if (!expired) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[9999] p-2 animate-in fade-in slide-in-from-bottom-5">
      <Alert 
        variant="destructive" 
        className="max-w-md shadow-2xl bg-destructive border-destructive text-destructive-foreground border-2"
      >
        <div className="flex items-start gap-4">
          <AlertCircle className="h-5 w-5 mt-0.5 shrink-0" />
          <div className="flex-1">
            <AlertTitle className="font-bold">Session Expired</AlertTitle>
            <AlertDescription className="mt-1 text-sm opacity-90 pr-4">
              Your session has ended for security. Refresh the page to log back in.
            </AlertDescription>
          </div>
          <Button 
            size="sm"
            variant="secondary" 
            onClick={() => window.location.reload()}
            className="font-bold whitespace-nowrap"
          >
            Refresh
          </Button>
        </div>
      </Alert>
    </div>
  );
}
