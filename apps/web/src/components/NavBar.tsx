import type { ApiUser } from "../types/api";

type Props = {
  user: ApiUser;
  onLogout: () => void;
};

export function NavBar({ user, onLogout }: Props) {
  return (
    <header className="navbar">
      <h1>Construction Daily Report</h1>
      <div className="navbar-actions">
        <span>{user.first_name || user.username}</span>
        <button onClick={onLogout}>Logout</button>
      </div>
    </header>
  );
}
