/**
 * Navigationsleiste der Anwendung.
 *
 * Zeigt Links zu den Hauptbereichen:
 * - Dashboard: Übersicht aller Imports
 * - Neuer Import: Import-Formular starten
 * - KI-Einstellungen: KI-Konfigurationen verwalten
 * - Bildeinstellungen: PDF-zu-Bild-Konvertierungseinstellungen
 *
 * Markiert den aktuell aktiven Link visuell (usePathname).
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/** Navigationspunkte der Anwendung */
const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/belege", label: "Belege" },
  { href: "/imports/new", label: "Neuer Import" },
  { href: "/lieferanten", label: "Lieferanten" },
  { href: "/settings/ai", label: "KI-Einstellungen" },
  { href: "/settings/prompts", label: "Systemprompts" },
  { href: "/settings/image", label: "Bildeinstellungen" },
  { href: "/settings/processing", label: "Einstellungen" },
  { href: "/logs", label: "Logs" },
];

export default function Nav() {
  const pathname = usePathname();
  const [jsOk, setJsOk] = useState(false);
  useEffect(() => { setJsOk(true); }, []);

  return (
    <nav className="border-b bg-white shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        {/* Logo / App-Titel */}
        <Link href="/dashboard" className="text-lg font-bold tracking-tight text-blue-700">
          Rechnungsanalyse
          <span className={`ml-2 text-xs font-normal px-1.5 py-0.5 rounded ${jsOk ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
            {jsOk ? "JS ✓" : "JS ✗"}
          </span>
        </Link>

        {/* Navigationslinks */}
        <ul className="flex gap-1">
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={[
                    "rounded px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
                  ].join(" ")}
                >
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}
