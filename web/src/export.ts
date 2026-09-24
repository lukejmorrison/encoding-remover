import JSZip from "jszip";
import type { DrugCapture, LabeledCount, Reaction } from "./types";

function csvEscape(value: string | number): string {
  const s = String(value);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function rowsToCsv(headers: string[], rows: (string | number)[][]): string {
  const lines = [headers.map(csvEscape).join(",")];
  for (const row of rows) lines.push(row.map(csvEscape).join(","));
  return lines.join("\n") + "\n";
}

function labeledCsv(rows: LabeledCount[]): string {
  return rowsToCsv(
    ["label", "count"],
    rows.map((r) => [r.label, r.count]),
  );
}

export type ZipEntry = {
  slug: string;
  data: DrugCapture;
};

const ALL_ZIPS_ROOT = "vigiaccess-all-zips";
const SELECTED_ROOT = "vigiaccess-export";

function writeCapture(folder: JSZip, data: DrugCapture): void {
  folder.file("capture.json", JSON.stringify(data, null, 2) + "\n");
  const csvs = buildCsvBundle(data);
  for (const [name, content] of Object.entries(csvs)) {
    folder.file(name, content);
  }
  folder.file(
    "README.txt",
    [
      `${data.drug.name} — VigiAccess capture`,
      `Dataset date: ${data.dataset_date}`,
      `Total reports: ${data.total_reports}`,
      "",
      data.caveat ?? "",
      "",
      `Source: ${data.source ?? "https://www.vigiaccess.org/"}`,
      "",
      "Files",
      "-----",
      "capture.json          full decoded capture",
      "reactions_soc.csv     system organ class counts",
      "preferred_terms.csv   preferred terms by system organ class",
      "by_year.csv",
      "by_age_group.csv",
      "by_sex.csv",
      "by_continent.csv",
      "brands.csv",
      "",
    ].join("\n"),
  );
}

function drugLine(entry: ZipEntry): string {
  const date = entry.data.dataset_date || "—";
  return `${entry.slug}/ — ${entry.data.drug.name} — ${entry.data.total_reports} reports — dataset ${date}`;
}

export function buildCsvBundle(data: DrugCapture): Record<string, string> {
  const files: Record<string, string> = {};
  files["reactions_soc.csv"] = rowsToCsv(
    ["soc", "count"],
    data.reactions.map((r) => [r.soc, r.count]),
  );
  const pts: (string | number)[][] = [];
  for (const r of data.reactions) {
    for (const pt of r.preferred_terms ?? []) {
      pts.push([r.soc, pt.term, pt.count]);
    }
  }
  files["preferred_terms.csv"] = rowsToCsv(["soc", "term", "count"], pts);
  files["by_year.csv"] = labeledCsv(data.by_year ?? []);
  files["by_age_group.csv"] = labeledCsv(data.by_age_group ?? []);
  files["by_sex.csv"] = labeledCsv(data.by_sex ?? []);
  files["by_continent.csv"] = labeledCsv(data.by_continent ?? []);
  files["brands.csv"] = rowsToCsv(
    ["brand"],
    (data.brands ?? []).map((b) => [b]),
  );
  return files;
}

async function drugZipBytes(data: DrugCapture, slug: string): Promise<Uint8Array> {
  const zip = new JSZip();
  const folder = zip.folder(slug) ?? zip;
  writeCapture(folder, data);
  return zip.generateAsync({ type: "uint8array" });
}

export async function exportDrugZip(
  data: DrugCapture,
  slug: string,
): Promise<Blob> {
  const bytes = await drugZipBytes(data, slug);
  return new Blob([bytes], { type: "application/zip" });
}

export async function exportAllZips(
  entries: ZipEntry[],
  onProgress?: (done: number, total: number) => void,
): Promise<Blob> {
  const zip = new JSZip();
  const root = zip.folder(ALL_ZIPS_ROOT) ?? zip;
  const total = entries.length;
  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    const bytes = await drugZipBytes(entry.data, entry.slug);
    root.file(`${entry.slug}-vigiaccess.zip`, bytes);
    onProgress?.(i + 1, total);
  }
  root.file(
    "README.txt",
    [
      "VigiAccess — all drug ZIPs",
      "",
      "Each file is the same ZIP you get from a single drug’s Export ZIP button.",
      "Unzip one to get a folder of capture.json and CSV files.",
      "",
      ...entries.map((entry) => `${entry.slug}-vigiaccess.zip — ${entry.data.drug.name}`),
      "",
    ].join("\n"),
  );
  return zip.generateAsync({ type: "blob", compression: "STORE" });
}

export async function exportSelectedFolders(entries: ZipEntry[]): Promise<Blob> {
  const zip = new JSZip();
  const root = zip.folder(SELECTED_ROOT) ?? zip;
  for (const entry of entries) {
    const folder = root.folder(entry.slug) ?? root;
    writeCapture(folder, entry.data);
  }
  root.file(
    "README.txt",
    [
      "VigiAccess export",
      "",
      "Unzip this archive and use the vigiaccess-export folder.",
      "Each drug is its own subfolder of capture.json and CSV files.",
      "",
      ...entries.map(drugLine),
      "",
    ].join("\n"),
  );
  return zip.generateAsync({ type: "blob" });
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function filterReactions(
  reactions: Reaction[],
  query: string,
): Reaction[] {
  const q = query.trim().toLowerCase();
  if (!q) return reactions;
  return reactions
    .map((r) => {
      const socHit = r.soc.toLowerCase().includes(q);
      const pts = (r.preferred_terms ?? []).filter((pt) =>
        pt.term.toLowerCase().includes(q),
      );
      if (socHit) return r;
      if (pts.length) return { ...r, preferred_terms: pts };
      return null;
    })
    .filter((r): r is Reaction => r !== null);
}
