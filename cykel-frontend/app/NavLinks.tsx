"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useRef } from "react";

const links = [
  { href: "/", label: "Løb" },
  { href: "/teams", label: "Hold" },
  { href: "/riders", label: "Ryttere" },
  { href: "/nyheder", label: "Nyheder" },
  { href: "/kontakt", label: "Kontakt" },
];

export default function NavLinks() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Luk dropdown ved navigation
  useEffect(() => { setOpen(false); }, [pathname]);

  // Luk dropdown ved klik udenfor
  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const activeLink = links.find(({ href }) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href)
  );

  return (
    <>
      {/* Desktop: uændret vandret menu */}
      <div className="hidden md:flex gap-7 text-sm">
        {links.map(({ href, label }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`transition-colors ${
                active ? "text-white font-medium" : "text-slate-500 hover:text-slate-200"
              }`}
            >
              {label}
              {active && <span className="ml-1 text-emerald-400">·</span>}
            </Link>
          );
        })}
      </div>

      {/* Mobil: dropdown */}
      <div ref={menuRef} className="relative md:hidden">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1.5 text-sm text-slate-300 hover:text-white transition-colors py-1"
          aria-expanded={open}
          aria-haspopup="true"
        >
          <span>{activeLink?.label ?? "Menu"}</span>
          <svg
            className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {open && (
          <div className="absolute right-0 top-full mt-2 w-40 rounded-xl border border-slate-700 bg-slate-900 shadow-xl py-1 z-30">
            {links.map(({ href, label }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setOpen(false)}
                  className={`block px-4 py-2.5 text-sm transition-colors ${
                    active
                      ? "text-white font-medium"
                      : "text-slate-400 hover:text-white hover:bg-slate-800/60"
                  }`}
                >
                  {label}
                  {active && <span className="ml-1 text-emerald-400">·</span>}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
