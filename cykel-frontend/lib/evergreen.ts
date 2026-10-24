/**
 * Faste adresser for løb, der køres hvert år (ejer-godkendt 2026-10-24).
 *
 * Den aktuelle udgave bor på den faste adresse (/tour-de-france og
 * /tour-de-france/stage/N), og ældre udgaver ligger som arkiv på deres
 * årstals-adresse (/tour-de-france-2026). Så samler én adresse alle links og
 * al autoritet år efter år i stedet for at starte forfra hver sommer.
 *
 * Fire regler, der skal holde:
 *  1. Årstallet står i titel og H1, så siden også rangerer på "… 2027".
 *  2. Etaperne har også faste adresser: /tour-de-france/stage/N.
 *  3. Hver udgave findes kun på ÉN adresse ad gangen. Den aktuelle udgaves
 *     årstals-adresse sender midlertidigt (307) videre til den faste — den
 *     bliver selv arkivsiden, når næste udgave tager over (se proxy.ts).
 *  4. Arkivsiderne flyttes aldrig, så gamle links bliver ved med at virke.
 *
 * Skiftet til næste udgave sker HER, når dens data er hentet — og samtidig i
 * linkstrategi.py's EVERGREEN, så de interne links følger med.
 */
export const AKTUELLE_UDGAVER: Record<string, string> = {
  "tour-de-france": "tour-de-france-2027",
};

const FAST_ADRESSE: Record<string, string> = Object.fromEntries(
  Object.entries(AKTUELLE_UDGAVER).map(([fast, udgave]) => [udgave, fast]),
);

/** Den offentlige adresse for et løb: den faste, hvis det er den aktuelle udgave. */
export function raceHref(slug: string): string {
  return `/${FAST_ADRESSE[slug] ?? slug}`;
}

export function stageHref(slug: string, stageNumber: number | string): string {
  return `${raceHref(slug)}/stage/${stageNumber}`;
}

/** Er løbet den aktuelle udgave på en fast adresse? */
export function erFastAdresse(slug: string): boolean {
  return slug in FAST_ADRESSE;
}

/** Til proxy.ts: hvilken udgave en fast adresse viser, og omvendt. */
export function udgaveFor(fast: string): string | undefined {
  return AKTUELLE_UDGAVER[fast];
}
export function fastAdresseFor(slug: string): string | undefined {
  return FAST_ADRESSE[slug];
}
