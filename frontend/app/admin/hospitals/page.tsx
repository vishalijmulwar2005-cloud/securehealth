"use client";
/** Hospitals in the consortium (adopted from the verified console's
 * Hospitals.jsx): per-node aggregate stats + pause/resume + non-IID chart. */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell";
import { ApiError, api } from "@/lib/api";
import { GroupedBars, LineChart } from "@/components/charts";
import {
  Badge, Button, Card, ErrorState, HashChip, Loading, PageHead, SectionHead, Table,
} from "@/components/ui";

interface Hospital {
  id: number; code: string; name: string; city: string; type: string; active: boolean;
  node_address: string | null; patients: number; consented: number; avg_age: number;
  conditions: Record<string, number>;
}

const DISEASE_COLORS: Record<string, string> = {
  heart: "#e63946", diabetes: "#2B59C3", stroke: "#8E44AD", kidney: "#B7791F",
};

export default function HospitalsPage() {
  return (
    <AppShell requireRole={["SYSTEM_ADMIN", "HOSPITAL_ADMIN"]}>
      <Hospitals />
    </AppShell>
  );
}

function Hospitals() {
  const [rows, setRows] = useState<Hospital[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setRows(await api.get<Hospital[]>("/federated/hospitals")); }
    catch { setError("Could not load the consortium."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function toggleNode(h: Hospital) {
    setError(null); setOk(null);
    try {
      await api.patch(`/admin/hospitals/${h.id}/status`, { active: !h.active });
      setOk(`${h.code} ${h.active ? "paused — excluded from the next training round" : "resumed — included in the next training round"}.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Node update failed.");
    }
  }

  if (error && !rows) return <ErrorState message={error} onRetry={load} />;
  if (!rows) return <Loading />;

  const groups = rows.map((r) => r.code);
  const condSeries = Object.keys(DISEASE_COLORS).map((k) => ({
    key: k, label: k,
    color: DISEASE_COLORS[k],
    data: rows.map((r) => r.conditions?.[k] ?? 0),
  }));

  return (
    <div className="space-y-6">
      <PageHead kicker="Consortium nodes" title="Hospitals in the consortium"
        sub="Each hospital is a node with its own patient database. The numbers below are computed locally; only these summaries are shown here, never individual records." />

      <div className="space-y-2">
        {ok && <p className="rounded-lg border border-teal/30 bg-teal-wash px-3 py-2 text-sm text-teal-deep">✓ {ok}</p>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      {rows.map((h) => (
        <Card key={h.id}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-ink">{h.name}</h2>
              <p className="text-xs text-ink-faint">{h.type}, {h.city}</p>
            </div>
            <div className="flex items-center gap-2">
              {h.active ? <Badge tone="teal" glyph="done">Training</Badge>
                : <Badge tone="amber" glyph="progress">Paused</Badge>}
              <Button tone={h.active ? "amber" : "teal"} onClick={() => toggleNode(h)}>
                {h.active ? "Pause this node" : "Resume this node"}
              </Button>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-4">
            <div><p className="text-sm text-ink-soft">Patients</p><p className="text-[22px] font-bold tnum text-ink">{h.patients}</p></div>
            <div><p className="text-sm text-ink-soft">Consented</p><p className="text-[22px] font-bold tnum text-ink">{h.consented}%</p></div>
            <div><p className="text-sm text-ink-soft">Average age</p><p className="text-[22px] font-bold tnum text-ink">{h.avg_age}</p></div>
            <div><p className="text-sm text-ink-soft">Node address</p>
              <p className="mt-1"><HashChip hash={h.node_address ?? ""} label="Node address" /></p></div>
          </div>
          <p className="mt-3 text-xs text-ink-faint">
            Patients with each condition — heart {h.conditions?.heart ?? 0}%, diabetes{" "}
            {h.conditions?.diabetes ?? 0}%, stroke {h.conditions?.stroke ?? 0}%, kidney{" "}
            {h.conditions?.kidney ?? 0}%
          </p>
        </Card>
      ))}

      <Card>
        <SectionHead title="Why the data can't just be pooled"
          sub="Hospitals serve different populations (non-IID data). A single-site model transfers poorly; federated learning learns from all four without moving any record." />
        {rows.length > 0 && (
          <GroupedBars
            groups={groups}
            series={condSeries}
          />
        )}
      </Card>
    </div>
  );
}
