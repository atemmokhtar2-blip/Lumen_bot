"use client";

import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/runs", label: "Runs" },
  { href: "/agents", label: "Agents" },
  { href: "/diff", label: "Diff" },
];

export function Nav() {
  const path = usePathname() || "/";
  return (
    <header className="nav">
      <span className="nav-brand">Lumen</span>
      {LINKS.map((l) => {
        const active =
          l.href === "/"
            ? path === "/"
            : path === l.href || path.startsWith(l.href + "/");
        return (
          <a key={l.href} href={l.href} className={`nav-link${active ? " active" : ""}`}>
            {l.label}
          </a>
        );
      })}
    </header>
  );
}
