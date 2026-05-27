import type { MetadataRoute } from "next";
import { API_BASE } from "@/lib/api";

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
  const [allRaces, riders, teams, news] = await Promise.all([
    safeFetch<{ slug: string; start_date: string; end_date: string | null; stage_count: number; category: string }>(`${API_BASE}/races`),
    safeFetch<{ slug: string }>(`${API_BASE}/riders`),
    safeFetch<{ slug: string }>(`${API_BASE}/teams`),
    safeFetch<{ slug: string; published_at: string }>(`${API_BASE}/news?limit=500`),
  ]);

  // Prioritér WorldTour-løb og igangværende/kommende løb højere
  const today = new Date().toISOString().slice(0, 10);
  const races = allRaces.filter(
    (r) => !r.end_date || r.end_date >= new Date(Date.now() - 30 * 86400 * 1000).toISOString().slice(0, 10)
  );

  const raceUrls: MetadataRoute.Sitemap = races.map((r) => {
    const isOngoing = r.start_date <= today && (!r.end_date || r.end_date >= today);
    return {
      url: `${BASE}/${r.slug}`,
      lastModified: r.start_date,
      changeFrequency: isOngoing ? "hourly" : "weekly",
      priority: isOngoing ? 1.0 : 0.9,
    };
  });

  const stageUrls: MetadataRoute.Sitemap = races.flatMap((r) =>
    Array.from({ length: r.stage_count ?? 0 }, (_, i) => ({
      url: `${BASE}/${r.slug}/stage/${i + 1}`,
      lastModified: r.start_date,
      changeFrequency: "daily" as const,
      priority: 0.8,
    }))
  );

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
