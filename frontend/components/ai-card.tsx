"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { Banner, Button, Card, StatusBadge } from "./ui";

/** AI analysis card (PRD §14): explicit async states, persistent assistance
 * labeling, original-report context — never a diagnosis, never fake progress. */
interface Job {
  id: number; status: string; model_id: string | null; model_version: string | null;
  trace_id: string | null; failure_category: string | null; notice: string;
  result?: { summary: string; observations: string[]; metrics: Record<string, unknown>;
    model: { id: string; version: string; prompt_version: string };
    disclaimer: string } | null;
}

export function AiAnalysisCard({ reportId, onGone }: { reportId: number | null; onGone?: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback((id: number) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const j = await api.get<Job>(`/ai/analyses/${id}`);
        setJob(j);
        if (["COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"].includes(j.status)) stopPolling();
      } catch { stopPolling(); }
    }, 1200);
  }, [stopPolling]);

  async function request() {
    if (!reportId) return;
    setRequesting(true); setError(null);
    try {
      const j = await api.post<Job>(`/ai/analyze/${reportId}`);
      setJob(j);
      poll(j.id); // truthfully drive the async state machine from the server
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not request the analysis.");
    } finally {
      setRequesting(false);
    }
  }

  if (!reportId) return null;
  const terminal = job && ["COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"].includes(job.status);

  return (
    <Card title="AI-assisted analysis">
      <p className="mb-3 text-xs text-ink-faint">
        AI-generated information is for assistance and should be reviewed by a qualified
        healthcare professional — it is never a medical diagnosis. The original report
        always remains available regardless of the analysis outcome.
      </p>

      {!job && (
        <Button onClick={request} disabled={requesting}>
          {requesting ? "Submitting…" : "Request AI analysis"}
        </Button>
      )}

      {job && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <StatusBadge status={job.status} />
            {job.trace_id && <span className="font-mono text-[10px] text-ink-faint">trace {job.trace_id.slice(0, 12)}…</span>}
          </div>

          {["QUEUED", "PROCESSING"].includes(job.status) && (
            <p className="rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink-soft">
              {job.status === "QUEUED" ? "Analysis accepted and waiting to run…" : "Analysis executing — progress comes from the server, never simulated."}
            </p>
          )}

          {job.status === "FAILED" && (
            <Banner kind="error">
              Analysis failed ({job.failure_category ?? "unknown category"}). The original report
              remains available — you can request a new analysis.
            </Banner>
          )}

          {job.status === "COMPLETED" && job.result && (
            <div className="space-y-2">
              <p className="text-sm text-ink">{job.result.summary}</p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-ink-soft">
                {job.result.observations.map((o) => <li key={o}>{o}</li>)}
              </ul>
              <p className="text-[11px] text-ink-faint">
                Model {job.result.model.id} v{job.result.model.version} · confidence index{" "}
                {String(job.result.metrics.confidence_index)} · AI-assisted, not a diagnosis.
              </p>
            </div>
          )}

          {terminal && (
            <Button kind="secondary" onClick={() => { setJob(null); onGone?.(); }}>
              {job.status === "COMPLETED" ? "New analysis" : "Retry analysis"}
            </Button>
          )}
        </div>
      )}

      {error && <div className="mt-3"><Banner kind="error">{error}</Banner></div>}
    </Card>
  );
}
