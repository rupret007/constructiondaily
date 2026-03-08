import { useState } from "react";

type Props = {
  onSubmit: (username: string, password: string) => Promise<void>;
};

export function LoginForm({ onSubmit }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  return (
    <form
      className="card login-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        try {
          await onSubmit(username, password);
        } catch (err) {
          if (err instanceof Error && err.message) {
            setError(err.message);
            return;
          }
          setError("Invalid username or password.");
        }
      }}
    >
      <h2>Sign in</h2>
      <label>
        Username
        <input value={username} onChange={(event) => setUsername(event.target.value)} required />
      </label>
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          autoComplete="current-password"
        />
      </label>
      {error && <p className="error-text">{error}</p>}
      <button type="submit">Login</button>
    </form>
  );
}
