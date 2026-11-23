"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/scheduler", label: "Scheduler" },
  { href: "/data", label: "Data" },
  { href: "/uncertainty", label: "Uncertainty" },
  { href: "/simulator", label: "Simulator" },
  { href: "/policies", label: "Policies" },
  { href: "/experiments", label: "Experiments" },
  { href: "/roadmap", label: "Roadmap" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="nav">
      {LINKS.map((link) => {
        const active =
          link.href === "/"
            ? pathname === "/"
            : pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link key={link.href} href={link.href} data-active={active}>
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
