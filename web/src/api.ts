import type { CatalogDrug } from "./types";

export type IngestJob = {
  id?: string;
  job_id?: string;
  query?: string;
  status: "running" | "done" | "error";
  message?: string;
  error?: string;
  entry?: CatalogDrug;
};

export async function startIngest(
  query: string,
  includePreferredTerms = true,
): Promise<IngestJob> {
  const res = await fetch("/api/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      include_preferred_terms: includePreferredTerms,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `Ingest failed (${res.status})`);
  }
  return data;
}

export async function getIngestJob(jobId: string): Promise<IngestJob> {
  const res = await fetch(`/api/ingest/${jobId}`, { cache: "no-cache" });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `Job status failed (${res.status})`);
  }
  return data;
}

export async function waitForIngest(
  jobId: string,
  onUpdate?: (job: IngestJob) => void,
): Promise<IngestJob> {
  for (;;) {
    const job = await getIngestJob(jobId);
    onUpdate?.(job);
    if (job.status === "done" || job.status === "error") return job;
    await new Promise((r) => setTimeout(r, 1500));
  }
}
