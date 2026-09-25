"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { ConsentBundle, ResearchConsent } from "@/lib/types";
import {
  Banner, Button, Card, ConfirmButton, EmptyState, ErrorState, Loading, Select, StatusBadge,
} from "@/components/ui";

const DURATIONS = [7, 30, 90]; // canonical time windows (PRD §8 / TRD §9)

export default function PrivacyCenterPage() {
  const [bundle, setBundle] = useState<ConsentBundle | null>(null);
  const [research, setResearch] = useState<ResearchConsent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [duration, setDuration] = useState<Record<number, number>>({});
  const [researchBusy, setResearchBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [b, r] = await Promise.all([
        api.get<ConsentBundle>("/consents"),
        api.get<ResearchConsent[]>("/research-consents/me"),
      ]);
      setBundle(b); setResearch(r);
    } catch {
      setError("Could not load your privacy data.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function act(fn: () => Promise<unknown>, success: string) {
    setError(null); setOk(null);
    try {
      await fn();
      setOk(success); // only after server confirmation
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed; try again.");
    }
  }

  async function toggleResearch() {
    setResearchBusy(true);
    const optedIn = research?.some((r) => r.status === "ACTIVE");
    await act(
      () => api.post("/research-consents", optedIn
        ? { opt_in: false }
        : { opt_in: true, scope: "LOCAL_FL", duration_days: 90 }),
      optedIn ? "Research participation withdrawn." : "Research participation active for 90 days.",
    );
    setResearchBusy(false);
  }

  if (error && !bundle) return <ErrorState message={error} onRetry={load} />;
  if (!bundle || !research) return <Loading />;

  const pending = bundle.requests.filter((r) => r.status === "PENDING");
  const decided = bundle.requests.filter((r) => r.status !== "PENDING");
  const researchActive = research.some((r) => r.status === "ACTIVE");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Privacy Center</h1>
        <p className="text-sm text-ink-soft">
          You control who accesses what, and for how long. PENDING never grants access.
        </p>
      </header>

      <div className="space-y-2">
        {ok && <Banner kind="ok">{ok}</Banner>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      <Card title={`Access requests (${pending.length} pending)`}>
        {pending.length === 0 ? (
          <EmptyState what="No pending requests." next="Doctor requests for your records appear here." />
        ) : (
          <ul className="divide-y divide-line">
            {pending.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="text-sm">
                  <p className="font-medium text-ink">Request #{r.id} · doctor #{r.requester_id}</p>
                  <p className="text-xs text-ink-faint">
                    {r.resource_type}{r.resource_id ? ` #${r.resource_id}` : " (your records)"} · scope {r.scope}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Select className="w-32" value={duration[r.id] ?? 7}
                    onChange={(e) => setDuration({ ...duration, [r.id]: Number(e.target.value) })}
                    aria-label="Access duration">
                    {DURATIONS.map((d) => <option key={d} value={d}>{d} days</option>)}
                  </Select>
                  <Button onClick={() => act(
                    () => api.post(`/consents/requests/${r.id}/approve`,
                      { duration_days: duration[r.id] ?? 7 }),
                    "Permission granted for the selected window.")}>
                    Approve
                  </Button>
                  <Button kind="secondary" onClick={() => act(
                    () => api.post(`/consents/requests/${r.id}/reject`, {}),
                    "Request rejected.")}>
                    Reject
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Active & past permissions">
        {bundle.permissions.length === 0 ? (
          <EmptyState what="No permissions yet." />
        ) : (
          <ul className="divide-y divide-line">
            {bundle.permissions.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="text-sm">
                  <p className="font-medium text-ink">
                    Doctor #{p.recipient_user_id} · {p.resource_type}{p.resource_id ? ` #${p.resource_id}` : ""}
                  </p>
                  <p className="text-xs text-ink-faint">
                    scope {p.permission_type}
                    {p.expires_at ? ` · expires ${p.expires_at.slice(0, 10)}` : ""}
                    {p.revoked_at ? ` · revoked ${p.revoked_at.slice(0, 10)}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={p.status} />
                  {p.status === "ACTIVE" && (
                    <ConfirmButton label="Revoke" confirmLabel="Confirm revoke?"
                      consequence="Retrieval is blocked immediately; history remains visible."
                      onConfirm={() => act(() => api.post(`/permissions/${p.id}/revoke`, {}),
                        "Permission revoked; next protected request is denied.")} />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Research participation (federated learning)">
        <p className="text-sm text-ink-soft">
          Optional and separate from care permissions. With active research consent, your
          synthetic records may join <strong>local</strong> training only — raw records never
          leave the institution, and &ldquo;records moved between hospitals: 0&rdquo; stays true.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <StatusBadge status={researchActive ? "ACTIVE" : "REVOKED"} />
          <Button kind={researchActive ? "danger" : "primary"} disabled={researchBusy}
            onClick={toggleResearch}>
            {researchBusy ? "Updating…" : researchActive ? "Withdraw participation" : "Participate (90 days)"}
          </Button>
        </div>
      </Card>

      {decided.length > 0 && (
        <Card title="Request history">
          <ul className="divide-y divide-line">
            {decided.map((r) => (
              <li key={r.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-ink-soft">Request #{r.id} · doctor #{r.requester_id}</span>
                <StatusBadge status={r.status} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
