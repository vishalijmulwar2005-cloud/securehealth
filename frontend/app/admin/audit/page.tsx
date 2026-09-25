"use client";
/** Audit trail (adopted from the verified console's Audit.jsx): who did what,
 * when, with the outcome and the ledger block that proves it. */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell";
import { api } from "@/lib/api";
import { Badge, Card, ErrorState, Loading, PageHead, Select, Table } from "@/components/ui";

interface AuditRow {
  id: number; actor_id: number | null; role: string | null; event_type: string;
  target_type: string | null; target_id: number | null; outcome: string;
  created_at: string; block_ref: string | null;
}

export default function AuditPage() {
  return (
    <AppShell requireRole={["SYSTEM_ADMIN", "HOSPITAL_ADMIN"]}>
      <AuditTrail />
    </AppShell>
  );
}

function AuditTrail() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [action, setAction] = useState("");
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const qs = new URLSearchParams();
      if (action) qs.set("action", action);
      if (outcome) qs.set("outcome", outcome);
      setRows(await api.get<AuditRow[]>(`/admin/audit?${qs.toString()}`));
    } catch {
      setError("Could not load the audit trail.");
    }
  }, [action, outcome]);
  useEffect(() => { load(); }, [load]);

  const actions = Array.from(new Set((rows ?? []).map((r) => r.event_type)));

  return (
    <div className="space-y-6">
      <PageHead kicker="Traceability" title="Audit trail"
        sub="Who did what, and when. Entries that changed data point to the ledger block that proves it." />

      {error && <ErrorState message={error} onRetry={load} />}

      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <label className="text-sm font-medium text-ink-soft">Filter by action
            <Select className="mt-1 w-52" value={action}
              onChange={(e) => setAction(e.target.value)}>
              <option value="">All actions</option>
              {actions.map((a) => <option key={a} value={a}>{a}</option>)}
            </Select>
          </label>
          <label className="text-sm font-medium text-ink-soft">Filter by outcome
            <Select className="mt-1 w-40" value={outcome}
              onChange={(e) => setOutcome(e.target.value)}>
              <option value="">All outcomes</option>
              <option value="SUCCESS">Success</option>
              <option value="DENIED">Denied</option>
              <option value="FAILED">Failed</option>
            </Select>
          </label>
        </div>

        {!rows ? <Loading /> : (
          <Table
            columns={["Time", "Who", "Role", "Action", "Target", "Outcome", "Block"]}
            rows={rows.map((a) => [
              a.created_at.slice(0, 19).replace("T", " "),
              a.actor_id ? `#${a.actor_id}` : "System",
              a.role ?? "—",
              <span key="a" className="font-medium text-ink">{a.event_type}</span>,
              a.target_type ? `${a.target_type}${a.target_id ? ` #${a.target_id}` : ""}` : "—",
              a.outcome === "SUCCESS" ? <Badge key="o" tone="teal" glyph="done">success</Badge>
                : <Badge key="o2" tone="alarm" glyph="failed">{a.outcome.toLowerCase()}</Badge>,
              a.block_ref ? <Badge key="b" tone="ink">#{a.block_ref}</Badge>
                : <Badge key="b2" tone="plain" glyph="progress">—</Badge>,
            ])}
          />
        )}
      </Card>
    </div>
  );
}
