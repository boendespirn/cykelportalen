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
  const [races, riders, teams, news] = await Promise.all([
    safeFetch<{ slug: string; start_date: string; stage_count: number }>(`${API_BASE}/upcoming-races`),
    safeFetch<{ slug: string }>(`${API_BASE}/riders`),
    safeFetch<{ slug: string }>(`${API_BASE}/teams`),
    safeFetch<{ slug: string; published_at: string }>(`${API_BASE}/news?limit=500`),
  ]);

  const raceUrls: MetadataRoute.Sitemap = races.map((r) => ({
    url: `${BASE}/${r.slug}`,
    lastModified: r.start_date,
    changeFrequency: "daily",
    priority: 0.9,
  }));

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
