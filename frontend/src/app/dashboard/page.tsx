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
  const [showHidden, setShowHidden] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  /** Alle Batches vom Server laden (ohne clientseitige Filter — für Vollständigkeit) */
  const load = useCallback(async () => {
    try {
      setError(null);
      // Ausgeblendete werden immer mitgeladen (Anzahl für den Schalter); angezeigt nur auf Wunsch.
      const data = await importsApi.list({ include_hidden: true });
      setBatches(data);
      // Auswahl um nicht mehr vorhandene Imports bereinigen (Auto-Refresh, Löschen)
      setSelected((prev) => {
        const ids = new Set(data.map((b) => b.id));
        const next = new Set(Array.from(prev).filter((id) => ids.has(id)));
        return next.size === prev.size ? prev : next;
      });
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
      if (batch.hidden_at && !showHidden) return false;

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
  }, [batches, filters, showHidden]);

  /** Alle eindeutigen Jahre aus den vorhandenen Batches (für Jahres-Filter) */
  const availableYears = useMemo(() => {
    const years = new Set(batches.map((b) => b.year));
    return Array.from(years).sort((a, b) => b - a); // Absteigend
  }, [batches]);

  const hiddenCount = batches.filter((b) => b.hidden_at).length;
  const selectedBatches = batches.filter((b) => selected.has(b.id));
  const selectedHidden = selectedBatches.filter((b) => b.hidden_at).length;

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleSelectAll() {
    const visible = filteredBatches.map((b) => b.id);
    setSelected((prev) => (visible.every((id) => prev.has(id)) ? new Set() : new Set(visible)));
  }

  /** Imports aus-/einblenden (Auswahl oder einzelner Import) */
  async function setHidden(ids: number[], hidden: boolean) {
    setActionMsg(null);
    try {
      const r = await importsApi.setHidden(ids, hidden);
      setActionMsg(
        `${r.updated} Import${r.updated !== 1 ? "s" : ""} ${hidden ? "ausgeblendet" : "eingeblendet"}.` +
        (hidden ? " Rückgängig: Ausgeblendete anzeigen, dann Einblenden." : ""),
      );
      setSelected(new Set());
      await load();
    } catch {
      setError("Aus-/Einblenden fehlgeschlagen");
    }
  }

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
          {filteredBatches.length} von {batches.length - (showHidden ? 0 : hiddenCount)} Import
          {batches.length - (showHidden ? 0 : hiddenCount) !== 1 ? "s" : ""}
        </span>
        <div className="flex items-center gap-4">
          {hiddenCount > 0 && (
            <label className="flex items-center gap-1.5 text-xs text-gray-600">
              <input
                type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)}
                className="rounded border-gray-300 text-blue-600"
              />
              Ausgeblendete anzeigen ({hiddenCount})
            </label>
          )}
          <button
            onClick={load}
            className="text-xs text-blue-600 hover:underline"
          >
            Aktualisieren
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700" data-testid="action-msg">
          {actionMsg}
        </div>
      )}

      {/* Aktionsleiste bei Auswahl */}
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5" data-testid="selection-bar">
          <span className="text-sm font-medium text-blue-800">
            {selected.size} Import{selected.size !== 1 ? "s" : ""} ausgewählt
          </span>
          <a
            href={importsApi.exportUrl(Array.from(selected))}
            download
            className="rounded border border-emerald-600 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700 hover:bg-emerald-100"
          >
            ↓ Excel exportieren{selected.size > 1 ? " (eine Datei)" : ""}
          </a>
          {selectedHidden < selected.size && (
            <button
              onClick={() => setHidden(selectedBatches.filter((b) => !b.hidden_at).map((b) => b.id), true)}
              className="rounded border border-gray-300 bg-white px-3 py-1 text-sm text-gray-700 hover:bg-gray-50"
            >
              Ausblenden
            </button>
          )}
          {selectedHidden > 0 && (
            <button
              onClick={() => setHidden(selectedBatches.filter((b) => b.hidden_at).map((b) => b.id), false)}
              className="rounded border border-gray-300 bg-white px-3 py-1 text-sm text-gray-700 hover:bg-gray-50"
            >
              Einblenden
            </button>
          )}
          <button onClick={() => setSelected(new Set())} className="ml-auto text-xs text-blue-700 hover:underline">
            Auswahl aufheben
          </button>
        </div>
      )}

      {/* Lade- und Fehlerzustand */}
      {loading && batches.length === 0 && (
        <p className="text-sm text-gray-500">Lade...</p>
      )}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Batch-Tabelle */}
      <BatchTable
        batches={filteredBatches}
        onDeleted={(id) => setBatches((prev) => prev.filter((b) => b.id !== id))}
        selectedIds={selected}
        onToggleSelect={toggleSelect}
        onToggleSelectAll={toggleSelectAll}
        onSetHidden={(id, hidden) => setHidden([id], hidden)}
      />
    </div>
  );
}
