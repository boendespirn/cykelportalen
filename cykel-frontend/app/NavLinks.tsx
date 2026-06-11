"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import SearchBar from "./SearchBar";

const links = [
  { href: "/races", label: "Løb" },
  { href: "/teams", label: "Hold" },
  { href: "/riders", label: "Ryttere" },
  { href: "/nyheder", label: "Nyheder" },
  { href: "/kontakt", label: "Kontakt" },
];

export default function NavLinks() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setOpen(false); }, [pathname]);

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

  const activeLink = links.find(({ href }) => pathname.startsWith(href));

  return (
    <>
      {/* Desktop */}
      <div className="hidden md:flex items-center gap-5">
        <div className="flex gap-1">
          {links.map(({ href, label }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className="relative px-3 py-1.5 text-sm transition-colors duration-150 rounded-md group"
                style={{ color: active ? "var(--foreground)" : "var(--text-2)" }}
              >
                <span className="group-hover:text-white transition-colors duration-150">{label}</span>
                {active && (
                  <span
                    className="absolute bottom-0 left-3 right-3 h-[2px] rounded-full"
                    style={{ background: "var(--accent)" }}
                  />
                )}
              </Link>
            );
          })}
        </div>
        <div style={{ width: "1px", height: "16px", background: "var(--border-bright)", flexShrink: 0 }} />
        <SearchBar />
      </div>

      {/* Mobile */}
      <div className="flex items-center gap-3 md:hidden">
        <SearchBar />
        <div ref={menuRef} className="relative">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-1.5 text-sm py-1 transition-colors duration-150"
            style={{ color: "var(--text-2)" }}
            aria-expanded={open}
            aria-haspopup="true"
          >
            <span>{activeLink?.label ?? "Menu"}</span>
            <svg
              className={`w-3.5 h-3.5 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {open && (
            <div
              className="absolute right-0 top-full mt-2 w-44 rounded-xl shadow-2xl py-1.5 z-30"
              style={{ border: "1px solid var(--border-bright)", background: "var(--surface-2)" }}
            >
              {links.map(({ href, label }) => {
                const active = pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    className="flex items-center justify-between px-4 py-2.5 text-sm transition-colors duration-100 hover:text-white"
                    style={{ color: active ? "var(--foreground)" : "var(--text-2)" }}
                  >
                    {label}
                    {active && (
                      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: "var(--accent)" }} />
                    )}
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
