/**
 * Ét sted for de oplysninger, der juridisk identificerer afsenderen bag
 * klassementet.dk. Cookiepolitik, privatlivspolitik og vilkår læser alle
 * herfra, så identiteten står ens tre steder og kun skal rettes ét sted.
 *
 * Bemærk om anonymitet: siden er skrevet, så der aldrig optræder et
 * personnavn — afsenderen er "Klassementet" som tjeneste. Det dækker
 * GDPR'ens krav om, at den dataansvarlige kan identificeres og kontaktes.
 * E-handelslovens § 7 kræver derudover et registreringsnummer af
 * erhvervsdrivende tjenesteydere: udfyld `cvr` og `adresse` nedenfor, så
 * snart siden drives i selskabsform, og felterne dukker automatisk op på
 * alle tre sider.
 *
 * Der står med vilje INGEN e-mailadresse nogen steder på siden. Al kontakt
 * går gennem formularen på /kontakt, og modtageradressen findes kun i
 * servermiljøet (se app/api/kontakt/route.ts) — aldrig i noget, browseren
 * får at se. En adresse i en politiktekst ville gøre hele den øvelse
 * forgæves, så henvis til KONTAKT_STI frem for at skrive en adresse.
 */
export const UDGIVER = {
  navn: "Klassementet",
  domaene: "klassementet.dk",
  url: "https://klassementet.dk",

  /** Sæt til fx "12345678" når der er et CVR-nummer at oplyse. */
  cvr: null as string | null,
  /** Sæt til den registrerede virksomhedsadresse, når den findes. */
  adresse: null as string | null,
} as const;

/** Eneste kontaktvej til os. Brug den frem for at skrive en adresse i teksten. */
export const KONTAKT_STI = "/kontakt";

/** Dato for seneste indholdsmæssige revision af de juridiske sider. */
export const POLITIK_OPDATERET = "17. oktober 2026";

/** Formateret som dansk dato, fx "17. oktober 2026". */
export function visDato(iso: string): string {
  return new Date(iso).toLocaleDateString("da-DK", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
