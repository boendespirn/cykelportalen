import type { NextConfig } from "next";

// Rytterprofiler, der blev lagt sammen 2026-10-29: KNWU-dubletten ("Joran
// Wyseure") blev slettet til fordel for arrangør-PDF'ens post ("WYSEURE
// Joran"). Den gamle adresse viderestilles permanent, så links og Googles
// indeks lander på den profil, der nu har rytterens resultater.
const SAMMENLAGTE_RYTTERE: Record<string, string> = {
  "mees-hendrikx": "hendrikx-mees",
  "cas-timmermans": "timmermans-cas",
  "wout-janssen": "janssen-wout",
  "thomas-mein": "mein-thomas",
  "ryan-kamp": "kamp-ryan",
  "pim-ronhaar": "ronhaar-pim",
  "mats-vanden-eynde": "vanden-eynde-mats",
  "senn-bossaerts": "bossaerts-senn",
  "arthur-janssens": "janssens-arthur",
  "lars-corsus": "corsus-lars",
  "loic-vanlaere": "vanlaere-loic",
  "niels-vandeputte": "vandeputte-niels",
  "laurens-sweeck": "sweeck-laurens",
  "joran-wyseure": "wyseure-joran",
  "arthur-soontjens": "soontjens-arthur",
  "dean-harvey": "harvey-dean",
  "felipe-orts-lloret": "orts-lloret-felipe",
  "joris-nieuwenhuis": "nieuwenhuis-joris",
};

const nextConfig: NextConfig = {
  async redirects() {
    return Object.entries(SAMMENLAGTE_RYTTERE).map(([gammel, ny]) => ({
      source: `/riders/${gammel}`,
      destination: `/riders/${ny}`,
      permanent: true,
    }));
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "rywfqirgkbdjqdyggybb.supabase.co" },
      { protocol: "https", hostname: "www.procyclingstats.com" },
      { protocol: "https", hostname: "image.climbfinder.com" },
    ],
    formats: ["image/avif", "image/webp"],
  },
};

export default nextConfig;
