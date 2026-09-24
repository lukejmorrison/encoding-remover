import "./styles.css";
import type { Catalog, CatalogDrug, DrugCapture, LabeledCount } from "./types";
import { loadCatalog, loadDrug } from "./types";
import {
  downloadBlob,
  exportDrugZip,
  filterReactions,
} from "./export";
import { startIngest, waitForIngest } from "./api";

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("#app missing");

type Route =
  | { view: "home"; q: string }
  | { view: "drug"; slug: string; q: string };

let catalogCache: Catalog | null = null;
const drugCache = new Map<string, DrugCapture>();
let ingestBusy = false;
let ingestStatus = "";

function invalidateCatalog(): void {
  catalogCache = null;
  drugCache.clear();
}

async function getCatalog(): Promise<Catalog> {
  if (!catalogCache) catalogCache = await loadCatalog();
  return catalogCache;
}

async function getDrug(file: string): Promise<DrugCapture> {
  const hit = drugCache.get(file);
  if (hit) return hit;
  const data = await loadDrug(file);
  drugCache.set(file, data);
  return data;
}

function parseRoute(): Route {
  const params = new URLSearchParams(location.search);
  const slug = params.get("drug");
  const q = params.get("q") ?? "";
  if (slug) return { view: "drug", slug, q };
  return { view: "home", q };
}

function setRoute(route: Route, replace = false): void {
  const params = new URLSearchParams();
  if (route.view === "drug") params.set("drug", route.slug);
  if (route.q) params.set("q", route.q);
  const qs = params.toString();
  const url = qs ? `?${qs}` : "/";
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
}

function formatCount(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function highlight(text: string, q: string): string {
  const safe = escapeHtml(text);
  const query = q.trim();
  if (!query) return safe;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx < 0) return safe;
  const before = escapeHtml(text.slice(0, idx));
  const match = escapeHtml(text.slice(idx, idx + query.length));
  const after = escapeHtml(text.slice(idx + query.length));
  return `${before}<mark class="mark">${match}</mark>${after}`;
}

function brandBar(extra = ""): string {
  return `
    <header class="brand-bar">
      <div>
        <p class="brand">Encoding<span>Remover</span></p>
        <p class="tagline">Decoded VigiAccess captures — searchable ADRs, offline-ready, exportable by drug.</p>
      </div>
      <p class="install-hint">${extra || "Install from your browser for offline access."}</p>
    </header>
  `;
}

function renderBars(rows: LabeledCount[]): string {
  const max = Math.max(...rows.map((r) => r.count), 1);
  return `
    <div class="chart-list">
      ${rows
        .map(
          (r) => `
        <div class="bar-row">
          <span>${escapeHtml(r.label)}</span>
          <div class="bar-track"><div class="bar-fill" data-width="${(r.count / max) * 100}"></div></div>
          <span>${formatCount(r.count)}</span>
        </div>`,
        )
        .join("")}
    </div>
  `;
}

function animateBars(root: HTMLElement): void {
  requestAnimationFrame(() => {
    root.querySelectorAll<HTMLElement>(".bar-fill").forEach((el) => {
      el.style.width = `${el.dataset.width ?? 0}%`;
    });
  });
}

function filterCatalog(drugs: CatalogDrug[], q: string): CatalogDrug[] {
  const query = q.trim().toLowerCase();
  if (!query) return drugs;
  return drugs.filter((d) => {
    const hay = `${d.name} ${d.trade_name ?? ""}`.toLowerCase();
    return hay.includes(query);
  });
}

function focusSearch(id: string): void {
  const el = app!.querySelector<HTMLInputElement>(id);
  if (!el) return;
  el.focus();
  const len = el.value.length;
  el.setSelectionRange(len, len);
}

function addDrugPanel(): string {
  return `
    <section class="add-drug" aria-labelledby="add-drug-title">
      <h2 id="add-drug-title">Add a drug</h2>
      <p class="note">Pull a fresh decode from VigiAccess and add it to this catalog. Full preferred-term capture can take a few minutes.</p>
      <form id="add-drug-form" class="add-drug-form">
        <input id="add-drug-input" name="query" type="text" placeholder="e.g. Omeprazole" required maxlength="120" ${ingestBusy ? "disabled" : ""} />
        <label class="check">
          <input type="checkbox" name="include_pts" checked ${ingestBusy ? "disabled" : ""} />
          Include preferred terms
        </label>
        <button class="primary" type="submit" ${ingestBusy ? "disabled" : ""}>${ingestBusy ? "Ingesting…" : "Ingest"}</button>
      </form>
      <p id="ingest-status" class="ingest-status ${ingestBusy ? "busy" : ""}">${escapeHtml(ingestStatus)}</p>
    </section>
  `;
}

