"use client";
/** Consortium overview (adopted from the verified console's Overview.jsx):
 * network stats, accuracy chart, disease models, recent activity. */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell";
import { ApiError, api } from "@/lib/api";
import type { AdminUser } from "@/lib/types";
import {
  Badge, Banner, Button, Card, ErrorState, Input, Loading, PageHead,
  SectionHead, Stat, StatusBadge, Table,
} from "@/components/ui";
import { LineChart } from "@/components/charts";

interface Summary {
  disease: string; name: string; version: number; fingerprint: string | null;
  cumulative_epsilon: number; served_matches_ledger: boolean; artifact_versions: number;
}
interface Job {
  id: number; disease: string; round: number;
  metrics: { accuracy: number; f1: number; totalSamples: number } | null;
  epsilon: number; cumulative_epsilon: number; model_hash: string;
  block_index: number | null; status: string; created_at: string;
}
interface Network {
  id: number; code: string; name: string; active: boolean;
  patients: number; consented: number;
}
interface LedgerInfo { total: number; types: Record<string, number> }
interface AuditRow { id: number; event_type: string; target_type: string | null; outcome: string; created_at: string; block_ref: string | null }

export default function AdminOverviewPage() {
  return (
    <AppShell requireRole={["SYSTEM_ADMIN", "HOSPITAL_ADMIN"]}>
      <Overview />
    </AppShell>
  );
}

