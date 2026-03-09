import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NavBar } from "./NavBar";

describe("NavBar", () => {
  const user = { username: "testuser", first_name: "Test", last_name: "User" };

  it("renders app title and tabs", () => {
    render(
      <NavBar
        user={user}
        area="reports"
        onAreaChange={() => {}}
        onLogout={() => {}}
      />
    );
    expect(screen.getByText("Construction Daily Report")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /daily reports/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preconstruction/i })).toBeInTheDocument();
  });

  it("shows user display name", () => {
    render(
      <NavBar
        user={user}
        area="reports"
        onAreaChange={() => {}}
        onLogout={() => {}}
      />
    );
    expect(screen.getByText("Test")).toBeInTheDocument();
  });

  it("calls onAreaChange when Preconstruction is clicked", async () => {
    const onAreaChange = vi.fn();
    render(
      <NavBar
        user={user}
        area="reports"
        onAreaChange={onAreaChange}
        onLogout={() => {}}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /preconstruction/i }));
    expect(onAreaChange).toHaveBeenCalledWith("preconstruction");
  });

  it("calls onLogout when Logout is clicked", async () => {
    const onLogout = vi.fn();
    render(
      <NavBar
        user={user}
        area="reports"
        onAreaChange={() => {}}
        onLogout={onLogout}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /logout/i }));
    expect(onLogout).toHaveBeenCalled();
  });
});