function wireAddDrugForm(currentQ: string): void {
  const form = app!.querySelector<HTMLFormElement>("#add-drug-form");
  const statusEl = app!.querySelector<HTMLParagraphElement>("#ingest-status");
  form?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    if (ingestBusy) return;
    const fd = new FormData(form);
    const query = String(fd.get("query") || "").trim();
    const includePts = fd.get("include_pts") === "on";
    if (!query) return;
    void (async () => {
      ingestBusy = true;
      ingestStatus = `Starting ingest for ${query}…`;
      await renderHome(currentQ);
      try {
        const started = await startIngest(query, includePts);
        const jobId = started.job_id || started.id;
        if (!jobId) throw new Error("No job id returned");
        const done = await waitForIngest(jobId, (job) => {
          ingestStatus = job.message || job.status;
          if (statusEl) statusEl.textContent = ingestStatus;
          const live = document.querySelector<HTMLParagraphElement>("#ingest-status");
          if (live) live.textContent = ingestStatus;
        });
        if (done.status === "error") {
          throw new Error(done.error || done.message || "Ingest failed");
        }
        invalidateCatalog();
        ingestStatus = done.message || `Ingested ${query}`;
        ingestBusy = false;
        const slug = done.entry?.slug;
        if (slug) {
          setRoute({ view: "drug", slug, q: "" });
          await renderDrug(slug, "");
          return;
        }
        await renderHome(currentQ);
      } catch (err) {
        ingestBusy = false;
        ingestStatus = err instanceof Error ? err.message : String(err);
        await renderHome(currentQ);
      }
    })();
  });
}

async function renderHome(q: string): Promise<void> {
  if (!catalogCache && !ingestBusy) {
    app!.innerHTML = `
      ${brandBar()}
      <div class="loading">Loading catalog…</div>
    `;
  }
  try {
    const catalog = await getCatalog();
    const drugs = filterCatalog(catalog.drugs, q);
    app!.innerHTML = `
      ${brandBar(`${catalog.drugs.length} drug${catalog.drugs.length === 1 ? "" : "s"} ingested`)}
      ${addDrugPanel()}
      <div class="search-shell">
        <label for="catalog-search">Search drugs</label>
        <input id="catalog-search" type="search" placeholder="e.g. Liraglutide" value="${escapeHtml(q)}" autocomplete="off" ${ingestBusy ? "disabled" : ""} />
      </div>
      <div class="drug-grid" id="drug-grid">
        ${
          drugs.length
            ? drugs
                .map(
                  (d, i) => `
            <button class="drug-item" data-slug="${escapeHtml(d.slug)}" style="animation-delay:${0.04 * i}s" ${ingestBusy ? "disabled" : ""}>
              <div>
                <h2>${highlight(d.name, q)}</h2>
                <p class="meta">${formatCount(d.total_reports)} reports · ${d.soc_count} SOCs · ${d.preferred_term_count} terms · dataset ${escapeHtml(d.dataset_date ?? "—")}</p>
              </div>
              <div class="count">${formatCount(d.total_reports)}</div>
            </button>`,
                )
                .join("")
            : `<p class="empty">No drugs match “${escapeHtml(q)}”. Use <strong>Add a drug</strong> above to ingest one.</p>`
        }
      </div>
    `;

    wireAddDrugForm(q);

    const input = app!.querySelector<HTMLInputElement>("#catalog-search");
    input?.addEventListener("input", () => {
      const next = input.value;
      setRoute({ view: "home", q: next }, true);
      void renderHome(next).then(() => focusSearch("#catalog-search"));
    });

    app!.querySelectorAll<HTMLButtonElement>(".drug-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (ingestBusy) return;
        const slug = btn.dataset.slug!;
        setRoute({ view: "drug", slug, q: "" });
        void renderDrug(slug, "");
      });
    });
  } catch (err) {
    app!.innerHTML = `
      ${brandBar()}
      <p class="error">${escapeHtml(err instanceof Error ? err.message : String(err))}. Run <code>encoding-remover ingest …</code> then rebuild/serve.</p>
    `;
  }
}

async function renderDrug(slug: string, q: string): Promise<void> {
  app!.innerHTML = `
    ${brandBar()}
    <div class="loading">Loading ${escapeHtml(slug)}…</div>
  `;
  try {
    const catalog = await getCatalog();
    const meta = catalog.drugs.find((d) => d.slug === slug);
    if (!meta) throw new Error(`Unknown drug slug: ${slug}`);
    const data = await getDrug(meta.file);
    paintDrug(meta, data, q);
  } catch (err) {
    app!.innerHTML = `
      ${brandBar()}
      <button class="ghost" id="back-home">← All drugs</button>
      <p class="error">${escapeHtml(err instanceof Error ? err.message : String(err))}</p>
    `;
    app!.querySelector("#back-home")?.addEventListener("click", () => {
      setRoute({ view: "home", q: "" });
      void renderHome("");
    });
  }
}

