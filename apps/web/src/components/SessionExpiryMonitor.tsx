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
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
      <Alert variant="destructive" className="max-w-md shadow-2xl bg-destructive/10 border-destructive/20 text-destructive border-2">
        <AlertCircle className="h-5 w-5" />
        <AlertTitle className="font-bold text-lg">Session Expired</AlertTitle>
        <AlertDescription className="mt-2 text-sm opacity-90">
          Your session has ended for security. Please refresh the page to log back in and continue your work.
        </AlertDescription>
        <div className="mt-6 flex justify-end">
          <Button 
            variant="destructive" 
            onClick={() => window.location.reload()}
            className="font-bold"
          >
            Refresh Now
          </Button>
        </div>
      </Alert>
    </div>
  );
}
