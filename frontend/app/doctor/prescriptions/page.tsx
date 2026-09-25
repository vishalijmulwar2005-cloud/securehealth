"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { Prescription } from "@/lib/types";
import {
  Banner, Button, Card, EmptyState, ErrorState, Input, Loading, Textarea,
} from "@/components/ui";

export default function DoctorPrescriptionsPage() {
  const [items, setItems] = useState<Prescription[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ patient_id: "", medication: "", dosage: "", instructions: "" });

  const load = useCallback(async () => {
    try { setItems(await api.get<Prescription[]>("/prescriptions")); }
    catch { setError("Could not load prescriptions."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setOk(null);
    try {
      await api.post("/prescriptions", {
        patient_id: Number(form.patient_id),
        medication: form.medication,
        dosage: form.dosage || undefined,
        instructions: form.instructions || undefined,
      });
      setOk("Prescription saved and the patient was notified.");
      setForm({ patient_id: "", medication: "", dosage: "", instructions: "" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError
        ? err.message
        : "Could not create the prescription.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Prescriptions</h1>
        <p className="text-sm text-ink-soft">
          Requires an active care relationship with the patient. Demo prescriptions are
          synthetic and are not legally valid electronic prescriptions.
        </p>
      </header>

      <div className="space-y-2">
        {ok && <Banner kind="ok">{ok}</Banner>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      <Card title="New prescription">
        <form onSubmit={create} className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-medium text-ink-soft">Patient ID
            <Input className="mt-1" required type="number" min={1} value={form.patient_id}
              onChange={(e) => setForm({ ...form, patient_id: e.target.value })} />
          </label>
          <label className="text-sm font-medium text-ink-soft">Medication
            <Input className="mt-1" required maxLength={255} value={form.medication}
              onChange={(e) => setForm({ ...form, medication: e.target.value })} />
          </label>
          <label className="text-sm font-medium text-ink-soft">Dosage
            <Input className="mt-1" maxLength={128} value={form.dosage}
              onChange={(e) => setForm({ ...form, dosage: e.target.value })} placeholder="e.g. 500 mg" />
          </label>
          <label className="text-sm font-medium text-ink-soft sm:col-span-2">Instructions
            <Textarea className="mt-1" rows={2} maxLength={512} value={form.instructions}
              onChange={(e) => setForm({ ...form, instructions: e.target.value })} />
          </label>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create prescription"}</Button>
          </div>
        </form>
      </Card>

      {!items ? <Loading /> : items.length === 0 ? (
        <EmptyState what="No prescriptions yet." next="Created prescriptions appear here with patient context." />
      ) : (
        <Card title={`${items.length} prescriptions`}>
          <ul className="divide-y divide-line">
            {items.map((p) => (
              <li key={p.id} className="py-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-ink">
                    {p.medication}{p.dosage ? ` · ${p.dosage}` : ""}
                  </p>
                  <span className="text-xs text-ink-faint">{p.issued_at.slice(0, 16).replace("T", " ")}</span>
                </div>
                <p className="text-xs text-ink-faint">
                  Patient #{p.patient_id} · by doctor #{p.doctor_id}
                  {p.instructions ? ` · ${p.instructions}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
