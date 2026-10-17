/**
 * Modtager kontaktformularen og sender henvendelsen videre til Telegram.
 *
 * Hvorfor Telegram og ikke mail: ejeren får i forvejen driftsbeskeder der
 * (se notify.py), så kanalen er allerede i brug og afprøvet. Samtidig
 * slipper vi for et afsenderdomæne, der skal verificeres med DNS, før en
 * henvendelse overhovedet kan komme frem.
 *
 * Hele pointen med at afsende her — og ikke med en mailto-adresse i
 * frontenden — er, at modtageren aldrig forlader serveren. Browseren får kun
 * at vide, om det lykkedes. Derfor må hverken token eller chat-id optræde i
 * noget, der sendes retur.
 *
 * Nødvendige miljøvariabler (sat i Vercel, ikke i koden):
 *   TELEGRAM_BOT_TOKEN — samme bot som driftsbeskederne bruger
 *   TELEGRAM_CHAT_ID   — chatten henvendelser skal lande i
 */

export const runtime = "nodejs";
// Formularen må aldrig besvares fra en cache — hver indsendelse er ny.
export const dynamic = "force-dynamic";

const EMNER: Record<string, string> = {
  advertorial: "Advertorial / blogindlæg",
  annonce: "Annoncering og sponsorater",
  nyheder: "Nyhedstip",
  andet: "Andet",
};

const MAKS = { navn: 120, email: 160, firma: 160, besked: 4000 };

// Telegram afviser beskeder over 4096 tegn. Vi klipper i stedet for at tabe
// henvendelsen helt — en afkortet lead er uendeligt meget bedre end ingen.
const TELEGRAM_MAKS = 4000;

type Fejl = { felt: string; besked: string };

function rens(vaerdi: unknown, maks: number): string {
  return typeof vaerdi === "string" ? vaerdi.trim().slice(0, maks) : "";
}

/** Felter, der skal stå på én linje, må ikke kunne bryde beskedens opbygning. */
function enLinje(vaerdi: string): string {
  return vaerdi.replace(/[\r\n]+/g, " ");
}

export async function POST(request: Request) {
  let krop: Record<string, unknown>;
  try {
    krop = await request.json();
  } catch {
    return Response.json({ fejl: "Ugyldig forespørgsel." }, { status: 400 });
  }

  // Skjult felt, som kun en bot udfylder. Vi svarer 200, så botten ikke
  // lærer noget af afvisningen — men sender ingenting videre.
  if (rens(krop.website, 100)) {
    return Response.json({ ok: true });
  }

  const emne = rens(krop.type, 40);
  const navn = enLinje(rens(krop.name, MAKS.navn));
  const email = enLinje(rens(krop.email, MAKS.email));
  const firma = enLinje(rens(krop.company, MAKS.firma));
  const besked = rens(krop.message, MAKS.besked);

  const fejl: Fejl[] = [];
  if (!EMNER[emne]) fejl.push({ felt: "type", besked: "Vælg hvad henvendelsen drejer sig om." });
  if (!navn) fejl.push({ felt: "name", besked: "Skriv dit navn." });
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
    fejl.push({ felt: "email", besked: "Skriv en gyldig e-mailadresse." });
  if (besked.length < 10)
    fejl.push({ felt: "message", besked: "Skriv lidt mere om, hvad det drejer sig om." });

  if (fejl.length > 0) {
    return Response.json({ fejl: "Nogle felter mangler.", felter: fejl }, { status: 400 });
  }

  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    // Fejler opsætningen, skal det være højlydt i loggen og ærligt over for
    // afsenderen. En formular, der siger "tak" uden at sende, er værre end
    // en, der siger fra: så ved brugeren i det mindste at prøve igen.
    console.error("[kontakt] mangler TELEGRAM_BOT_TOKEN eller TELEGRAM_CHAT_ID");
    return Response.json(
      { fejl: "Vi kan ikke modtage beskeder lige nu. Prøv igen senere." },
      { status: 503 },
    );
  }

  // Ren tekst uden parse_mode: så kan hverken < > * _ eller andet fra en
  // fremmed besked ødelægge formateringen eller blive tolket som opmærkning.
  const tekst = [
    "Ny henvendelse fra kontaktformularen",
    "",
    `Emne:    ${EMNER[emne]}`,
    `Navn:    ${navn}`,
    `E-mail:  ${email}`,
    firma ? `Firma:   ${firma}` : null,
    "",
    besked,
  ]
    .filter((l): l is string => l !== null)
    .join("\n")
    .slice(0, TELEGRAM_MAKS);

  try {
    const svar = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: tekst,
        disable_web_page_preview: true,
      }),
    });

    if (!svar.ok) {
      // Telegrams svar kan indeholde chat-id'et — det logges, men
      // returneres aldrig til browseren.
      console.error(
        `[kontakt] Telegram svarede ${svar.status}: ${(await svar.text()).slice(0, 300)}`,
      );
      return Response.json(
        { fejl: "Beskeden kunne ikke sendes. Prøv igen om lidt." },
        { status: 502 },
      );
    }
  } catch (e) {
    console.error(`[kontakt] kunne ikke nå Telegram: ${e instanceof Error ? e.message : e}`);
    return Response.json(
      { fejl: "Beskeden kunne ikke sendes. Prøv igen om lidt." },
      { status: 502 },
    );
  }

  return Response.json({ ok: true });
}
