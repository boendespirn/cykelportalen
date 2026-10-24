import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { fastAdresseFor, udgaveFor } from "@/lib/evergreen";

/** Faste adresser for den aktuelle udgave af årlige løb (se lib/evergreen.ts).
 *  /tour-de-france[/stage/N] vises med den aktuelle udgaves indhold, og den
 *  udgaves årstals-adresse sender videre dertil, så indholdet kun findes ét
 *  sted. Viderestillingen er midlertidig (307): adressen bliver arkivside,
 *  når næste udgave overtager den faste adresse. */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const [, foerste, ...rest] = pathname.split("/");
  const resten = rest.length ? `/${rest.join("/")}` : "";

  const udgave = udgaveFor(foerste);
  if (udgave) {
    const url = request.nextUrl.clone();
    url.pathname = `/${udgave}${resten}`;
    return NextResponse.rewrite(url);
  }

  const fast = fastAdresseFor(foerste);
  if (fast) {
    const url = request.nextUrl.clone();
    url.pathname = `/${fast}${resten}`;
    return NextResponse.redirect(url, 307);
  }

  return NextResponse.next();
}

export const config = {
  // Kun løbs- og etapeadresser. Funktionen er et opslag i et lille objekt, så
  // de øvrige sider på ét segment (/races, /nyheder …) koster intet.
  matcher: ["/:slug", "/:slug/stage/:n"],
};
