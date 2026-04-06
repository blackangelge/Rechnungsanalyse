"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SystemLog, logsApi } from "@/lib/api";

// ─── Hilfsfunktionen ────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(iso));
}

function LevelBadge({ level }: { level: string }) {
  const styles: Record<string, string> = {
    info: "bg-blue-100 text-blue-700",
    warning: "bg-yellow-100 text-yellow-700",
    error: "bg-red-100 text-red-700",
  };
  const labels: Record<string, string> = {
    info: "Info",
    warning: "Warnung",
    error: "Fehler",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[level] ?? "bg-gray-100 text-gray-600"}`}>
      {labels[level] ?? level}
    </span>
  );
}

function CategoryBadge({ category }: { category: string }) {
  const styles: Record<string, string> = {
    import: "bg-purple-100 text-purple-700",
    ki: "bg-green-100 text-green-700",
  };
  const labels: Record<string, string> = {
    import: "Import",
    ki: "KI-Abfrage",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[category] ?? "bg-gray-100 text-gray-600"}`}>
      {labels[category] ?? category}
    </span>
  );
}

// ─── Hauptkomponente ─────────────────────────────────────────────────────────

export default function LogsPage() {
  const [logs, setLogs] = useState<SystemLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter
  const [filterCategory, setFilterCategory] = useState<string>("");
  const [filterLevel, setFilterLevel] = useState<string>("");
  const [autoRefresh, setAutoRefresh] = useState(false);

  // Bestätigung löschen
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Laden ──────────────────────────────────────────────────────────────

  const loadLogs = useCallback(async (category: string, level: string) => {
    setLoading(true);
    setError(null);
    try {
      const params: { category?: string; level?: string; limit: number } = { limit: 500 };
      if (category) params.category = category;
      if (level) params.level = level;
      const data = await logsApi.list(params);
      setLogs(data);
    } catch (err) {
      setError("Fehler beim Laden der Logs");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLogs(filterCategory, filterLevel);
  }, [loadLogs, filterCategory, filterLevel]);

  // Auto-Refresh
  useEffect(() => {
    if (autoRefresh && !refreshTimerRef.current) {
      refreshTimerRef.current = setInterval(() => {
        loadLogs(filterCategory, filterLevel);
      }, 5000);
    } else if (!autoRefresh && refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [autoRefresh, filterCategory, filterLevel, loadLogs]);

  // ─── Filter ──────────────────────────────────────────────────────────────

  function handleCategoryChange(val: string) {
    setFilterCategory(val);
    setConfirmClear(false);
  }

  function handleLevelChange(val: string) {
    setFilterLevel(val);
    setConfirmClear(false);
  }

  // ─── Löschen ─────────────────────────────────────────────────────────────

  async function handleClear() {
    setClearing(true);
    try {
      const result = await logsApi.clear(filterCategory || undefined);
      setConfirmClear(false);
      await loadLogs(filterCategory, filterLevel);
      setError(null);
    } catch (err) {
      setError("Fehler beim Löschen der Logs");
      console.error(err);
    } finally {
      setClearing(false);
    }
  }

  // ─── Statistiken ─────────────────────────────────────────────────────────

  const countByLevel = {
    info: logs.filter((l) => l.level === "info").length,
    warning: logs.filter((l) => l.level === "warning").length,
    error: logs.filter((l) => l.level === "error").length,
  };

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Logs</h1>

      {/* ── Fehler ─────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700 border border-red-200">
          {error}
        </div>
      )}

      {/* ── Filter + Aktionen ──────────────────────────────────────────── */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border bg-white p-4 shadow-sm">

        {/* Kategorie */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Kategorie</label>
          <select
            value={filterCategory}
            onChange={(e) => handleCategoryChange(e.target.value)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-40"
          >
            <option value="">Alle</option>
            <option value="import">Import</option>
            <option value="ki">KI-Abfragen</option>
          </select>
        </div>

        {/* Level */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Level</label>
          <select
            value={filterLevel}
            onChange={(e) => handleLevelChange(e.target.value)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-36"
          >
            <option value="">Alle Level</option>
            <option value="info">Info</option>
            <option value="warning">Warnung</option>
            <option value="error">Fehler</option>
          </select>
        </div>

        {/* Separator */}
        <div className="h-8 w-px bg-gray-200 mt-auto" />

        {/* Auto-Refresh */}
        <label className="flex cursor-pointer items-center gap-2 mt-auto pb-1.5">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="rounded border-gray-300 text-blue-600"
          />
          <span className="text-sm text-gray-600">Auto-Refresh (5 s)</span>
        </label>

        {/* Manuell neu laden */}
        <button
          onClick={() => loadLogs(filterCategory, filterLevel)}
          disabled={loading}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-50 transition-colors mt-auto"
        >
          {loading ? "Lade..." : "↻ Neu laden"}
        </button>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Löschen */}
        {!confirmClear ? (
          <button
            onClick={() => setConfirmClear(true)}
            className="rounded border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors mt-auto"
          >
            Logs löschen{filterCategory ? ` (${filterCategory === "import" ? "Import" : "KI"})` : " (alle)"}
          </button>
        ) : (
          <div className="flex items-center gap-2 mt-auto">
            <span className="text-sm text-red-600 font-medium">Wirklich löschen?</span>
            <button
              onClick={handleClear}
              disabled={clearing}
              className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {clearing ? "Löschen..." : "Ja, löschen"}
            </button>
            <button
              onClick={() => setConfirmClear(false)}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100"
            >
              Abbrechen
            </button>
          </div>
        )}
      </div>

      {/* ── Statistik-Badges ───────────────────────────────────────────── */}
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="flex items-center gap-2 rounded-lg border bg-white px-4 py-2 shadow-sm text-sm">
          <span className="text-gray-500">Gesamt:</span>
          <span className="font-semibold text-gray-800">{logs.length}</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border bg-white px-4 py-2 shadow-sm text-sm">
          <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
          <span className="text-gray-500">Info:</span>
          <span className="font-semibold text-gray-800">{countByLevel.info}</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border bg-white px-4 py-2 shadow-sm text-sm">
          <span className="inline-block h-2 w-2 rounded-full bg-yellow-400" />
          <span className="text-gray-500">Warnungen:</span>
          <span className="font-semibold text-gray-800">{countByLevel.warning}</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border bg-white px-4 py-2 shadow-sm text-sm">
          <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
          <span className="text-gray-500">Fehler:</span>
          <span className="font-semibold text-gray-800">{countByLevel.error}</span>
        </div>
      </div>

      {/* ── Tabelle ────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-3 text-left font-medium text-gray-600 w-44">Zeitpunkt</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600 w-28">Kategorie</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600 w-24">Level</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Meldung</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600 w-20">Batch</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600 w-20">Dok.</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading && logs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Wird geladen...
                </td>
              </tr>
            )}
            {!loading && logs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Keine Log-Einträge vorhanden
                </td>
              </tr>
            )}
            {logs.map((log) => (
              <tr
                key={log.id}
                className={
                  log.level === "error"
                    ? "bg-red-50"
                    : log.level === "warning"
                    ? "bg-yellow-50"
                    : "hover:bg-gray-50"
                }
              >
                {/* Zeitpunkt */}
                <td className="px-3 py-2.5 text-xs text-gray-500 tabular-nums whitespace-nowrap">
                  {formatDate(log.created_at)}
                </td>

                {/* Kategorie */}
                <td className="px-3 py-2.5">
                  <CategoryBadge category={log.category} />
                </td>

                {/* Level */}
                <td className="px-3 py-2.5">
                  <LevelBadge level={log.level} />
                </td>

                {/* Meldung */}
                <td className="px-3 py-2.5 text-gray-800">{log.message}</td>

                {/* Batch-ID */}
                <td className="px-3 py-2.5 text-gray-500 tabular-nums">
                  {log.batch_id != null ? (
                    <a
                      href={`/imports/${log.batch_id}`}
                      className="text-blue-600 hover:underline"
                    >
                      #{log.batch_id}
                    </a>
                  ) : (
                    "–"
                  )}
                </td>

                {/* Dokument-ID */}
                <td className="px-3 py-2.5 text-gray-500 tabular-nums">
                  {log.document_id != null ? `#${log.document_id}` : "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
