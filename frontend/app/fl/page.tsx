"use client";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell";
import { ApiError, api } from "@/lib/api";
import { AreaChart, LineChart } from "@/components/charts";
import {
  Badge, Banner, Button, Card, EmptyState, ErrorState, HashChip, Loading, PageHead,
  SectionHead, Select, Slider, Stat, Table,
} from "@/components/ui";

interface Disease { key: string; name: string; features: string[] }
interface Summary {
  disease: string; name: string; version: number; fingerprint: string | null;
  cumulative_epsilon: number; served_matches_ledger: boolean;
}
interface Participant {
  hospital: string; samples: number; localAccuracy: number; localLoss: number;
  updateNorm: number; clipped: boolean; updateHash: string;
}
interface Job {
  id: number; disease: string; round: number;
  metrics: { accuracy: number; f1: number; totalSamples: number; durationMs: number } | null;
  participants: Participant[] | null; epsilon: number; cumulative_epsilon: number;
  model_hash: string; block_index: number | null; status: string; created_at: string;
}

function epsilonFor(sigma: number): number {
  if (!sigma || sigma <= 0) return 0;
  return Math.sqrt(2 * Math.log(1.25 / 1e-5)) / sigma;
}

export default function FederatedLearningPage() {
  return (
    <AppShell requireRole={["SYSTEM_ADMIN", "HOSPITAL_ADMIN"]}>
      <FLConsole />
    </AppShell>
  );
}

