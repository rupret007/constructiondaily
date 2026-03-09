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
    <header className="navbar">
      <h1>Construction Daily Report</h1>
      <nav className="navbar-tabs" aria-label="Main sections">
        <button
          type="button"
          className={area === "reports" ? "navbar-tab active" : "navbar-tab"}
          onClick={() => onAreaChange("reports")}
        >
          Daily Reports
        </button>
        <button
          type="button"
          className={area === "preconstruction" ? "navbar-tab active" : "navbar-tab"}
          onClick={() => onAreaChange("preconstruction")}
        >
          Preconstruction
        </button>
      </nav>
      <div className="navbar-actions">
        <span>{user.first_name || user.username}</span>
        <button onClick={onLogout}>Logout</button>
      </div>
    </header>
  );
}
