"use client";

import Link from "next/link";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import {
  ACCEPTER_ALLE,
  AFVIS_ALLE,
  ER_HYDRERET,
  ER_IKKE_HYDRERET,
  gemSamtykke,
  samtykkeServerSnapshot,
  samtykkeSnapshot,
  samtykkeSubscribe,
  type Samtykke,
  type SamtykkeValg,
} from "@/lib/samtykke";

type SamtykkeKontekst = {
  /** null = brugeren har endnu ikke taget stilling. Intet ikke-nødvendigt må køre. */
  samtykke: Samtykke | null;
  /** Er en given kategori aktivt tilvalgt? Falsk indtil der er sagt ja. */
  harSamtykke: (kategori: keyof SamtykkeValg) => boolean;
  /** Åbner indstillingspanelet — bruges af "Cookieindstillinger" i footeren. */
  aabenIndstillinger: () => void;
  /** Giver samtykke til én kategori, fx fra en pladsholder over et indlejret element. */
  tilladKategori: (kategori: keyof SamtykkeValg) => void;
};

const Kontekst = createContext<SamtykkeKontekst | null>(null);

export function useSamtykke(): SamtykkeKontekst {
  const kontekst = useContext(Kontekst);
  if (!kontekst) {
    // Uden provider er det sikre svar "intet samtykke" — så fejler vi lukket,
    // ikke åbent, hvis en komponent nogensinde havner uden for provideren.
    return {
      samtykke: null,
      harSamtykke: () => false,
      aabenIndstillinger: () => {},
      tilladKategori: () => {},
    };
  }
  return kontekst;
}

const KATEGORIER: {
  noegle: keyof SamtykkeValg;
  titel: string;
  beskrivelse: string;
}[] = [
  {
    noegle: "statistik",
    titel: "Statistik",
    beskrivelse:
      "Anonym besøgsstatistik via Vercel Analytics, så vi kan se hvilke sider der bliver brugt, og gøre dem bedre. Der sættes ingen cookies, og du bliver ikke fulgt på tværs af websites.",
  },
  {
    noegle: "tredjepart",
    titel: "Indlejret indhold",
    beskrivelse:
      "Interaktive 3D-stigningsprofiler fra VeloViewer. Indholdet hentes direkte fra VeloViewer, som derfor modtager din IP-adresse og kan sætte egne cookies. Siger du nej, viser vi i stedet vores egen tegnede profil, hvor vi har en.",
  },
];

