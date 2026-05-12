"use client";
import { useState } from "react";
import Link from "next/link";

type DnfEntry = {
  status: string;
  dnf_stage_number: number | null;
  bib_number: number | null;
  riders: { name: string; slug: string; nationality: string | null } | null;
  teams: { name: string; slug: string } | null;
};

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5))
    .join("");
}

const STATUS_LABEL: Record<string, string> = {
  dnf: "DNF",
  dns: "DNS",
  dsq: "DSQ",
};
const STATUS_COLOR: Record<string, string> = {
  dnf: "text-red-400 bg-red-500/10 border-red-500/20",
  dns: "text-slate-400 bg-slate-500/10 border-slate-500/20",
  dsq: "text-orange-400 bg-orange-500/10 border-orange-500/20",
};

export default function DnfSection({ entries }: { entries: DnfEntry[] }) {
  const [open, setOpen] = useState(false);

  return (
    <section className="mb-10">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-red-400 transition-colors"
      >
        <svg
          className={`w-4 h-4 transition-transform duration-150 ${open ? "rotate-90" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span className="uppercase tracking-[0.15em] text-xs">
          Udgåede ryttere ({entries.length})
        </span>
      </button>

      {open && (
        <div className="mt-3 rounded-xl border border-slate-800 overflow-hidden animate-in fade-in duration-150">
          <table className="w-full text-sm">
            <tbody>
              {entries.map((entry, i) => {
                const rider = entry.riders;
                if (!rider) return null;
                const statusKey = entry.status?.toLowerCase() ?? "dnf";
                return (
                  <tr key={i} className="border-b border-slate-800/40 hover:bg-slate-900/40 transition-colors">
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border ${STATUS_COLOR[statusKey] ?? "text-slate-400"}`}>
                        {STATUS_LABEL[statusKey] ?? statusKey.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <Link href={`/riders/${rider.slug}`} className="flex items-center gap-2 hover:text-red-400 transition-colors">
                        <span>{flagEmoji(rider.nationality)}</span>
                        <span className="text-slate-300">{rider.name}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-slate-600 text-xs hidden sm:table-cell">
                      {entry.teams?.name ?? ""}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600 text-xs text-right">
                      {entry.dnf_stage_number ? `Etape ${entry.dnf_stage_number}` : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
