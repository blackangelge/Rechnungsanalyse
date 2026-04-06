"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AIConfig,
  AnalyzeRequest,
  DocumentFilter,
  DocumentItem,
  SystemPrompt,
  aiConfigsApi,
  documentsApi,
  systemPromptsApi,
} from "@/lib/api";

// ─── Hilfsfunktionen ────────────────────────────────────────────────────────

function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return "–";
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(amount);
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-gray-100 text-gray-600",
    processing: "bg-blue-100 text-blue-700",
    done: "bg-green-100 text-green-700",
    error: "bg-red-100 text-red-700",
  };
  const labels: Record<string, string> = {
    pending: "Ausstehend",
    processing: "Wird verarbeitet",
    done: "Fertig",
    error: "Fehler",
  };
  const cls = styles[status] ?? "bg-gray-100 text-gray-500";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {labels[status] ?? status}
    </span>
  );
}

// ─── Hauptkomponente ─────────────────────────────────────────────────────────

export default function BelegePage() {
  // Filter-State
  const [filterCompany, setFilterCompany] = useState("");
  const [filterYear, setFilterYear] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterTotalMin, setFilterTotalMin] = useState("");
  const [filterTotalMax, setFilterTotalMax] = useState("");
  const [filterPageMin, setFilterPageMin] = useState("");
  const [filterPageMax, setFilterPageMax] = useState("");

  // Aktive Filter (werden nur bei "Filter anwenden" übernommen)
  const [activeFilters, setActiveFilters] = useState<DocumentFilter>({});

  // Daten
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Auswahl
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Analyse-Optionen
  const [aiConfigs, setAiConfigs] = useState<AIConfig[]>([]);
  const [systemPrompts, setSystemPrompts] = useState<SystemPrompt[]>([]);
  const [selectedAiConfigId, setSelectedAiConfigId] = useState<string>("");
  const [selectedSystemPromptId, setSelectedSystemPromptId] = useState<string>("");
  const [analyzing, setAnalyzing] = useState(false);

  // Auto-Refresh
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Daten laden ──────────────────────────────────────────────────────────

  const loadDocuments = useCallback(async (filters: DocumentFilter) => {
    setLoading(true);
    setError(null);
    try {
      const docs = await documentsApi.list(filters);
      setDocuments(docs);
    } catch (err: unknown) {
      setError("Fehler beim Laden der Belege");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadOptions = useCallback(async () => {
    try {
      const [configs, prompts] = await Promise.all([
        aiConfigsApi.list(),
        systemPromptsApi.list(),
      ]);
      setAiConfigs(configs);
      setSystemPrompts(prompts);

      // Defaults vorauswählen
      const defaultConfig = configs.find((c) => c.is_default);
      if (defaultConfig) setSelectedAiConfigId(String(defaultConfig.id));

      const defaultPrompt = prompts.find((p) => p.is_default);
      if (defaultPrompt) setSelectedSystemPromptId(String(defaultPrompt.id));
    } catch (err) {
      console.error("Fehler beim Laden der KI-Optionen:", err);
    }
  }, []);

  // Initial laden
  useEffect(() => {
    loadDocuments({});
    loadOptions();
  }, [loadDocuments, loadOptions]);

  // Auto-Refresh wenn Processing-Dokumente vorhanden
  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");

    if (hasProcessing && !refreshTimerRef.current) {
      refreshTimerRef.current = setInterval(() => {
        loadDocuments(activeFilters);
      }, 5000);
    } else if (!hasProcessing && refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [documents, activeFilters, loadDocuments]);

  // ─── Filter-Logik ─────────────────────────────────────────────────────────

  function applyFilters() {
    const filters: DocumentFilter = {};
    if (filterCompany.trim()) filters.company = filterCompany.trim();
    if (filterYear) filters.year = parseInt(filterYear, 10);
    if (filterStatus) filters.status = filterStatus;
    if (filterTotalMin) filters.total_min = parseFloat(filterTotalMin);
    if (filterTotalMax) filters.total_max = parseFloat(filterTotalMax);
    if (filterPageMin) filters.page_min = parseInt(filterPageMin, 10);
    if (filterPageMax) filters.page_max = parseInt(filterPageMax, 10);
    setActiveFilters(filters);
    setSelectedIds(new Set());
    loadDocuments(filters);
  }

  function resetFilters() {
    setFilterCompany("");
    setFilterYear("");
    setFilterStatus("");
    setFilterTotalMin("");
    setFilterTotalMax("");
    setFilterPageMin("");
    setFilterPageMax("");
    setActiveFilters({});
    setSelectedIds(new Set());
    loadDocuments({});
  }

  // ─── Auswahl-Logik ────────────────────────────────────────────────────────

  function toggleSelectAll() {
    if (selectedIds.size === documents.length && documents.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(documents.map((d) => d.id)));
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // ─── Analyse starten ──────────────────────────────────────────────────────

  async function startAnalysis() {
    if (selectedIds.size === 0) return;
    setAnalyzing(true);
    setError(null);
    setSuccessMsg(null);

    const payload: AnalyzeRequest = {
      document_ids: Array.from(selectedIds),
    };
    if (selectedAiConfigId) payload.ai_config_id = parseInt(selectedAiConfigId, 10);
    if (selectedSystemPromptId) payload.system_prompt_id = parseInt(selectedSystemPromptId, 10);

    try {
      const result = await documentsApi.analyze(payload);
      setSuccessMsg(result.message);
      setSelectedIds(new Set());
      // Sofort neu laden um "processing"-Status zu sehen
      await loadDocuments(activeFilters);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Fehler beim Starten der KI-Analyse";
      setError(msg);
    } finally {
      setAnalyzing(false);
    }
  }

  // ─── Jahr-Optionen aus vorhandenen Dokumenten ────────────────────────────
  const availableYears = Array.from(new Set(documents.map((d) => d.year))).sort(
    (a, b) => b - a
  );

  // ─── Render ───────────────────────────────────────────────────────────────

  const allSelected = documents.length > 0 && selectedIds.size === documents.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < documents.length;

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Belege</h1>

      {/* ── Meldungen ──────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700 border border-red-200">
          {error}
        </div>
      )}
      {successMsg && (
        <div className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-700 border border-green-200">
          {successMsg}
        </div>
      )}

      {/* ── Filter-Bereich ─────────────────────────────────────────────── */}
      <div className="mb-4 rounded-lg border bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-end gap-3">
          {/* Firma */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Firma</label>
            <input
              type="text"
              value={filterCompany}
              onChange={(e) => setFilterCompany(e.target.value)}
              placeholder="z.B. Müller GmbH"
              className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-40"
            />
          </div>

          {/* Jahr */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Jahr</label>
            <select
              value={filterYear}
              onChange={(e) => setFilterYear(e.target.value)}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-28"
            >
              <option value="">Alle Jahre</option>
              {availableYears.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>

          {/* Status */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Status</label>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-40"
            >
              <option value="">Alle Status</option>
              <option value="pending">Ausstehend</option>
              <option value="processing">Wird verarbeitet</option>
              <option value="done">Fertig</option>
              <option value="error">Fehler</option>
            </select>
          </div>

          {/* Betrag von/bis */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Betrag von (€)</label>
            <input
              type="number"
              value={filterTotalMin}
              onChange={(e) => setFilterTotalMin(e.target.value)}
              placeholder="0"
              min="0"
              step="0.01"
              className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-28"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Betrag bis (€)</label>
            <input
              type="number"
              value={filterTotalMax}
              onChange={(e) => setFilterTotalMax(e.target.value)}
              placeholder="∞"
              min="0"
              step="0.01"
              className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-28"
            />
          </div>

          {/* Seiten von/bis */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Seiten von</label>
            <input
              type="number"
              value={filterPageMin}
              onChange={(e) => setFilterPageMin(e.target.value)}
              placeholder="1"
              min="1"
              className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-24"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Seiten bis</label>
            <input
              type="number"
              value={filterPageMax}
              onChange={(e) => setFilterPageMax(e.target.value)}
              placeholder="∞"
              min="1"
              className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-24"
            />
          </div>

          {/* Buttons */}
          <div className="flex gap-2 mt-auto">
            <button
              onClick={applyFilters}
              className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              Filter anwenden
            </button>
            <button
              onClick={resetFilters}
              className="rounded border border-gray-300 px-4 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
            >
              Zurücksetzen
            </button>
          </div>
        </div>
      </div>

      {/* ── Aktionsleiste (erscheint bei Auswahl) ──────────────────────── */}
      {selectedIds.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <span className="text-sm font-medium text-blue-800">
            {selectedIds.size} Dokument{selectedIds.size !== 1 ? "e" : ""} ausgewählt
          </span>

          {/* KI-Konfiguration */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-blue-700">KI-Konfiguration</label>
            <select
              value={selectedAiConfigId}
              onChange={(e) => setSelectedAiConfigId(e.target.value)}
              className="rounded border border-blue-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none min-w-48"
            >
              <option value="">Standard</option>
              {aiConfigs.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}{c.is_default ? " (Standard)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* System-Prompt */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-blue-700">Systemprompt</label>
            <select
              value={selectedSystemPromptId}
              onChange={(e) => setSelectedSystemPromptId(e.target.value)}
              className="rounded border border-blue-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none min-w-48"
            >
              <option value="">Standard</option>
              {systemPrompts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.is_default ? " (Standard)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Analyse-Button */}
          <button
            onClick={startAnalysis}
            disabled={analyzing}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 transition-colors mt-auto"
          >
            {analyzing ? "Starte..." : "KI-Analyse starten"}
          </button>
        </div>
      )}

      {/* ── Anzahl-Anzeige ─────────────────────────────────────────────── */}
      <div className="mb-2 text-sm text-gray-500">
        {loading ? "Lade..." : `${documents.length} Beleg${documents.length !== 1 ? "e" : ""} gefunden`}
      </div>

      {/* ── Tabelle ────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              {/* Checkbox Header */}
              <th className="w-10 px-3 py-3">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someSelected;
                  }}
                  onChange={toggleSelectAll}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
              </th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">#</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Firma</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Jahr</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Dateiname</th>
              <th className="px-3 py-3 text-right font-medium text-gray-600">Seiten</th>
              <th className="px-3 py-3 text-right font-medium text-gray-600">Betrag</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Status</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Rechnungsnr.</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Lieferant</th>
              <th className="px-3 py-3 text-left font-medium text-gray-600">Aktionen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading && documents.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-8 text-center text-gray-400">
                  Wird geladen...
                </td>
              </tr>
            )}
            {!loading && documents.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-8 text-center text-gray-400">
                  Keine Belege gefunden
                </td>
              </tr>
            )}
            {documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                selected={selectedIds.has(doc.id)}
                onToggle={() => toggleSelect(doc.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Tabellenzeile ────────────────────────────────────────────────────────────

function DocumentRow({
  doc,
  selected,
  onToggle,
}: {
  doc: DocumentItem;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <tr className={selected ? "bg-blue-50" : "hover:bg-gray-50"}>
      {/* Checkbox */}
      <td className="w-10 px-3 py-2.5">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        />
      </td>

      {/* ID */}
      <td className="px-3 py-2.5 text-gray-500 tabular-nums">{doc.id}</td>

      {/* Firma */}
      <td className="px-3 py-2.5 font-medium text-gray-900">{doc.company}</td>

      {/* Jahr */}
      <td className="px-3 py-2.5 text-gray-700">{doc.year}</td>

      {/* Dateiname */}
      <td className="px-3 py-2.5 text-gray-700 max-w-xs truncate" title={doc.original_filename}>
        {doc.original_filename}
      </td>

      {/* Seiten */}
      <td className="px-3 py-2.5 text-right text-gray-700 tabular-nums">
        {doc.page_count > 0 ? doc.page_count : "–"}
      </td>

      {/* Betrag */}
      <td className="px-3 py-2.5 text-right text-gray-700 tabular-nums">
        {formatCurrency(doc.total_amount)}
      </td>

      {/* Status */}
      <td className="px-3 py-2.5">
        <StatusBadge status={doc.status} />
      </td>

      {/* Rechnungsnr. */}
      <td className="px-3 py-2.5 text-gray-700">
        {doc.invoice_number ?? "–"}
      </td>

      {/* Lieferant */}
      <td className="px-3 py-2.5 text-gray-700 max-w-[160px] truncate" title={doc.supplier_name ?? ""}>
        {doc.supplier_name ?? "–"}
      </td>

      {/* Aktionen */}
      <td className="px-3 py-2.5">
        <a
          href={documentsApi.previewUrl(doc.id)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors"
        >
          PDF
        </a>
      </td>
    </tr>
  );
}
