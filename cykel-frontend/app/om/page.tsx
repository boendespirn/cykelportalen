import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Om os",
  description:
    "Klassementet er lavet af en cykel- og AI-entusiast, der ville samle al den fedeste data om professionel cykling ét sted.",
};

export default function OmPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-14">
        <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">
          Om Klassementet
        </p>
        <h1 className="font-display text-7xl sm:text-9xl tracking-wide leading-none text-white">
          Om os
        </h1>
      </header>

      <div className="space-y-8 text-slate-300 leading-relaxed">
        <p className="text-lg sm:text-xl text-slate-200 leading-relaxed">
          Klassementet er lavet af en cykel- og AI-entusiast, der ville samle
          al den fedeste data om professionel cykling ét sted.
        </p>

        <p>
          Målet er simpelt: give dig bedre indsigt og overblik i et løb —
          hvem kører hvad, hvornår, og hvorfor det er spændende. Ikke bare
          resultater, men konteksten bag: hvem er favoritterne, hvad siger
          højdeprofilen, og hvilke ryttere skal du holde øje med?
        </p>

        <p>
          Bag siden ligger en håndfuld scrapers, AI-agenter og en kærlighed
          til tal, der henter data fra UCI, ProCyclingStats og VeloWire og
          koger det ned til det vigtigste.
        </p>

        <p>
          Vi dækker UCI WorldTour — de største løb med de bedste ryttere.
          Fra Giro og Tour til klassikerne og alt derimellem.
        </p>

        <div className="pt-4 border-t border-slate-800 flex flex-col sm:flex-row gap-4">
          <Link
            href="/races"
            className="inline-flex items-center gap-2 text-emerald-400 hover:text-emerald-300 transition-colors text-sm font-medium"
          >
            Se løbskalenderen →
          </Link>
          <Link
            href="/nyheder"
            className="inline-flex items-center gap-2 text-slate-400 hover:text-slate-300 transition-colors text-sm"
          >
            Seneste nyheder →
          </Link>
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a
            href="/api/rss"
            className="inline-flex items-center gap-2 text-slate-500 hover:text-slate-400 transition-colors text-sm"
          >
            RSS feed →
          </a>
        </div>
      </div>
    </div>
  );
}
