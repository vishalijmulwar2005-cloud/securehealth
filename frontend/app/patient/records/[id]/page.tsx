"use client";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { MedicalRecord } from "@/lib/types";
import {
  Banner, Button, Card, ConfirmButton, EmptyState, ErrorState, Loading, StatusBadge,
} from "@/components/ui";
import { AiAnalysisCard } from "@/components/ai-card";

const ALLOWED_EXT = [".pdf", ".png", ".jpg", ".jpeg", ".dcm"];
const MAX_MB = 25;

export default function RecordDetailPage() {
  const params = useParams<{ id: string }>();
  const recordId = params.id;
  const router = useRouter();
  const [record, setRecord] = useState<MedicalRecord | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [aiReportId, setAiReportId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setRecord(await api.get<MedicalRecord>(`/records/${recordId}`));
    } catch (err) {
      if (err instanceof ApiError && (err.code === "NOT_FOUND" || err.code === "FORBIDDEN")) {
        setNotFound(true); // controlled unauthorized/not-found state
      } else {
        setError("Could not load this record.");
      }
    }
  }, [recordId]);
  useEffect(() => { load(); }, [load]);

  function pickFile(f: File | null) {
    setFileError(null); setFile(f);
    if (!f) return;
    // Client-side pre-checks mirror the server allowlist (server re-validates).
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) { setFile(null); setFileError("Allowed types: PDF, PNG, JPEG, DICOM."); return; }
    if (f.size > MAX_MB * 1024 * 1024) { setFile(null); setFileError("Maximum upload size is 25 MB."); return; }
    if (f.size === 0) { setFile(null); setFileError("Empty files are rejected."); }
  }

  async function upload() {
    if (!file) return;
    setUploading(true); setFileError(null); setOk(null); setError(null);
    try {
      await api.upload(`/records/${recordId}/files`, file);
      setFile(null);
      setOk("Report stored securely."); // only after server confirmation
      await load();
    } catch (err) {
      setFileError(err instanceof ApiError ? err.message : "Upload failed; try again.");
    } finally {
      setUploading(false);
    }
  }

  async function download(fileId: number) {
    setError(null);
    try { await api.download(`/records/${recordId}/download?file_id=${fileId}`); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Download failed."); }
  }

  async function deleteRecord() {
    try {
      await api.del(`/records/${recordId}`);
      router.push("/patient/records");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed.");
    }
  }

  if (notFound) {
    return (
      <Card title="Record unavailable">
        <EmptyState what="This record is not available to you."
          next="It may not exist, or your account may not have access." />
      </Card>
    );
  }
  if (error && !record) return <ErrorState message={error} onRetry={load} />;
  if (!record) return <Loading />;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">{record.title}</h1>
          <p className="text-sm text-ink-soft">Record #{record.id} · {record.record_type}</p>
        </div>
        <ConfirmButton label="Delete record" confirmLabel="Confirm delete?"
          consequence="The record is marked deleted; this cannot be undone from the UI."
          onConfirm={deleteRecord} />
      </header>

      <div className="space-y-2">
        {ok && <Banner kind="ok">{ok}</Banner>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      <Card title="Attach a report">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm font-medium text-ink-soft">
            File (PDF, PNG, JPEG, DICOM — max 25 MB)
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.dcm" className="mt-1 block w-full
              rounded-lg border border-line bg-white px-3 py-2 text-sm file:mr-3 file:rounded
              file:border-0 file:bg-teal-wash file:px-3 file:py-1 file:text-teal-deep"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
          </label>
          <Button onClick={upload} disabled={!file || uploading}>
            {uploading ? "Validating · scanning · encrypting…" : "Upload"}
          </Button>
        </div>
        {fileError && <div className="mt-3"><ErrorState message={fileError} /></div>}
        <p className="mt-2 text-[11px] text-ink-faint">
          Files are quarantined, security-scanned, encrypted and stored outside public web roots.
          Success is shown only after the server confirms storage.
        </p>
      </Card>

      <Card title={`Files (${record.files.length})`}>
        {record.files.length === 0 ? (
          <EmptyState what="No files attached yet." next="Upload a report above." />
        ) : (
          <ul className="divide-y divide-line">
            {record.files.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div className="text-sm">
                  <p className="font-medium text-ink">Protected file #{f.id}</p>
                  <p className="text-xs text-ink-faint">
                    {f.mime_type} · {(f.size / 1024).toFixed(1)} KB · key {f.key_id} v{f.key_version}
                  </p>
                  <p className="font-mono text-[10px] text-ink-faint">sha256 {f.checksum.slice(0, 32)}…</p>
                </div>
                <Button kind="secondary" onClick={() => download(f.id)}>Download</Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <AiAnalysisCard reportId={aiReportId} />
      {!aiReportId && record.reports.length > 0 && (
        <Card title="Start AI analysis">
          <div className="space-y-2">
            {record.reports.map((rp) => (
              <div key={rp.id} className="flex items-center justify-between rounded-lg border border-line bg-paper px-3 py-2 text-sm">
                <span className="text-ink-soft">Report #{rp.id} · {rp.title}</span>
                <Button kind="secondary" onClick={() => setAiReportId(rp.id)}>Analyze this report</Button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
