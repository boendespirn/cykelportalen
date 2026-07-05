"use client";
import { useState } from "react";

type Props = {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  accentColor?: string;
  children: React.ReactNode;
};

export default function Disclosure({
  title,
  subtitle,
  defaultOpen = false,
  accentColor = "text-emerald-400",
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden h-fit">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between gap-3 px-5 py-3 bg-slate-900/60 text-left ${
          open ? "border-b border-slate-800" : ""
        }`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-xs uppercase tracking-[0.2em] font-medium ${accentColor}`}>
            {title}
          </span>
          {subtitle && <span className="text-xs text-slate-600 flex-shrink-0">{subtitle}</span>}
        </div>
        <svg
          className={`w-4 h-4 text-slate-500 transition-transform duration-200 flex-shrink-0 ${
            open ? "rotate-180" : ""
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div>{children}</div>}
    </div>
  );
}
