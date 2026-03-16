import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchPlanSetEstimatingDashboard } from "../services/preconstruction";
import type { PlanSetEstimatingDashboard } from "../types/api";

type Props = {
  planSetId: string;
  planSetName?: string | null;
  refreshKey?: number;
  onOpenSheet: (sheetId: string) => void;
};

function formatTokenLabel(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatSheetLabel(row: PlanSetEstimatingDashboard["sheet_rollups"][number]): string {
  return row.sheet_number || row.title || row.id.slice(0, 8);
}

function formatTimestamp(value: string | null): string {
  if (!value) return "None yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function PlanSetEstimatingDashboard({
  planSetId,
  planSetName,
  refreshKey = 0,
  onOpenSheet,
}: Props) {
  const [dashboard, setDashboard] = useState<PlanSetEstimatingDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(async () => {
    if (!planSetId) {
      setDashboard(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await fetchPlanSetEstimatingDashboard(planSetId);
      setDashboard(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load estimating dashboard.");
      setDashboard(null);
    } finally {
      setLoading(false);
    }
  }, [planSetId]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard, refreshKey]);

  const summaryCards = useMemo(() => {
    if (!dashboard) return [];
    const totalSheets = dashboard.coverage.total_sheet_count;
    return [
      {
        label: "Takeoff rows",
        value: dashboard.summary.total_items,
        detail: `${dashboard.summary.pending_items} pending review`,
      },
      {
        label: "Calibrated sheets",
        value: `${dashboard.coverage.calibrated_sheet_count}/${totalSheets}`,
        detail: `${dashboard.coverage.parsed_sheet_count}/${totalSheets} parsed`,
      },
      {
        label: "Analyzed sheets",
        value: `${dashboard.coverage.analyzed_sheet_count}/${totalSheets}`,
        detail: `${dashboard.coverage.pending_suggestion_count} pending suggestions`,
      },
      {
        label: "Covered sheets",
        value: `${dashboard.coverage.sheets_with_takeoff_count}/${totalSheets}`,
        detail: `${dashboard.coverage.unassigned_takeoff_items} unassigned rows`,
      },
    ];
  }, [dashboard]);

  return (
    <Card className="min-w-0">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Estimating Dashboard</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Cross-sheet estimating view for {planSetName || dashboard?.plan_set_name || "the selected plan set"}.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => void loadDashboard()} disabled={loading || !planSetId}>
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-6">
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {loading && !dashboard ? (
          <p className="text-sm text-muted-foreground">Loading estimator dashboard...</p>
        ) : null}
        {!loading && !dashboard ? (
          <p className="text-sm text-muted-foreground">Select a plan set to review estimating coverage.</p>
        ) : null}
        {dashboard ? (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {summaryCards.map((card) => (
                <div key={card.label} className="rounded-lg border border-border bg-muted/40 p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {card.label}
                  </div>
                  <div className="mt-2 text-2xl font-semibold text-foreground">{card.value}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{card.detail}</div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-border p-4">
                <h4 className="text-sm font-semibold text-foreground">Plan Set Status</h4>
                <dl className="mt-3 space-y-2 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-muted-foreground">Status</dt>
                    <dd className="font-medium text-foreground">{formatTokenLabel(dashboard.plan_set_status)}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-muted-foreground">Version</dt>
                    <dd className="font-medium text-foreground">{dashboard.version_label || "Not set"}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-muted-foreground">Latest snapshot</dt>
                    <dd className="text-right font-medium text-foreground">
                      {dashboard.latest_snapshot
                        ? `${dashboard.latest_snapshot.name} · ${formatTokenLabel(dashboard.latest_snapshot.status)}`
                        : "None yet"}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-muted-foreground">Latest export</dt>
                    <dd className="text-right font-medium text-foreground">
                      {dashboard.latest_export
                        ? `${formatTokenLabel(dashboard.latest_export.export_type)} · ${formatTokenLabel(dashboard.latest_export.status)}`
                        : "None yet"}
                    </dd>
                  </div>
                </dl>
              </div>
              <div className="rounded-lg border border-border p-4">
                <h4 className="text-sm font-semibold text-foreground">Unassigned Takeoff</h4>
                <p className="mt-2 text-sm text-muted-foreground">
                  Plan-set-level rows not attached to a specific sheet.
                </p>
                <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-md bg-muted/50 p-3">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">Rows</div>
                    <div className="mt-1 text-xl font-semibold text-foreground">
                      {dashboard.unassigned_summary.total_items}
                    </div>
                  </div>
                  <div className="rounded-md bg-muted/50 p-3">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">Pending</div>
                    <div className="mt-1 text-xl font-semibold text-foreground">
                      {dashboard.unassigned_summary.pending_items}
                    </div>
                  </div>
                </dl>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-foreground">Discipline Rollups</h4>
                <span className="text-xs text-muted-foreground">
                  Sorted by takeoff activity
                </span>
              </div>
              {dashboard.discipline_rollups.length === 0 ? (
                <p className="text-sm text-muted-foreground">No discipline activity yet.</p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="min-w-full text-sm">
                    <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2">Discipline</th>
                        <th className="px-3 py-2">Sheets</th>
                        <th className="px-3 py-2">Calibrated</th>
                        <th className="px-3 py-2">Analyzed</th>
                        <th className="px-3 py-2">Rows</th>
                        <th className="px-3 py-2">Pending</th>
                        <th className="px-3 py-2">Suggestions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.discipline_rollups.map((row) => (
                        <tr key={row.discipline} className="border-t border-border">
                          <td className="px-3 py-2 font-medium text-foreground">{row.discipline}</td>
                          <td className="px-3 py-2 text-muted-foreground">{row.sheet_count}</td>
                          <td className="px-3 py-2 text-muted-foreground">
                            {row.calibrated_sheet_count}/{row.sheet_count}
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">
                            {row.analyzed_sheet_count}/{row.sheet_count}
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">{row.takeoff_total_items}</td>
                          <td className="px-3 py-2 text-muted-foreground">{row.pending_items}</td>
                          <td className="px-3 py-2 text-muted-foreground">{row.pending_suggestions}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-foreground">Sheet Worklist</h4>
                <span className="text-xs text-muted-foreground">
                  Sorted by pending review first
                </span>
              </div>
              {dashboard.sheet_rollups.length === 0 ? (
                <p className="text-sm text-muted-foreground">No sheets in this plan set yet.</p>
              ) : (
                <div className="space-y-3">
                  {dashboard.sheet_rollups.map((row) => (
                    <div
                      key={row.id}
                      className="rounded-lg border border-border bg-muted/20 p-4"
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-base font-semibold text-foreground">
                              {formatSheetLabel(row)}
                            </span>
                            <span className="rounded-full bg-background px-2 py-1 text-xs text-muted-foreground">
                              {formatTokenLabel(row.file_type)}
                            </span>
                            <span className="rounded-full bg-background px-2 py-1 text-xs text-muted-foreground">
                              {formatTokenLabel(row.parse_status)}
                            </span>
                            <span className="rounded-full bg-background px-2 py-1 text-xs text-muted-foreground">
                              {row.calibrated ? "Calibrated" : "Needs calibration"}
                            </span>
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {row.discipline || "No discipline"} · {row.total_items} takeoff rows · {row.pending_items} pending review · {row.pending_suggestions} pending suggestions
                          </p>
                          {row.top_categories.length ? (
                            <div className="flex flex-wrap gap-2">
                              {row.top_categories.map((category) => (
                                <span
                                  key={`${row.id}-${category.category}-${category.unit}`}
                                  className="rounded-full border border-border bg-background px-2 py-1 text-xs text-muted-foreground"
                                >
                                  {formatTokenLabel(category.category)} {category.quantity_total} {formatTokenLabel(category.unit).toLowerCase()}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <p className="text-xs text-muted-foreground">No takeoff categories recorded yet.</p>
                          )}
                        </div>
                        <div className="flex min-w-[220px] flex-col items-start gap-2 lg:items-end">
                          <p className="text-xs text-muted-foreground">
                            Latest analysis:{" "}
                            <span className="font-medium text-foreground">
                              {row.latest_analysis_status
                                ? `${formatTokenLabel(row.latest_analysis_status)} · ${formatTimestamp(row.latest_analysis_at)}`
                                : "Not run yet"}
                            </span>
                          </p>
                          <Button type="button" size="sm" onClick={() => onOpenSheet(row.id)}>
                            Open sheet
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