function paintDrug(meta: CatalogDrug, data: DrugCapture, q: string): void {
  const filtered = filterReactions(data.reactions, q);
  app!.innerHTML = `
    ${brandBar(`Dataset ${escapeHtml(data.dataset_date)}`)}
    <div class="back-row">
      <button class="ghost" id="back-home">← All drugs</button>
      <button class="primary" id="export-zip">Export ZIP</button>
    </div>
    <section class="hero-drug">
      <h1>${escapeHtml(data.drug.name)}</h1>
      <p class="lede">${formatCount(data.total_reports)} potential ADR reports across ${data.reactions.length} MedDRA system organ classes. Counts do not imply causality.</p>
      <div class="stat-row">
        <div class="stat"><span class="label">Reports</span><span class="value">${formatCount(data.total_reports)}</span></div>
        <div class="stat"><span class="label">SOCs</span><span class="value">${data.reactions.length}</span></div>
        <div class="stat"><span class="label">Preferred terms</span><span class="value">${formatCount(meta.preferred_term_count)}</span></div>
        <div class="stat"><span class="label">Brands</span><span class="value">${data.brands.length}</span></div>
      </div>
    </section>

    <section class="section">
      <h2>Search reactions</h2>
      <p class="note">Filter system organ classes and preferred terms.</p>
      <div class="search-shell" style="margin-bottom:1rem">
        <label for="rx-search">ADR search</label>
        <input id="rx-search" type="search" placeholder="e.g. nausea, gastrointestinal" value="${escapeHtml(q)}" autocomplete="off" />
      </div>
      <div class="soc-list" id="soc-list">
        ${
          filtered.length
            ? filtered
                .map((r) => {
                  const pts = r.preferred_terms ?? [];
                  return `
            <details class="soc" ${q.trim() ? "open" : ""}>
              <summary>
                <span>${highlight(r.soc, q)}</span>
                <span>${formatCount(r.count)}</span>
              </summary>
              ${
                pts.length
                  ? `<table class="pt-table"><thead><tr><th>Preferred term</th><th>Count</th></tr></thead><tbody>
                      ${pts
                        .map(
                          (pt) =>
                            `<tr><td>${highlight(pt.term, q)}</td><td>${formatCount(pt.count)}</td></tr>`,
                        )
                        .join("")}
                    </tbody></table>`
                  : `<p class="empty" style="padding:1rem">No preferred terms in this capture (summary-only ingest).</p>`
              }
            </details>`;
                })
                .join("")
            : `<p class="empty">No reactions match “${escapeHtml(q)}”.</p>`
        }
      </div>
    </section>

    <section class="section">
      <h2>Reports by year</h2>
      ${renderBars(data.by_year ?? [])}
    </section>
    <section class="section">
      <h2>Age groups</h2>
      ${renderBars(data.by_age_group ?? [])}
    </section>
    <section class="section">
      <h2>Sex</h2>
      ${renderBars(data.by_sex ?? [])}
    </section>
    <section class="section">
      <h2>Continent</h2>
      ${renderBars(data.by_continent ?? [])}
    </section>

    <section class="section">
      <h2>Related brand names</h2>
      <div class="chip-row">
        ${(data.brands ?? []).map((b) => `<span class="chip">${escapeHtml(b)}</span>`).join("") || `<p class="empty">None listed</p>`}
      </div>
    </section>

    <p class="caveat">${escapeHtml(data.caveat ?? "VigiAccess data is aggregate potential side-effect reporting only.")}</p>
  `;

  animateBars(app!);

  app!.querySelector("#back-home")?.addEventListener("click", () => {
    setRoute({ view: "home", q: "" });
    void renderHome("");
  });

  const exportBtn = app!.querySelector<HTMLButtonElement>("#export-zip");
  exportBtn?.addEventListener("click", async () => {
    exportBtn.disabled = true;
    exportBtn.textContent = "Packing…";
    try {
      const blob = await exportDrugZip(data, meta.slug);
      downloadBlob(blob, `${meta.slug}-vigiaccess.zip`);
    } finally {
      exportBtn.disabled = false;
      exportBtn.textContent = "Export ZIP";
    }
  });

  const input = app!.querySelector<HTMLInputElement>("#rx-search");
  let timer = 0;
  input?.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      const next = input.value;
      setRoute({ view: "drug", slug: meta.slug, q: next }, true);
      paintDrug(meta, data, next);
      focusSearch("#rx-search");
    }, 120);
  });
}

async function boot(): Promise<void> {
  const route = parseRoute();
  if (route.view === "drug") await renderDrug(route.slug, route.q);
  else await renderHome(route.q);
}

window.addEventListener("popstate", () => {
  void boot();
});

void boot();
