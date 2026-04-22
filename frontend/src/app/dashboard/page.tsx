/**
 * Dashboard-Seite (/dashboard)
 *
 * Zeigt eine Übersicht aller Import-Batches mit:
 * - Filterleiste (Firma, Jahr — auch Mehrfachauswahl)
 * - Tabelle aller Batches mit Status und Fortschritt
 * - Auto-Refresh alle 10 Sekunden (für laufende Imports)
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ImportBatch, importsApi } from "@/lib/api";
import BatchTable from "@/components/dashboard/BatchTable";
import FilterBar from "@/components/dashboard/FilterBar";

/** Filter-Zustand */
interface Filters {
  company: string;
  years: number[];
}

export default function DashboardPage() {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ company: "", years: [] });

  /** Alle Batches vom Server laden (ohne clientseitige Filter — für Vollständigkeit) */
  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await importsApi.list();
      setBatches(data);
    } catch {
      setError("Fehler beim Laden der Imports");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Auto-Refresh alle 10 Sekunden (für laufende Imports)
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [load]);

  /**
   * Clientseitige Filterung der Batches.
   * Alle Batches wurden vollständig geladen — Filter werden lokal angewendet.
   * Für sehr große Datenmengen könnte man auf serverseitige Filter umstellen.
   */
  const filteredBatches = useMemo(() => {
    return batches.filter((batch) => {
      // Firmenname-Filter (Teilstring, Groß-/Kleinschreibung ignorieren)
      if (
        filters.company &&
        !batch.company_name.toLowerCase().includes(filters.company.toLowerCase())
      ) {
        return false;
      }

      // Jahres-Filter (Mehrfachauswahl)
      if (filters.years.length > 0 && !filters.years.includes(batch.year)) {
        return false;
      }

      return true;
    });
  }, [batches, filters]);

  /** Alle eindeutigen Jahre aus den vorhandenen Batches (für Jahres-Filter) */
  const availableYears = useMemo(() => {
    const years = new Set(batches.map((b) => b.year));
    return Array.from(years).sort((a, b) => b - a); // Absteigend
  }, [batches]);

  // Anzahl laufender Imports (für Hinweisanzeige)
  const runningCount = batches.filter((b) => b.status === "running").length;

  return (
    <div className="space-y-6">
      {/* Kopfzeile */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Import-Dashboard</h1>
          {runningCount > 0 && (
            <p className="text-sm text-blue-600">
              {runningCount} Import{runningCount > 1 ? "s" : ""} aktiv — wird alle 10s aktualisiert
            </p>
          )}
        </div>
        <Link
          href="/imports/new"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Neuer Import
        </Link>
      </div>

      {/* Filterleiste */}
      <FilterBar
        availableYears={availableYears}
        filters={filters}
        onChange={setFilters}
      />

      {/* Statuszeile */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          {filteredBatches.length} von {batches.length} Import
          {batches.length !== 1 ? "s" : ""}
        </span>
        <button
          onClick={load}
          className="text-xs text-blue-600 hover:underline"
        >
          Aktualisieren
        </button>
      </div>

      {/* Lade- und Fehlerzustand */}
      {loading && batches.length === 0 && (
        <p className="text-sm text-gray-500">Lade...</p>
      )}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Batch-Tabelle */}
      <BatchTable
        batches={filteredBatches}
        onDeleted={(id) => setBatches((prev) => prev.filter((b) => b.id !== id))}
      />
    </div>
  );
}