function FLConsole() {
  const [diseases, setDiseases] = useState<Disease[] | null>(null);
  const [summary, setSummary] = useState<Summary[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [active, setActive] = useState("heart");
  const [epochs, setEpochs] = useState(3);
  const [lr, setLr] = useState(0.1);
  const [dp, setDp] = useState(true);
  const [noise, setNoise] = useState(1.0);
  const [clip, setClip] = useState(0.5);
  const [rounds, setRounds] = useState(1);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [d, s, j] = await Promise.all([
        api.get<Disease[]>("/federated/diseases"),
        api.get<Summary[]>("/federated/summary"),
        api.get<Job[]>("/federated/jobs?limit=50"),
      ]);
      setDiseases(d); setSummary(s); setJobs(j);
    } catch {
      setError("Could not load federated-learning state.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function runRounds() {
    setRunning(true); setError(null); setOk(null);
    try {
      const r = await api.post<{ rounds_run: number }>("/federated/run", {
        disease: active, epochs, learning_rate: lr, dp_enabled: dp,
        noise_multiplier: noise, clip_norm: clip, rounds,
      });
      setOk(`${r.rounds_run} round(s) completed — AGGREGATION blocks mined.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Training failed; try again.");
    } finally {
      setRunning(false);
    }
  }

  async function resetModel() {
    setError(null); setOk(null);
    try {
      await api.post("/federated/reset", { disease: active });
      setOk(`${active} model reset to version 0 — ε cleared, RESET block mined.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed.");
    }
  }

  if (!diseases || !summary || !jobs) return <Loading />;
  const current = summary.find((s) => s.disease === active);
  const diseaseJobs = jobs.filter((j) => j.disease === active && j.status === "COMPLETED")
    .sort((a, b) => a.round - b.round);
  const latest = diseaseJobs[diseaseJobs.length - 1];
  const accSeries = [{
    key: active, label: "Accuracy %", color: "#0e7c7b",
    data: diseaseJobs.map((j) => ({ x: `R${j.round}`, y: (j.metrics?.accuracy ?? 0) * 100 })),
  }];
  const epsSeries = diseaseJobs.map((j) => ({ x: `R${j.round}`, y: j.cumulative_epsilon }));

  return (
    <div className="space-y-6">
      <PageHead kicker="Federated training" title={`Train the ${diseases.find((d) => d.key === active)?.name ?? active} model`}
        sub="Each hospital trains locally on consenting patients only, privatises its update, and the aggregator averages with FedAvg. Records moved between hospitals: 0." />

      <div className="space-y-2">
        {ok && <Banner kind="ok">{ok}</Banner>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      <Card>
        <div className="mb-4 flex flex-wrap gap-2">
          {diseases.map((d) => (
            <button key={d.key} onClick={() => setActive(d.key)}
              className={`rounded-md border px-3 py-1.5 text-sm font-semibold transition ${
                active === d.key ? "border-teal/40 bg-teal-wash text-teal-deep" : "border-line bg-white text-ink-soft hover:text-ink"}`}>
              {d.name}
            </button>
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4">
            <SectionHead title="Round settings" />
            <Slider label="Local epochs" min={1} max={10} step={1} value={epochs} onChange={setEpochs} />
            <Slider label="Learning rate" min={0.01} max={0.5} step={0.01} value={lr} onChange={setLr} />
            <label className="flex items-center gap-2 text-sm font-medium text-ink-soft">
              <input type="checkbox" checked={dp} onChange={(e) => setDp(e.target.checked)}
                className="h-4 w-4 rounded border-line text-teal" />
              Differential privacy
            </label>
            <Slider label="Noise multiplier (σ)" min={0.1} max={3} step={0.1} value={noise} onChange={setNoise} disabled={!dp} />
            <Slider label="Clipping norm (C)" min={0.1} max={2} step={0.1} value={clip} onChange={setClip} disabled={!dp} />
            <Slider label="Rounds to run" min={1} max={20} step={1} value={rounds} onChange={setRounds} />
            <p className="text-xs text-ink-faint">
              Privacy cost per round: ε ≈ <span className="font-semibold text-ink">{epsilonFor(dp ? noise : 0).toFixed(2)}</span> (δ = 10⁻⁵).
              More noise means stronger privacy, but a less accurate model.
            </p>
            <div className="flex gap-2">
              <Button tone="solid" onClick={runRounds} disabled={running}>
                {running ? "Training locally · aggregating…" : `Run ${rounds} round${rounds > 1 ? "s" : ""}`}
              </Button>
              <Button tone="alarm" onClick={resetModel}>Reset model</Button>
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="grid gap-4 sm:grid-cols-4">
              <Stat label="Version" value={current?.version ?? 0} />
              <Stat label="Accuracy" value={latest?.metrics ? `${(latest.metrics.accuracy * 100).toFixed(1)}%` : "–"} />
              <Stat label="F1 score" value={latest?.metrics ? `${(latest.metrics.f1 * 100).toFixed(1)}%` : "–"} />
              <Stat label="ε spent" value={current?.cumulative_epsilon ?? 0} />
            </div>
            <p className="mt-3 text-xs text-ink-faint">Model fingerprint</p>
            <p className="mt-1"><HashChip hash={current?.fingerprint ?? ""} label="Model fingerprint" /></p>
            <p className="mt-2 flex items-center gap-2 text-xs">
              Ledger-verified:
              {current?.fingerprint ? (current.served_matches_ledger
                ? <Badge tone="teal" glyph="done">matches AGGREGATION block</Badge>
                : <Badge tone="amber" glyph="progress">pending</Badge>) : "—"}
            </p>
          </div>
        </div>
      </Card>

      {diseaseJobs.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <SectionHead title="Accuracy per round" sub="Evaluated on the pooled consenting set." />
            <LineChart series={accSeries} />
          </Card>
          <Card>
            <SectionHead title="Privacy budget spent" sub="Cumulative ε — lower is more private." />
            <AreaChart data={epsSeries} />
          </Card>
        </div>
      )}

      <Card>
        <SectionHead title={`Round ${latest?.round ?? "—"}: what each hospital sent`}
          sub="Only these weight updates left each hospital. Fingerprints are on the ledger so any hospital can prove what it contributed." />
        {!latest?.participants ? (
          <EmptyState title="No rounds yet" hint="Run a round to see per-hospital updates." />
        ) : (
          <Table
            columns={["Hospital", "Patients used", "Local accuracy", "Update norm", "Clipped", "Update fingerprint"]}
            rows={latest.participants.map((p) => [
              <span key="h" className="font-semibold text-ink">{p.hospital}</span>,
              p.samples,
              `${(p.localAccuracy * 100).toFixed(1)}%`,
              p.updateNorm.toFixed(3),
              p.clipped ? <Badge key="c" tone="amber">Yes</Badge> : <Badge key="c2" tone="plain">No</Badge>,
              <HashChip key="f" hash={p.updateHash} label="Update fingerprint" />,
            ])}
          />
        )}
      </Card>

      <Card>
        <SectionHead title="Round history" sub="Every round references its AGGREGATION ledger block." />
        {diseaseJobs.length === 0 ? (
          <EmptyState title="No rounds trained for this disease yet." />
        ) : (
          <Table
            columns={["Round", "Accuracy", "F1", "ε", "Cumulative ε", "Samples", "Ledger block"]}
            rows={diseaseJobs.map((j) => [
              `R${j.round}`,
              j.metrics ? `${(j.metrics.accuracy * 100).toFixed(1)}%` : "–",
              j.metrics ? `${(j.metrics.f1 * 100).toFixed(1)}%` : "–",
              j.epsilon,
              j.cumulative_epsilon,
              j.metrics?.totalSamples ?? 0,
              j.block_index != null ? <Badge key="b" tone="ink">#{j.block_index}</Badge>
                : <Badge key="b2" tone="plain" glyph="progress">queued</Badge>,
            ])}
          />
        )}
      </Card>
    </div>
  );
}
