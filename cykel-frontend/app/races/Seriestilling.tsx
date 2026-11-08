import Link from "next/link";
import { API_BASE } from "@/lib/api";

/** Seriens officielle samlede stilling (series_standings). Hentes fra seriens
 *  egen side af cross_standings_agent.py — vi regner den aldrig ud selv, fordi
 *  vi kun har top 10 pr. løb. Viser intet, når serien ingen stilling har. */

type Raekke = {
  position: number;
  rider_name: string;
  team_name: string | null;
  points: number | null;
  time_seconds: number | null;
  races_counted: number;
  source_url: string;
  updated_at: string;
  riders: { name: string; slug: string; nationality: string | null } | null;
};

async function hent(kategori: string, antal: number) {
  try {
    const res = await fetch(
      `${API_BASE}/cross-standings?category=${encodeURIComponent(kategori)}&limit=${antal}`,
      { next: { revalidate: 300 } },
    );
    if (!res.ok) return null;
    return (await res.json()) as { season: string | null; rows: Raekke[] };
  } catch {
    return null;
  }
}

/** "NYS Thibau" → "Thibau Nys"; "Michael Vanthourenhout" står allerede rigtigt. */
function visNavn(navn: string): string {
  const dele = navn.trim().split(/\s+/);
  const efter = dele.filter((d) => d.length > 1 && d === d.toUpperCase());
  if (!efter.length || efter.length === dele.length) return navn;
  const for_ = dele.filter((d) => !efter.includes(d));
  const paen = efter
    .map((d) => d.toLowerCase().replace(/(^|[-'])(\p{L})/gu, (_, a: string, b: string) => a + b.toUpperCase()))
    .join(" ");
  return `${for_.join(" ")} ${paen}`;
}

function tid(sek: number): string {
  const h = Math.floor(sek / 3600);
  const m = Math.floor((sek % 3600) / 60);
  const s = sek % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

function flag(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code.toUpperCase().split("").map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)).join("");
}

export default async function Seriestilling({
  kategori,
  serieNavn,
  antal = 30,
  serieHref,
}: {
  kategori: string;
  serieNavn: string;
  /** Hvor mange rækker. Løbssiden viser 5 og linker til seriesiden. */
  antal?: number;
  serieHref?: string;
}) {
  const data = await hent(kategori, antal);
  if (!data || !data.rows.length) return null;
  const forer = data.rows[0];
  const paaTid = forer.time_seconds != null;
  const opdateret = new Date(forer.updated_at).toLocaleDateString("da-DK", {
    day: "numeric", month: "long",
  });

  return (
    <section className="mb-12 rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 py-3 border-b border-slate-800 bg-slate-900/60">
        <h2 className="text-xs uppercase tracking-[0.2em] text-amber-300 font-medium">
          Samlet stilling · {serieNavn} {data.season}
        </h2>
        <span className="text-xs text-slate-500">
          efter {forer.races_counted} løb · {paaTid ? "afgøres på tid" : "point"}
        </span>
      </div>
      <ol className="divide-y divide-slate-800/40">
        {data.rows.map((r, i) => {
          const vaerdi = paaTid
            ? i === 0 ? tid(r.time_seconds ?? 0) : `+${tid((r.time_seconds ?? 0) - (forer.time_seconds ?? 0))}`
            : `${r.points} p`;
          const indhold = (
            <>
              <span className="w-7 text-right font-mono text-xs text-slate-500 flex-shrink-0">{r.position}</span>
              <span className="w-5 text-center text-sm flex-shrink-0">{flag(r.riders?.nationality ?? null)}</span>
              <span className="flex-1 text-sm text-slate-200 truncate">{visNavn(r.rider_name)}</span>
              {r.team_name && (
                <span className="hidden sm:block text-xs text-slate-600 truncate max-w-[220px]">{r.team_name}</span>
              )}
              <span className={`font-mono text-xs flex-shrink-0 ${i === 0 ? "text-amber-300" : "text-slate-400"}`}>
                {vaerdi}
              </span>
            </>
          );
          return (
            <li key={`${r.rider_name}-${i}`}>
              {r.riders?.slug ? (
                <Link href={`/riders/${r.riders.slug}`}
                  className="flex items-center gap-3 px-5 py-2 hover:bg-slate-800/40 transition-colors">
                  {indhold}
                </Link>
              ) : (
                <div className="flex items-center gap-3 px-5 py-2">{indhold}</div>
              )}
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2.5 border-t border-slate-800 text-[11px] text-slate-600">
        <span>Officiel stilling fra seriens egen side, opdateret {opdateret}.</span>
        <a href={forer.source_url} target="_blank" rel="noopener noreferrer"
          className="hover:text-emerald-400 transition-colors">Kilde →</a>
        {serieHref && (
          <Link href={serieHref} className="ml-auto text-emerald-400 hover:underline">
            Hele stillingen og kalenderen →
          </Link>
        )}
      </div>
    </section>
  );
}
