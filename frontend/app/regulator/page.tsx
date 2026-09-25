"use client";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell";
import { api } from "@/lib/api";
import { Card, EmptyState, ErrorState, Loading, StatusBadge } from "@/components/ui";

/** Regulator read-only verification console (AppFlow §24): integrity and
 * chronology only — no clinical content, no mutation, server-authoritative. */
interface Integrity {
  chain: { valid: boolean; broken_index: number; count: number };
  models: { disease: string; round: number; model_hash: string;
    cumulative_epsilon: number; block_index: number | null }[];
}
interface AuditRow { id: number; event_type: string; target_type: string | null;
  outcome: string; created_at: string; block_ref: string | null }

export default function RegulatorPage() {
  return (
    <AppShell requireRole={["REGULATOR", "SYSTEM_ADMIN"]}>
      <RegulatorConsole />
    </AppShell>
  );
}

function RegulatorConsole() {
  const [integrity, setIntegrity] = useState<Integrity | null>(null);
  const [audit, setAudit] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [i, a] = await Promise.all([
        api.get<Integrity>("/regulator/integrity"),
        api.get<AuditRow[]>("/regulator/audit"),
      ]);
      setIntegrity(i); setAudit(a);
    } catch {
      setError("Could not load verification data.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Regulator verification console</h1>
        <p className="text-sm text-ink-soft">
          Read-only verification of integrity and traceability. No clinical content is
          exposed and no mutation is permitted.
        </p>
      </header>

      {error && <ErrorState message={error} onRetry={load} />}
      {!integrity || !audit ? <Loading /> : (
        <>
          <Card title="Chain integrity">
            {integrity.chain.valid ? (
              <p className="text-sm text-teal-deep">
                ✓ All {integrity.chain.count} blocks verified — hashes and previous-hash links intact.
              </p>
            ) : (
              <p className="text-sm text-alarm">✕ Chain broken at block #{integrity.chain.broken_index}.</p>
            )}
          </Card>

          <Card title="Served-model integrity">
            {integrity.models.length === 0 ? (
              <EmptyState what="No trained models recorded yet." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-[11px] uppercase tracking-wide text-ink-faint">
                      <th className="py-2 pr-4">Disease</th><th className="py-2 pr-4">Round</th>
                      <th className="py-2 pr-4">Model fingerprint</th>
                      <th className="py-2 pr-4">Cumulative ε</th>
                      <th className="py-2 pr-4">Ledger block</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {integrity.models.map((m) => (
                      <tr key={m.disease}>
                        <td className="py-2 pr-4 font-medium text-ink">{m.disease}</td>
                        <td className="py-2 pr-4">{m.round}</td>
                        <td className="py-2 pr-4 font-mono text-[10px]">{m.model_hash.slice(0, 24)}…</td>
                        <td className="py-2 pr-4">{m.cumulative_epsilon}</td>
                        <td className="py-2 pr-4">#{m.block_index ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Audit chronology (verification data only)">
            {audit.length === 0 ? <EmptyState what="No audit events recorded." /> : (
              <ul className="divide-y divide-line">
                {audit.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                    <span className="text-ink-soft">{a.event_type}{a.target_type ? ` · ${a.target_type}` : ""}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-[11px] text-ink-faint">{a.created_at.slice(0, 19).replace("T", " ")}</span>
                      <StatusBadge status={a.outcome === "SUCCESS" ? "COMPLETED" : "REJECTED"} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
