"use client";

import { useState } from "react";

type GradientSection = { km: number; gradient: number };

type Climb = {
  id: string;
  name: string;
  km_from_start: number | null;
  length_km: number | null;
  elevation_m: number | null;
  avg_gradient: number | null;
  max_gradient: number | null;
  gradient_sections: GradientSection[] | null;
  profile_image_url: string | null;
};

function avg4kmBuckets(sections: GradientSection[]): { km: number; gradient: number }[] {
  if (sections.length === 0) return [];
  const BUCKET = 4;
  const maxKm = sections[sections.length - 1].km;
  const result: { km: number; gradient: number }[] = [];
  for (let start = 0; start <= maxKm; start += BUCKET) {
    const inRange = sections.filter(s => s.km >= start && s.km < start + BUCKET);
    if (inRange.length > 0) {
      const avg = inRange.reduce((sum, s) => sum + s.gradient, 0) / inRange.length;
      result.push({ km: start + BUCKET / 2, gradient: parseFloat(avg.toFixed(1)) });
    }
  }
  return result;
}

function curvePath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return "";
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const cpx = (prev.x + curr.x) / 2;
    d += ` C ${cpx} ${prev.y} ${cpx} ${curr.y} ${curr.x} ${curr.y}`;
  }
  return d;
}

type Props = {
  climbs: Climb[];
  elevationImageUrl: string | null;
};

// Gradient → farve (grøn <6%, gul 6-9%, rød >9%, lilla >13%)
function gradientColor(g: number): string {
  if (g < 4)  return "#10b981"; // emerald-500
  if (g < 6)  return "#84cc16"; // lime-500
  if (g < 9)  return "#eab308"; // yellow-500
  if (g < 13) return "#f97316"; // orange-500
  return "#ef4444";             // red-500
}

