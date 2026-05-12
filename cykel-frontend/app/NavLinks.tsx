"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Løb" },
  { href: "/teams", label: "Hold" },
  { href: "/riders", label: "Ryttere" },
];

export default function NavLinks() {
  const pathname = usePathname();
  return (
    <div className="flex gap-7 text-sm">
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
  );
}
