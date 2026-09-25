"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { ConsentBundle, MedicalRecord } from "@/lib/types";
import {
  Banner, Button, Card, EmptyState, ErrorState, Input, Loading, Select, StatusBadge, Textarea,
} from "@/components/ui";

export default function DoctorDashboard() {
  const [bundle, setBundle] = useState<ConsentBundle | null>(null);
  const [records, setRecords] = useState<MedicalRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  // Access-request form
  const [patientId, setPatientId] = useState("");
  const [recordId, setRecordId] = useState("");
  const [scope, setScope] = useState("VIEW");
  const [purpose, setPurpose] = useState("");
  const [requesting, setRequesting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [b, r] = await Promise.all([
        api.get<ConsentBundle>("/consents"),
        api.get<MedicalRecord[]>("/records"),
      ]);
      setBundle(b); setRecords(r);
    } catch {
      setError("Could not load your workspace.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function requestAccess(e: React.FormEvent) {
    e.preventDefault();
    setRequesting(true); setError(null); setOk(null);
    try {
      await api.post("/consents/requests", {
        patient_id: Number(patientId),
        resource_type: recordId ? "RECORD" : "RECORD_CONTAINER",
        resource_id: recordId ? Number(recordId) : null,
        scope, purpose: purpose || undefined,
      });
      setOk("Request sent — PENDING until the patient decides.");
      setPatientId(""); setRecordId(""); setPurpose("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the request.");
    } finally {
      setRequesting(false);
    }
  }

  async function download(record: MedicalRecord, fileId: number) {
    setError(null);
    try { await api.download(`/records/${record.id}/download?file_id=${fileId}`); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Download failed."); }
  }

  const pending = bundle?.requests.filter((r) => r.status === "PENDING") ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Doctor workspace</h1>
        <p className="text-sm text-ink-soft">
          Explicit access only — a doctor role alone never grants record access.
        </p>
      </header>

      <div className="space-y-2">
        {ok && <Banner kind="ok">{ok}</Banner>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Request access to patient records">
          <form onSubmit={requestAccess} className="space-y-3">
            <label className="block text-sm font-medium text-ink-soft">Patient ID
              <Input className="mt-1" required type="number" min={1} value={patientId}
                onChange={(e) => setPatientId(e.target.value)} placeholder="e.g. 2" />
            </label>
            <label className="block text-sm font-medium text-ink-soft">Record ID (optional — leave blank for the record container)
              <Input className="mt-1" type="number" min={1} value={recordId}
                onChange={(e) => setRecordId(e.target.value)} placeholder="e.g. 1" />
            </label>
            <label className="block text-sm font-medium text-ink-soft">Scope
              <Select className="mt-1" value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="VIEW">View</option>
                <option value="VIEW_DOWNLOAD">View + download</option>
              </Select>
            </label>
            <label className="block text-sm font-medium text-ink-soft">Purpose
              <Textarea className="mt-1" rows={2} maxLength={512} value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="Clinical reason visible to the patient" />
            </label>
            <Button type="submit" disabled={requesting}>
              {requesting ? "Sending…" : "Send request"}
            </Button>
          </form>
        </Card>

        <Card title={`My requests (${pending.length} pending)`}>
          {!bundle ? <Loading /> : bundle.requests.length === 0 ? (
            <EmptyState what="No requests sent yet." next="Use the form to request authorized access." />
          ) : (
            <ul className="divide-y divide-line">
              {bundle.requests.map((r) => (
                <li key={r.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-ink-soft">
                    #{r.id} · patient #{r.patient_id} · {r.resource_type}
                    {r.resource_id ? ` #${r.resource_id}` : ""}
                  </span>
                  <StatusBadge status={r.status} />
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[11px] text-ink-faint">
            While a request is PENDING, no record access is possible.
          </p>
        </Card>
      </div>

      <Card title={`Authorized records (${records?.length ?? 0})`}>
        {!records ? <Loading /> : records.length === 0 ? (
          <EmptyState what="No authorized records."
            next="Records appear here only after the patient grants permission and your care relationship is active." />
        ) : (
          <ul className="divide-y divide-line">
            {records.map((r) => (
              <li key={r.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium text-ink">{r.title}</p>
                    <p className="text-xs text-ink-faint">
                      Record #{r.id} · {r.record_type} · patient #{r.patient_id}
                    </p>
                  </div>
                </div>
                {r.files.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {r.files.map((f) => (
                      <li key={f.id} className="flex items-center justify-between rounded-lg border border-line bg-paper px-3 py-1.5 text-xs">
                        <span className="text-ink-soft">
                          File #{f.id} · {f.mime_type} · {(f.size / 1024).toFixed(1)} KB
                        </span>
                        <Button kind="ghost" onClick={() => download(r, f.id)}>Download</Button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