function GradientLegend() {
  return (
    <div className="flex items-center gap-3 text-[10px] text-slate-500 flex-wrap">
      {[
        { color: "#10b981", label: "<4%" },
        { color: "#84cc16", label: "4-6%" },
        { color: "#eab308", label: "6-9%" },
        { color: "#f97316", label: "9-13%" },
        { color: "#ef4444", label: ">13%" },
      ].map(({ color, label }) => (
        <span key={label} className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

function ClimbSvg({ climb }: { climb: Climb }) {
  const sections = climb.gradient_sections ?? [];
  if (sections.length === 0) return null;

  const W = 600;
  const H = 140;
  const PAD_LEFT = 32;
  const PAD_BOTTOM = 24;
  const PAD_TOP = 10;
  const PAD_RIGHT = 8;

  const innerW = W - PAD_LEFT - PAD_RIGHT;
  const innerH = H - PAD_BOTTOM - PAD_TOP;

  const maxGrad = Math.max(...sections.map((s) => s.gradient), 1);
  const totalKm = sections.length > 0 ? sections[sections.length - 1].km + 0.5 : 1;

  // Byg SVG path som area chart
  const points = sections.map((s, i) => {
    const x = PAD_LEFT + (s.km / totalKm) * innerW;
    const y = PAD_TOP + innerH - (s.gradient / (maxGrad * 1.1)) * innerH;
    return { x, y, g: s.gradient, km: s.km };
  });

  // Area path
  const pathD = points.length > 0
    ? [
        `M ${points[0].x} ${PAD_TOP + innerH}`,
        ...points.map((p) => `L ${p.x} ${p.y}`),
        `L ${points[points.length - 1].x} ${PAD_TOP + innerH}`,
        "Z",
      ].join(" ")
    : "";

  // Bar chart (én bar per sektion, farvekodet)
  const barW = innerW / sections.length;

  // Y-akse labels
  const yLabels = [0, Math.round(maxGrad * 0.5), Math.round(maxGrad)];

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ minWidth: "300px", maxHeight: "160px" }}
      >
        {/* Grid lines */}
        {yLabels.map((val) => {
          const y = PAD_TOP + innerH - (val / (maxGrad * 1.1)) * innerH;
          return (
            <g key={val}>
              <line x1={PAD_LEFT} y1={y} x2={W - PAD_RIGHT} y2={y}
                stroke="#334155" strokeWidth={0.5} strokeDasharray="3 3" />
              <text x={PAD_LEFT - 3} y={y + 4} textAnchor="end"
                fontSize={8} fill="#64748b">{val}%</text>
            </g>
          );
        })}

        {/* Farvelagte bars */}
        {sections.map((s, i) => {
          const x = PAD_LEFT + (s.km / totalKm) * innerW;
          const barH = (s.gradient / (maxGrad * 1.1)) * innerH;
          const y = PAD_TOP + innerH - barH;
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={Math.max(barW - 0.5, 1)}
              height={barH}
              fill={gradientColor(s.gradient)}
              opacity={0.85}
            />
          );
        })}

        {/* X-akse */}
        <line x1={PAD_LEFT} y1={PAD_TOP + innerH} x2={W - PAD_RIGHT} y2={PAD_TOP + innerH}
          stroke="#475569" strokeWidth={1} />

        {/* X labels (km) */}
        {sections
          .filter((_, i) => i % Math.max(1, Math.floor(sections.length / 6)) === 0)
          .map((s) => {
            const x = PAD_LEFT + (s.km / totalKm) * innerW;
            return (
              <text key={s.km} x={x} y={H - 8} textAnchor="middle"
                fontSize={8} fill="#64748b">{s.km} km</text>
            );
          })}

        {/* Smooth 4 km-gennemsnit kurve */}
        {(() => {
          const buckets = avg4kmBuckets(sections);
          if (buckets.length < 2) return null;
          const pts = buckets.map(b => ({
            x: PAD_LEFT + (b.km / totalKm) * innerW,
            y: PAD_TOP + innerH - (b.gradient / (maxGrad * 1.1)) * innerH,
            g: b.gradient,
          }));
          const line = curvePath(pts);
          return (
            <g>
              <path d={line} fill="none" stroke="white" strokeWidth={1.8}
                opacity={0.85} strokeLinecap="round" strokeLinejoin="round" />
              {pts.map((p, i) => (
                <g key={i}>
                  <circle cx={p.x} cy={p.y} r={2.5} fill="white" opacity={0.9} />
                  <text x={p.x} y={p.y - 5} textAnchor="middle"
                    fontSize={7} fill="white" opacity={0.75} fontWeight="500">
                    {p.g}%
                  </text>
                </g>
              ))}
            </g>
          );
        })()}

        {/* Toppen — max gradient label */}
        {climb.max_gradient && (
          <text
            x={W - PAD_RIGHT}
            y={PAD_TOP + 8}
            textAnchor="end"
            fontSize={9}
            fill="#f97316"
            fontWeight="bold"
          >
            max {climb.max_gradient}%
          </text>
        )}
      </svg>
    </div>
  );
}

export default function ClimbProfile({ climbs, elevationImageUrl }: Props) {
  const [activeIdx, setActiveIdx] = useState<number>(-1); // -1 = fuld profil

  if (!elevationImageUrl && climbs.length === 0) return null;

  const activeClimb = activeIdx >= 0 ? climbs[activeIdx] ?? null : null;

  return (
    <div className="mb-6 rounded-xl overflow-hidden border border-slate-800 bg-slate-950">
      {/* Tab navigation */}
      {climbs.length > 0 && (
        <div className="flex flex-wrap gap-1 p-2 border-b border-slate-800 bg-slate-900/60">
          {elevationImageUrl && (
            <button
              onClick={() => setActiveIdx(-1)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeIdx === -1
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
              }`}
            >
              Fuld profil
            </button>
          )}
          {climbs.map((c, i) => (
            <button
              key={i}
              onClick={() => setActiveIdx(i)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeIdx === i
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
              }`}
            >
              ⛰ {c.name}
            </button>
          ))}
        </div>
      )}

      {/* Fuld profil — klik åbner native billedvisning (roterbar på iPhone) */}
      {activeIdx === -1 && elevationImageUrl && (
        <a href={elevationImageUrl} target="_blank" rel="noopener noreferrer" className="block">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={elevationImageUrl}
            alt="Højdeprofil"
            className="w-full"
          />
        </a>
      )}

      {/* Enkelt stigning */}
      {activeIdx >= 0 && activeClimb && (
        <div className="p-4">
          {/* Klatre-navn */}
          <p className="text-slate-200 font-semibold text-sm mb-3">{activeClimb.name}</p>
          {/* Klatre-stats */}
          <div className="flex flex-wrap gap-4 mb-4 text-sm">
            {activeClimb.length_km != null && (
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Længde</p>
                <p className="text-slate-200 font-mono font-medium">{activeClimb.length_km} km</p>
              </div>
            )}
            {activeClimb.elevation_m != null && (
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Højdemeter</p>
                <p className="text-red-400 font-mono font-medium">+{activeClimb.elevation_m} m</p>
              </div>
            )}
            {activeClimb.avg_gradient != null && (
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Gns. stigning</p>
                <p className="text-orange-400 font-mono font-medium">{activeClimb.avg_gradient}%</p>
              </div>
            )}
            {activeClimb.max_gradient != null && (
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Max stigning</p>
                <p className="text-red-400 font-mono font-bold">{activeClimb.max_gradient}%</p>
              </div>
            )}
            {activeClimb.km_from_start != null && (
              <div>
                <p className="text-xs text-slate-500 mb-0.5">Starter ved</p>
                <p className="text-slate-400 font-mono">km {activeClimb.km_from_start}</p>
              </div>
            )}
          </div>

          {/* Gradient visualisering — ClimbFinder-billede foretrækkes */}
          {activeClimb.profile_image_url ? (
            <a href={activeClimb.profile_image_url} target="_blank" rel="noopener noreferrer" className="block">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={activeClimb.profile_image_url}
                alt={activeClimb.name}
                className="w-full rounded-lg"
              />
            </a>
          ) : activeClimb.gradient_sections && activeClimb.gradient_sections.length > 0 ? (
            <>
              <ClimbSvg climb={activeClimb} />
              <div className="mt-2">
                <GradientLegend />
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
