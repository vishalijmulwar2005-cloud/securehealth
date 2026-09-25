"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AccessEvent } from "@/lib/types";
import { Card, EmptyState, ErrorState, Loading, StatusBadge } from "@/components/ui";

export default function AccessHistoryPage() {
  const [events, setEvents] = useState<AccessEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setEvents(await api.get<AccessEvent[]>("/access-history")); }
    catch { setError("Could not load your access history."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Access history</h1>
        <p className="text-sm text-ink-soft">
          Who, what, when and the outcome — denials are audited just like successful access.
        </p>
      </header>
      {error && <ErrorState message={error} onRetry={load} />}
      {!events ? <Loading /> : events.length === 0 ? (
        <EmptyState what="No recorded access events yet." />
      ) : (
        <Card title={`${events.length} events`}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-[11px] uppercase tracking-wide text-ink-faint">
                  <th className="py-2 pr-4">When</th>
                  <th className="py-2 pr-4">Action</th>
                  <th className="py-2 pr-4">Resource</th>
                  <th className="py-2 pr-4">Outcome</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {events.map((a) => (
                  <tr key={a.id}>
                    <td className="py-2 pr-4 text-ink-soft">{a.created_at.slice(0, 16).replace("T", " ")}</td>
                    <td className="py-2 pr-4 font-medium text-ink">{a.action}</td>
                    <td className="py-2 pr-4 text-ink-soft">
                      {a.resource_type ?? "—"}{a.resource_id ? ` #${a.resource_id}` : ""}
                    </td>
                    <td className="py-2 pr-4"><StatusBadge status={a.outcome === "GRANTED" ? "ACTIVE" : "REJECTED"} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