function Overview() {
  const [summary, setSummary] = useState<Summary[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [network, setNetwork] = useState<Network[] | null>(null);
  const [ledger, setLedger] = useState<LedgerInfo | null>(null);
  const [audit, setAudit] = useState<AuditRow[] | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [rel, setRel] = useState({ patient_id: "", doctor_id: "" });

  const load = useCallback(async () => {
    try {
      const [s, j, n, l, a, u] = await Promise.all([
        api.get<Summary[]>("/federated/summary"),
        api.get<Job[]>("/federated/jobs"),
        api.get<Network[]>("/federated/hospitals"),
        api.get<LedgerInfo>("/ledger/blocks"),
        api.get<AuditRow[]>("/admin/audit"),
        api.get<AdminUser[]>("/admin/users"),
      ]);
      setSummary(s); setJobs(j); setNetwork(n); setLedger(l); setAudit(a); setUsers(u);
    } catch {
      setError("Could not load consortium state.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function bindRelationship(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setOk(null);
    try {
      await api.post("/admin/care-relationships", {
        patient_id: Number(rel.patient_id), doctor_id: Number(rel.doctor_id),
      });
      setOk("Care relationship bound — the doctor can now pass the relationship check.");
      setRel({ patient_id: "", doctor_id: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Binding failed.");
    }
  }

  async function setStatus(userId: number, status: string) {
    setError(null); setOk(null);
    try {
      await api.patch(`/admin/users/${userId}/status`, { status });
      setOk(`User #${userId} is now ${status}.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Status change failed.");
    }
  }

  if (error && !summary) return <ErrorState message={error} onRetry={load} />;
  if (!summary || !jobs || !network || !ledger || !audit || !users) return <Loading />;

  const rounds = jobs.length;
  const totalSamples = jobs.reduce((s, j) => s + (j.metrics?.totalSamples ?? 0), 0);
  const totalPatients = network.reduce((s, h) => s + h.patients, 0);
  const consenting = network.reduce((s, h) => s + Math.round((h.patients * h.consented) / 100), 0);
  const activeHospitals = network.filter((h) => h.active).length;
  const eps = summary.reduce((s, m) => s + m.cumulative_epsilon, 0);
  const trained = summary.filter((m) => m.version > 0);
  const avgAcc = trained.length
    ? trained.reduce((s, m) => {
        const j = jobs.find((x) => x.disease === m.disease);
        return s + (j?.metrics?.accuracy ?? 0) * 100;
      }, 0) / trained.length : 0;

  const chartSeries = trained.length ? trained.map((m) => ({
    key: m.disease, label: m.name,
    color: m.disease === "heart" ? "#e63946" : m.disease === "diabetes" ? "#2B59C3"
      : m.disease === "stroke" ? "#8E44AD" : "#B7791F",
    data: jobs.filter((j) => j.disease === m.disease)
      .sort((a, b) => a.round - b.round)
      .map((j) => ({ x: `R${j.round}`, y: (j.metrics?.accuracy ?? 0) * 100 })),
  })) : [];

  return (
    <div className="space-y-6">
      <PageHead kicker="Consortium overview" title="Live state of the network"
        sub="The shared model, the privacy spent training it, and the ledger that records every step." />

      <div className="space-y-2">
        {ok && <Banner kind="ok">{ok}</Banner>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      <div className="grid gap-6 sm:grid-cols-3 lg:grid-cols-6 rise">
        <div className="col-span-2 rounded-lg border border-teal/30 bg-teal-wash p-4">
          <div className="flex items-center gap-2 text-sm text-teal-deep">
            <span className="live-dot h-2 w-2 rounded-full bg-teal" />
            <strong className="tnum text-[27px] font-bold leading-none">0</strong>
          </div>
          <p className="mt-1 text-xs text-teal-deep/80">patient records moved between hospitals for training</p>
        </div>
        <Stat label="Hospitals training" value={`${activeHospitals} / ${network.length}`} />
        <Stat label="Consenting patients" value={consenting} note={`of ${totalPatients} total`} />
        <Stat label="Rounds trained" value={rounds} note={`${totalSamples} samples used`} />
        <Stat label="Privacy spent (ε)" value={eps.toFixed(1)} note="lower is more private" />
        <Stat label="Ledger blocks" value={ledger.total} note="all hashes verified" />
        <Stat label="Avg accuracy" value={`${avgAcc.toFixed(1)}%`} note={`${trained.length} of 4 models trained`} />
      </div>

      <Card>
        <SectionHead title="Accuracy by round, per disease" sub="Federated rounds — each hospital trains locally; only updates are aggregated." />
        {chartSeries.length > 0 ? (
          <LineChart series={chartSeries} />
        ) : (
          <p className="text-sm text-ink-soft">No rounds trained yet — open Federated Training to run the first round.</p>
        )}
      </Card>

      <Card>
        <SectionHead title="Disease models" />
        <Table
          columns={["Disease", "Version", "Accuracy", "F1 score", "Privacy spent (ε)", "Ledger-verified"]}
          rows={summary.map((m) => {
            const j = jobs.find((x) => x.disease === m.disease && x.round === m.version);
            return [
              <span key="d" className="font-semibold text-ink">{m.name}</span>,
              m.version || <span className="text-ink-faint">not trained</span>,
              j?.metrics ? `${(j.metrics.accuracy * 100).toFixed(1)}%` : "–",
              j?.metrics ? `${(j.metrics.f1 * 100).toFixed(1)}%` : "–",
              m.cumulative_epsilon,
              m.fingerprint ? (m.served_matches_ledger
                ? <Badge tone="teal" glyph="done">verified</Badge>
                : <Badge tone="amber" glyph="progress">pending</Badge>) : "—",
            ];
          })}
        />
      </Card>

      <Card>
        <SectionHead title="Recent activity" sub="Who did what, and when — entries point to their ledger blocks." />
        <Table
          columns={["Time", "Event", "Target", "Outcome", "Block"]}
          rows={audit.slice(0, 8).map((a) => [
            a.created_at.slice(0, 19).replace("T", " "),
            <span key="e" className="font-medium text-ink">{a.event_type}</span>,
            a.target_type ?? "—",
            a.outcome === "SUCCESS" ? <Badge key="o" tone="teal" glyph="done">success</Badge>
              : <Badge key="o" tone="alarm" glyph="failed">{a.outcome.toLowerCase()}</Badge>,
            a.block_ref ? `#${a.block_ref}` : <Badge key="b" tone="plain" glyph="progress">queued</Badge>,
          ])}
        />
      </Card>

      <p className="text-xs text-ink-faint">{users.length} accounts on this platform · all data synthetic</p>

      <Card>
        <SectionHead title="Bind care relationship (institutional)"
          sub="A doctor role alone never grants access - permission AND an active care relationship are both checked." />
        <form onSubmit={bindRelationship} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm font-medium text-ink-soft">Patient ID
            <Input className="mt-1" required type="number" min={1} value={rel.patient_id}
              onChange={(e) => setRel({ ...rel, patient_id: e.target.value })} />
          </label>
          <label className="flex-1 text-sm font-medium text-ink-soft">Doctor ID
            <Input className="mt-1" required type="number" min={1} value={rel.doctor_id}
              onChange={(e) => setRel({ ...rel, doctor_id: e.target.value })} />
          </label>
          <Button type="submit" tone="solid">Bind</Button>
        </form>
      </Card>

      <Card>
        <SectionHead title="User lifecycle"
          sub="Suspend or reactivate accounts. Self status change is blocked; actions are audited." />
        <Table
          columns={["ID", "Name", "Email", "Role", "Status", "Lifecycle"]}
          rows={users.filter((u) => u.role !== "SYSTEM_ADMIN").map((u) => [
            String(u.id),
            <span key="n" className="font-medium text-ink">{u.full_name}</span>,
            u.email,
            u.role,
            <StatusBadge key="s" status={u.status} />,
            <select key="c" aria-label={`Lifecycle for ${u.email}`} value={u.status}
              onChange={(e) => setStatus(u.id, e.target.value)}
              className="rounded-md border border-line bg-white px-2 py-1 text-sm">
              {["ACTIVE", "SUSPENDED", "DISABLED"].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>,
          ])}
        />
      </Card>
    </div>
  );
}
