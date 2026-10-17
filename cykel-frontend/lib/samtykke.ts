/**
 * Cookiesamtykke — lagring og læsning.
 *
 * Samtykket ligger i en first-party cookie, så varigheden er dokumenterbar
 * og kan oplyses i cookiepolitikken (12 måneder, jf. Erhvervsstyrelsens
 * anbefaling om at genindhente samtykke mindst én gang om året).
 *
 * `version` findes, fordi et samtykke kun dækker de formål, brugeren faktisk
 * blev spurgt om. Tilføjer vi en ny kategori, hæves versionen, og banneret
 * vises igen — et gammelt samtykke må ikke bruges som dækning for nyt.
 */

export const SAMTYKKE_COOKIE = "klassementet_samtykke";
export const SAMTYKKE_VERSION = 1;
export const SAMTYKKE_VARIGHED_DAGE = 365;

/** De kategorier brugeren kan til- og fravælge. Nødvendige er ikke med — de kan ikke fravælges. */
export type SamtykkeValg = {
  /** Vercel Analytics (cookiefri besøgsstatistik). */
  statistik: boolean;
  /** Indlejret indhold fra tredjepart, i dag VeloViewers 3D-stigningsprofiler. */
  tredjepart: boolean;
};

export type Samtykke = SamtykkeValg & {
  version: number;
  /** ISO-tidspunkt for valget — dokumentation efter databeskyttelsesforordningens art. 7. */
  tidspunkt: string;
};

export const AFVIS_ALLE: SamtykkeValg = { statistik: false, tredjepart: false };
export const ACCEPTER_ALLE: SamtykkeValg = { statistik: true, tredjepart: true };

/** Udsendes på `window`, når samtykket ændres, så lyttere kan reagere uden at genindlæse. */
export const SAMTYKKE_EVENT = "klassementet:samtykke";

export function laesSamtykke(): Samtykke | null {
  if (typeof document === "undefined") return null;
  try {
    const raekke = document.cookie
      .split("; ")
      .find((c) => c.startsWith(`${SAMTYKKE_COOKIE}=`));
    if (!raekke) return null;

    const data = JSON.parse(decodeURIComponent(raekke.slice(SAMTYKKE_COOKIE.length + 1)));
    // Et samtykke til en ældre version af kategorierne dækker ikke de nye.
    if (data?.version !== SAMTYKKE_VERSION) return null;

    return {
      version: SAMTYKKE_VERSION,
      statistik: data.statistik === true,
      tredjepart: data.tredjepart === true,
      tidspunkt: typeof data.tidspunkt === "string" ? data.tidspunkt : "",
    };
  } catch {
    return null;
  }
}

export function gemSamtykke(valg: SamtykkeValg): Samtykke {
  const samtykke: Samtykke = {
    ...valg,
    version: SAMTYKKE_VERSION,
    tidspunkt: new Date().toISOString(),
  };

  if (typeof document !== "undefined") {
    const sikker = typeof location !== "undefined" && location.protocol === "https:" ? "; Secure" : "";
    document.cookie =
      `${SAMTYKKE_COOKIE}=${encodeURIComponent(JSON.stringify(samtykke))}` +
      `; Path=/; Max-Age=${SAMTYKKE_VARIGHED_DAGE * 24 * 60 * 60}; SameSite=Lax${sikker}`;
    window.dispatchEvent(new CustomEvent(SAMTYKKE_EVENT, { detail: samtykke }));
  }

  return samtykke;
}

export function sletSamtykke(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SAMTYKKE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
  window.dispatchEvent(new CustomEvent(SAMTYKKE_EVENT, { detail: null }));
}

/* --- Samtykket som eksternt store (useSyncExternalStore) ----------------
 *
 * Cookien er en kilde uden for React. Læses den i en useEffect og lægges i
 * state, får vi både en ekstra render og et kort glimt af banneret for dem,
 * der allerede har svaret. Et store løser begge: server-snapshottet er null,
 * og klienten skifter til den rigtige værdi i hydreringen.
 */

export function samtykkeSubscribe(paaAendring: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(SAMTYKKE_EVENT, paaAendring);
  return () => window.removeEventListener(SAMTYKKE_EVENT, paaAendring);
}

// getSnapshot SKAL returnere samme reference, så længe intet har ændret sig —
// ellers render-looper useSyncExternalStore. Derfor caches det parsede
// resultat, indtil den rå cookiestreng faktisk skifter.
let sidsteRaaCookie: string | null = null;
let sidsteSamtykke: Samtykke | null = null;

export function samtykkeSnapshot(): Samtykke | null {
  const raa = typeof document === "undefined" ? "" : document.cookie;
  if (raa !== sidsteRaaCookie) {
    sidsteRaaCookie = raa;
    sidsteSamtykke = laesSamtykke();
  }
  return sidsteSamtykke;
}

/** Under servermæssig rendering og hydrering kender vi ikke brugerens valg. */
export function samtykkeServerSnapshot(): null {
  return null;
}

/** true først efter hydrering — bruges til ikke at vise banneret i server-HTML. */
export const ER_HYDRERET = () => true;
export const ER_IKKE_HYDRERET = () => false;
