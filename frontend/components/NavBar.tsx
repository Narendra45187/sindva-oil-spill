"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/weather", label: "Weather" },
  { href: "/alerts", label: "Alerts" },
  { href: "/reports", label: "Reports" },
  { href: "/investigation", label: "Investigation" },
  { href: "/traffic", label: "Live Traffic" },
] as const;

const COMING_SOON_ITEMS: readonly string[] = [];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-1 border-b border-line bg-panel/60 px-6 backdrop-blur-sm">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`border-b-2 px-3 py-2.5 text-xs font-semibold uppercase tracking-wide transition ${
              active
                ? "border-accent text-accent"
                : "border-transparent text-slate-400 hover:border-line hover:text-slate-200"
            }`}
          >
            {item.label}
          </Link>
        );
      })}

      {COMING_SOON_ITEMS.map((label) => (
        <span
          key={label}
          title="Coming soon"
          className="flex cursor-not-allowed items-center gap-1.5 border-b-2 border-transparent px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-600"
        >
          {label}
          <span className="rounded-full border border-line bg-white/[0.02] px-1.5 py-0.5 text-[9px] normal-case tracking-normal text-slate-600">
            Soon
          </span>
        </span>
      ))}
    </nav>
  );
}
