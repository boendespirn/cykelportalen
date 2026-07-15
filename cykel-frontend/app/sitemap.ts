import type { MetadataRoute } from "next";
import { API_BASE } from "@/lib/api";
import { isHistoricRaceSlug } from "@/lib/historic-stage";

const BASE = "https://klassementet.dk";

async function safeFetch<T>(url: string): Promise<T[]> {
  try {
    const res = await fetch(url, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [races, riders, teams, news] = await Promise.all([
    safeFetch<{
      slug: string; start_date: string; end_date: string | null;
      stage_count: number; ready_through_stage: number; category: string;
    }>(`${API_BASE}/races`),
    safeFetch<{ slug: string }>(`${API_BASE}/riders`),
    safeFetch<{ slug: string }>(`${API_BASE}/teams`),
    safeFetch<{ slug: string; published_at: string }>(`${API_BASE}/news?limit=500`),
  ]);

  // Alle løb er med (historiske løb er ikke længere udelukket, jf.
  // SEO-022/SEO-023-backfillen — historiske sider skal kunne findes af
  // Google), men prioritet/opdateringshyppighed differentierer stadig
  // igangværende løb højest.
  const today = new Date().toISOString().slice(0, 10);

  const raceUrls: MetadataRoute.Sitemap = races.map((r) => {
    const isOngoing = r.start_date <= today && (!r.end_date || r.end_date >= today);
    return {
      url: `${BASE}/${r.slug}`,
      lastModified: r.start_date,
      changeFrequency: isOngoing ? "hourly" : isHistoricRaceSlug(r.slug) ? "monthly" : "weekly",
      priority: isOngoing ? 1.0 : isHistoricRaceSlug(r.slug) ? 0.5 : 0.9,
    };
  });

  // Etsdagsløb (stage_count <= 1) har al deres info på løbssiden selv —
  // /stage/1 redirecter permanent dertil, så den skal ikke i sitemappet.
  // For historiske løb medtages KUN etaper der reelt er backfillet
  // (ready_through_stage — se api.py get_races()) — ellers genindfører vi
  // præcis det 404-i-sitemap-problem SEO-019 oprindeligt fjernede.
  const stageUrls: MetadataRoute.Sitemap = races
    .filter((r) => (r.stage_count ?? 0) > 1)
    .flatMap((r) => {
      const historic = isHistoricRaceSlug(r.slug);
      const count = historic ? Math.min(r.ready_through_stage ?? 0, r.stage_count ?? 0) : (r.stage_count ?? 0);
      return Array.from({ length: count }, (_, i) => ({
        url: `${BASE}/${r.slug}/stage/${i + 1}`,
        lastModified: r.start_date,
        changeFrequency: historic ? ("monthly" as const) : ("daily" as const),
        priority: historic ? 0.5 : 0.8,
      }));
    });

  const riderUrls: MetadataRoute.Sitemap = riders.map((r) => ({
    url: `${BASE}/riders/${r.slug}`,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  const teamUrls: MetadataRoute.Sitemap = teams.map((t) => ({
    url: `${BASE}/teams/${t.slug}`,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  const newsUrls: MetadataRoute.Sitemap = news.map((n) => ({
    url: `${BASE}/nyheder/${n.slug}`,
    lastModified: n.published_at,
    changeFrequency: "never",
    priority: 0.7,
  }));

  return [
    { url: BASE, changeFrequency: "daily", priority: 1.0 },
    { url: `${BASE}/races`, changeFrequency: "daily", priority: 0.6 },
    { url: `${BASE}/riders`, changeFrequency: "weekly", priority: 0.5 },
    { url: `${BASE}/teams`, changeFrequency: "weekly", priority: 0.5 },
    { url: `${BASE}/nyheder`, changeFrequency: "daily", priority: 0.7 },
    ...raceUrls,
    ...stageUrls,
    ...riderUrls,
    ...teamUrls,
    ...newsUrls,
  ];
}
