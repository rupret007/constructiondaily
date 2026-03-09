import { Button } from "@/components/ui/button";
import type { ApiUser } from "../types/api";

export type AppArea = "reports" | "preconstruction";

type Props = {
  user: ApiUser;
  area: AppArea;
  onAreaChange: (area: AppArea) => void;
  onLogout: () => void;
};

export function NavBar({ user, area, onAreaChange, onLogout }: Props) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border bg-card px-4 py-3 shadow-sm">
      <h1 className="text-xl font-semibold tracking-tight text-foreground">
        Construction Daily Report
      </h1>
      <nav className="flex items-center gap-1" aria-label="Main sections">
        <Button
          type="button"
          variant={area === "reports" ? "default" : "ghost"}
          size="default"
          onClick={() => onAreaChange("reports")}
        >
          Daily Reports
        </Button>
        <Button
          type="button"
          variant={area === "preconstruction" ? "default" : "ghost"}
          size="default"
          onClick={() => onAreaChange("preconstruction")}
        >
          Preconstruction
        </Button>
      </nav>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {user.first_name || user.username}
        </span>
        <Button type="button" variant="outline" size="default" onClick={onLogout}>
          Logout
        </Button>
      </div>
    </header>
  );
}
