export type CatalogDrug = {
  slug: string;
  name: string;
  trade_name: string | null;
  total_reports: number;
  dataset_date?: string;
  retrieved_at?: string;
  soc_count: number;
  preferred_term_count: number;
  brand_count: number;
  file: string;
};

export type Catalog = {
  version: number;
  drugs: CatalogDrug[];
};

export type PreferredTerm = { term: string; count: number };
export type Reaction = {
  soc: string;
  count: number;
  preferred_terms?: PreferredTerm[];
};
export type LabeledCount = { label: string; count: number };

export type DrugCapture = {
  query: string;
  dataset_date: string;
  retrieved_at: string;
  drug: { name: string; trade_name: string | null };
  total_reports: number;
  brands: string[];
  search_matches?: { name: string; trade_name: string | null }[];
  reactions: Reaction[];
  by_year: LabeledCount[];
  by_age_group: LabeledCount[];
  by_sex: LabeledCount[];
  by_continent: LabeledCount[];
  source?: string;
  caveat?: string;
};

export async function loadCatalog(): Promise<Catalog> {
  const res = await fetch("/data/catalog.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`Catalog not found (${res.status})`);
  return res.json();
}

export async function loadDrug(file: string): Promise<DrugCapture> {
  const res = await fetch(`/data/${file}`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`Drug file missing (${res.status})`);
  return res.json();
}
