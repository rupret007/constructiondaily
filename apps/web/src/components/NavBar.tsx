import { Button } from "@/components/ui/button";
import type { ApiUser } from "../types/api";

export type AppArea = "reports" | "preconstruction";

type Theme = "light" | "dark";

type Props = {
  user: ApiUser;
  area: AppArea;
  onAreaChange: (area: AppArea) => void;
  onLogout: () => void;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
};

function SunIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </svg>
  );
}

export function NavBar({ user, area, onAreaChange, onLogout, theme, onThemeChange }: Props) {
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
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => onThemeChange(theme === "dark" ? "light" : "dark")}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={theme === "dark" ? "Light mode" : "Dark mode"}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </Button>
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
