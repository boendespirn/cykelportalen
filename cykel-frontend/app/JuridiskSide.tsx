import Link from "next/link";
import { KONTAKT_STI, POLITIK_OPDATERET, UDGIVER } from "@/lib/udgiver";

/**
 * Henvisning til kontaktformularen. Bruges overalt hvor der ellers ville
 * have stået en mailadresse — se noten i lib/udgiver.ts.
 */
export function KontaktLink({ tekst = "kontaktformularen" }: { tekst?: string }) {
  return <Link href={KONTAKT_STI}>{tekst}</Link>;
}

/**
 * Fælles ramme for cookiepolitik, privatlivspolitik og vilkår, så de tre
 * sider har samme opbygning — brugeren lærer dem én gang.
 */

const JURIDISKE_SIDER = [
  { href: "/privatlivspolitik", titel: "Privatlivspolitik" },
  { href: "/cookiepolitik", titel: "Cookiepolitik" },
  { href: "/vilkaar-og-betingelser", titel: "Vilkår og betingelser" },
];

export function JuridiskSide({
  kicker,
  titel,
  indledning,
  aktivSti,
  children,
}: {
  kicker: string;
  titel: string;
  indledning: string;
  aktivSti: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-12">
        <p className="mb-4 text-xs uppercase tracking-[0.25em] text-emerald-400">{kicker}</p>
        <h1 className="font-display text-5xl leading-none tracking-wide text-white sm:text-7xl">
          {titel}
        </h1>
        <p className="mt-5 max-w-xl text-sm leading-relaxed text-slate-400">{indledning}</p>
        <p className="mt-4 text-xs text-slate-600">Sidst opdateret: {POLITIK_OPDATERET}</p>
      </header>

      <div className="space-y-10">{children}</div>

      <nav className="mt-16 border-t border-slate-800 pt-8">
        <p className="mb-3 text-xs uppercase tracking-widest text-slate-600">Øvrige vilkår</p>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {JURIDISKE_SIDER.filter((s) => s.href !== aktivSti).map((s) => (
            <Link
              key={s.href}
              href={s.href}
              className="text-sm text-emerald-400 transition-colors hover:text-emerald-300"
            >
              {s.titel} →
            </Link>
          ))}
          <Link
            href="/kontakt"
            className="text-sm text-slate-400 transition-colors hover:text-slate-300"
          >
            Kontakt →
          </Link>
        </div>
      </nav>
    </div>
  );
}

export function Afsnit({
  nr,
  titel,
  children,
}: {
  nr: number;
  titel: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-3 flex items-baseline gap-3 text-lg font-semibold text-white">
        <span className="font-mono text-sm text-emerald-500/70">{nr}.</span>
        {titel}
      </h2>
      <div className="space-y-3 text-sm leading-relaxed text-slate-300 [&_a]:text-emerald-400 [&_a:hover]:underline [&_strong]:font-medium [&_strong]:text-slate-100 [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}

/**
 * Hvem står bag siden. Genbruges på alle tre sider, så identiteten står ens.
 * CVR og adresse vises først, når de er udfyldt i lib/udgiver.ts.
 */
export function Afsender() {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 text-sm">
      <p className="mb-3 text-xs uppercase tracking-widest text-slate-500">Ansvarlig for siden</p>
      <dl className="space-y-1.5 text-slate-300">
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-slate-500">Tjeneste</dt>
          <dd>
            {UDGIVER.navn} ({UDGIVER.domaene})
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-slate-500">Kontakt</dt>
          <dd>
            <Link href={KONTAKT_STI} className="text-emerald-400 hover:underline">
              Skriv til os via kontaktformularen →
            </Link>
          </dd>
        </div>
        {UDGIVER.cvr && (
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 text-slate-500">CVR-nr.</dt>
            <dd>{UDGIVER.cvr}</dd>
          </div>
        )}
        {UDGIVER.adresse && (
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 text-slate-500">Adresse</dt>
            <dd>{UDGIVER.adresse}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}
