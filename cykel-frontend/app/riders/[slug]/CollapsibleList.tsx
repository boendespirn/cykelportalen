"use client";

import { useState } from "react";

export default function CollapsibleList({
  items,
  initialCount = 8,
  className = "space-y-1.5",
}: {
  items: React.ReactNode[];
  initialCount?: number;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const hidden = items.length - initialCount;
  const visible = expanded ? items : items.slice(0, initialCount);

  return (
    <>
      <div className={className}>{visible}</div>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="mt-3 w-full text-center text-xs font-medium text-slate-500 hover:text-emerald-400 transition-colors py-2 rounded-lg border border-slate-800 hover:border-emerald-500/30"
        >
          {expanded ? "Vis færre" : `Vis alle (${items.length})`}
        </button>
      )}
    </>
  );
}