export default function SamtykkeProvider({ children }: { children: React.ReactNode }) {
  // Samtykket læses direkte fra cookien som et eksternt store, så alle
  // komponenter ser samme værdi, og et nyt valg forplanter sig med det samme.
  const samtykke = useSyncExternalStore(
    samtykkeSubscribe,
    samtykkeSnapshot,
    samtykkeServerSnapshot,
  );
  // Server-HTML'en kender ikke brugerens valg, så banneret må først dukke op
  // efter hydreringen — ellers blinker det hos dem, der allerede har svaret.
  const hydreret = useSyncExternalStore(samtykkeSubscribe, ER_HYDRERET, ER_IKKE_HYDRERET);

  const [panelAabent, setPanelAabent] = useState(false);
  // Panelets kladde sættes, når panelet åbnes, så den altid starter fra det
  // faktiske samtykke.
  const [udkast, setUdkast] = useState<SamtykkeValg>(AFVIS_ALLE);

  const vaelg = useCallback((valg: SamtykkeValg) => {
    gemSamtykke(valg);
    setPanelAabent(false);
  }, []);

  const vaerdi = useMemo<SamtykkeKontekst>(
    () => ({
      samtykke,
      harSamtykke: (kategori) => samtykke?.[kategori] === true,
      aabenIndstillinger: () => {
        setUdkast(
          samtykke ? { statistik: samtykke.statistik, tredjepart: samtykke.tredjepart } : AFVIS_ALLE,
        );
        setPanelAabent(true);
      },
      tilladKategori: (kategori) => {
        const nuvaerende: SamtykkeValg = samtykke
          ? { statistik: samtykke.statistik, tredjepart: samtykke.tredjepart }
          : AFVIS_ALLE;
        vaelg({ ...nuvaerende, [kategori]: true });
      },
    }),
    [samtykke, vaelg],
  );

  const visBanner = hydreret && !samtykke && !panelAabent;

  return (
    <Kontekst.Provider value={vaerdi}>
      {children}

      {visBanner && (
        <div
          role="region"
          aria-label="Samtykke til cookies"
          className="fixed inset-x-0 bottom-0 z-50 border-t border-slate-800 bg-slate-950/95 backdrop-blur-sm"
        >
          <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm leading-relaxed text-slate-300 sm:max-w-xl">
              <p className="mb-1 font-medium text-slate-100">Vi spørger, før vi måler noget</p>
              <p className="text-[13px] text-slate-400">
                Vi bruger kun det nødvendige for at vise siden. Vil du også tillade anonym
                besøgsstatistik og indlejrede 3D-profiler fra VeloViewer? Vi bruger aldrig
                reklame- eller marketingcookies. Læs mere i{" "}
                <Link href="/cookiepolitik" className="text-emerald-400 hover:underline">
                  cookiepolitikken
                </Link>
                .
              </p>
            </div>

            {/* Afvis og accepter har med vilje samme størrelse og vægt — et
                "nej" skal være lige så let som et "ja". */}
            <div className="flex flex-col gap-2 sm:shrink-0">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => vaelg(AFVIS_ALLE)}
                  className="flex-1 rounded-xl border border-slate-700 bg-slate-900 px-5 py-2.5 text-sm font-medium text-slate-200 transition-colors hover:border-slate-600 hover:bg-slate-800 sm:w-36 sm:flex-none"
                >
                  Afvis alle
                </button>
                <button
                  type="button"
                  onClick={() => vaelg(ACCEPTER_ALLE)}
                  className="flex-1 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-5 py-2.5 text-sm font-medium text-emerald-300 transition-colors hover:border-emerald-500/60 hover:bg-emerald-500/20 sm:w-36 sm:flex-none"
                >
                  Accepter alle
                </button>
              </div>
              <button
                type="button"
                onClick={vaerdi.aabenIndstillinger}
                className="text-xs text-slate-500 underline-offset-2 transition-colors hover:text-slate-300 hover:underline"
              >
                Tilpas selv
              </button>
            </div>
          </div>
        </div>
      )}

      {panelAabent && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/80 backdrop-blur-sm sm:items-center sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="cookie-indstillinger-titel"
        >
          <div className="w-full max-w-lg overflow-hidden rounded-t-2xl border border-slate-800 bg-slate-900 sm:rounded-2xl">
            <div className="border-b border-slate-800 px-6 py-5">
              <h2
                id="cookie-indstillinger-titel"
                className="font-display text-3xl tracking-wide text-white"
              >
                Cookieindstillinger
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Du kan ændre dit valg når som helst via Cookieindstillinger nederst på siden.
              </p>
            </div>

            <div className="max-h-[55vh] divide-y divide-slate-800 overflow-y-auto">
              <div className="px-6 py-4">
                <div className="mb-1 flex items-center justify-between gap-4">
                  <p className="text-sm font-medium text-slate-200">Nødvendige</p>
                  <span className="shrink-0 rounded border border-slate-700 px-2 py-0.5 text-[10px] uppercase tracking-widest text-slate-500">
                    Altid aktiv
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-slate-500">
                  Husker udelukkende dit cookievalg, så vi ikke spørger igen ved hvert besøg.
                  Kræver ikke samtykke og kan derfor ikke fravælges.
                </p>
              </div>

              {KATEGORIER.map((k) => (
                <div key={k.noegle} className="px-6 py-4">
                  <div className="mb-1 flex items-center justify-between gap-4">
                    <label
                      htmlFor={`samtykke-${k.noegle}`}
                      className="cursor-pointer text-sm font-medium text-slate-200"
                    >
                      {k.titel}
                    </label>
                    <input
                      id={`samtykke-${k.noegle}`}
                      type="checkbox"
                      checked={udkast[k.noegle]}
                      onChange={(e) =>
                        setUdkast((u) => ({ ...u, [k.noegle]: e.target.checked }))
                      }
                      className="h-5 w-5 shrink-0 cursor-pointer accent-emerald-500"
                    />
                  </div>
                  <p className="text-xs leading-relaxed text-slate-500">{k.beskrivelse}</p>
                </div>
              ))}
            </div>

            <div className="flex flex-col gap-2 border-t border-slate-800 px-6 py-4 sm:flex-row">
              <button
                type="button"
                onClick={() => vaelg(AFVIS_ALLE)}
                className="flex-1 rounded-xl border border-slate-700 bg-slate-900 px-5 py-2.5 text-sm font-medium text-slate-200 transition-colors hover:border-slate-600 hover:bg-slate-800"
              >
                Afvis alle
              </button>
              <button
                type="button"
                onClick={() => vaelg(udkast)}
                className="flex-1 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-5 py-2.5 text-sm font-medium text-emerald-300 transition-colors hover:border-emerald-500/60 hover:bg-emerald-500/20"
              >
                Gem mit valg
              </button>
            </div>
          </div>
        </div>
      )}
    </Kontekst.Provider>
  );
}

/** Footer-knap, der åbner indstillingspanelet igen — tilbagetrækning af samtykke. */
export function CookieIndstillingerKnap({ className }: { className?: string }) {
  const { aabenIndstillinger } = useSamtykke();
  return (
    <button type="button" onClick={aabenIndstillinger} className={className}>
      Cookieindstillinger
    </button>
  );
}

/** Vercel Analytics indlæses først, når der er samtykke til statistik. */
export function SamtykkeAnalytics({ children }: { children: React.ReactNode }) {
  const { harSamtykke } = useSamtykke();
  return harSamtykke("statistik") ? <>{children}</> : null;
}
