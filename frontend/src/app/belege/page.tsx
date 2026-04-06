"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AIConfig,
  AnalyzeRequest,
  DocumentFilter,
  DocumentItem,
  ImportBatch,
  SystemPrompt,
  aiConfigsApi,
  documentsApi,
  importsApi,
  systemPromptsApi,
} from "@/lib/api";

// ─── Hilfsfunktionen ────────────────────────────────────────────────────────

function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return "–";
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(amount);
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
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-gray-100 text-gray-500"}`}>
      {labels[status] ?? status}
    </span>
  );
}

function KiBadge({ status }: { status: string }) {
  if (status === "done") return <span className="text-xs font-medium text-green-700">✓ Ja</span>;
  if (status === "processing") return <span className="text-xs font-medium text-blue-600">⟳ Läuft</span>;
  if (status === "error") return <span className="text-xs font-medium text-red-600">✗ Fehler</span>;
  return <span className="text-xs text-gray-400">–</span>;
}

// ─── Batch-Multiselect ───────────────────────────────────────────────────────

function BatchMultiSelect({
  batches,
  selectedIds,
  onChange,
}: {
  batches: ImportBatch[];
  selectedIds: Set<number>;
  onChange: (ids: Set<number>) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function toggle(id: number) {
    const next = new Set(selectedIds);
    next.has(id) ? next.delete(id) : next.add(id);
    onChange(next);
  }

  const label =
    selectedIds.size === 0
      ? "Alle Imports"
      : selectedIds.size === 1
      ? (() => { const b = batches.find((b) => selectedIds.has(b.id)); return b ? `${b.company_name} ${b.year}` : "1 Import"; })()
      : `${selectedIds.size} Imports`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex min-w-48 items-center justify-between gap-2 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none"
      >
        <span className="truncate">{label}</span>
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="absolute z-20 mt-1 max-h-64 min-w-64 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
          <button type="button" onClick={() => onChange(new Set())}
            className="w-full px-3 py-2 text-left text-xs font-medium text-blue-600 hover:bg-blue-50 border-b">
            Alle Imports anzeigen
          </button>
          {batches.length === 0 && <p className="px-3 py-2 text-xs text-gray-400">Keine Imports vorhanden</p>}
          {batches.map((b) => (
            <label key={b.id} className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50">
              <input type="checkbox" checked={selectedIds.has(b.id)} onChange={() => toggle(b.id)}
                className="rounded border-gray-300 text-blue-600" />
              <span className="flex-1 truncate">{b.company_name} {b.year}</span>
              <span className="text-xs text-gray-400">#{b.id}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Hauptkomponente ─────────────────────────────────────────────────────────

export default function BelegePage() {
  // Filter
  const [filterCompany, setFilterCompany] = useState("");
  const [filterYear, setFilterYear] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterTotalMin, setFilterTotalMin] = useState("");
  const [filterTotalMax, setFilterTotalMax] = useState("");
  const [filterPageMin, setFilterPageMin] = useState("");
  const [filterPageMax, setFilterPageMax] = useState("");
  const [selectedBatchIds, setSelectedBatchIds] = useState<Set<number>>(new Set());
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [activeFilters, setActiveFilters] = useState<DocumentFilter>({});

  // Daten
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Auswahl
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // PDF-Vorschau (Split-View)
  const [previewDocId, setPreviewDocId] = useState<number | null>(null);

  // Löschen-Bestätigung
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  // Analyse-Optionen
  const [aiConfigs, setAiConfigs] = useState<AIConfig[]>([]);
  const [systemPrompts, setSystemPrompts] = useState<SystemPrompt[]>([]);
  const [selectedAiConfigId, setSelectedAiConfigId] = useState<string>("");
  const [selectedSystemPromptId, setSelectedSystemPromptId] = useState<string>("");
  const [analyzing, setAnalyzing] = useState(false);

  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Laden ──────────────────────────────────────────────────────────────

  const loadDocuments = useCallback(async (filters: DocumentFilter) => {
    setLoading(true);
    setError(null);
    try {
      const docs = await documentsApi.list(filters);
      setDocuments(docs);
    } catch (err) {
      setError("Fehler beim Laden der Belege");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadOptions = useCallback(async () => {
    try {
      const [configs, prompts, allBatches] = await Promise.all([
        aiConfigsApi.list(),
        systemPromptsApi.list(),
        importsApi.list(),
      ]);
      setAiConfigs(configs);
      setSystemPrompts(prompts);
      setBatches(allBatches);
      const defaultConfig = configs.find((c) => c.is_default);
      if (defaultConfig) setSelectedAiConfigId(String(defaultConfig.id));
      const defaultPrompt = prompts.find((p) => p.is_default);
      if (defaultPrompt) setSelectedSystemPromptId(String(defaultPrompt.id));
    } catch (err) {
      console.error("Fehler beim Laden der Optionen:", err);
    }
  }, []);

  useEffect(() => {
    loadDocuments({});
    loadOptions();
  }, [loadDocuments, loadOptions]);

  // Auto-Refresh bei processing-Dokumenten
  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");
    if (hasProcessing && !refreshTimerRef.current) {
      refreshTimerRef.current = setInterval(() => loadDocuments(activeFilters), 5000);
    } else if (!hasProcessing && refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    return () => { if (refreshTimerRef.current) { clearInterval(refreshTimerRef.current); refreshTimerRef.current = null; } };
  }, [documents, activeFilters, loadDocuments]);

  // ─── Filter-Logik ─────────────────────────────────────────────────────────

  function buildFilters(): DocumentFilter {
    const f: DocumentFilter = {};
    if (filterCompany.trim()) f.company = filterCompany.trim();
    if (filterYear) f.year = parseInt(filterYear, 10);
    if (filterStatus) f.status = filterStatus;
    if (filterTotalMin) f.total_min = parseFloat(filterTotalMin);
    if (filterTotalMax) f.total_max = parseFloat(filterTotalMax);
    if (filterPageMin) f.page_min = parseInt(filterPageMin, 10);
    if (filterPageMax) f.page_max = parseInt(filterPageMax, 10);
    if (selectedBatchIds.size > 0) f.batch_ids = Array.from(selectedBatchIds);
    if (includeDeleted) f.include_deleted = true;
    return f;
  }

  function applyFilters() {
    const f = buildFilters();
    setActiveFilters(f);
    setSelectedIds(new Set());
    setPreviewDocId(null);
    loadDocuments(f);
  }

  function resetFilters() {
    setFilterCompany(""); setFilterYear(""); setFilterStatus("");
    setFilterTotalMin(""); setFilterTotalMax(""); setFilterPageMin(""); setFilterPageMax("");
    setSelectedBatchIds(new Set()); setIncludeDeleted(false);
    const f: DocumentFilter = {};
    setActiveFilters(f);
    setSelectedIds(new Set());
    setPreviewDocId(null);
    loadDocuments(f);
  }

  // ─── Auswahl ──────────────────────────────────────────────────────────────

  function toggleSelectAll() {
    const activeDocs = documents.filter((d) => !d.deleted_at);
    if (selectedIds.size === activeDocs.length && activeDocs.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(activeDocs.map((d) => d.id)));
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  // ─── KI-Analyse ───────────────────────────────────────────────────────────

  async function startAnalysis() {
    if (selectedIds.size === 0) return;
    setAnalyzing(true);
    setError(null);
    setSuccessMsg(null);
    const payload: AnalyzeRequest = { document_ids: Array.from(selectedIds) };
    if (selectedAiConfigId) payload.ai_config_id = parseInt(selectedAiConfigId, 10);
    if (selectedSystemPromptId) payload.system_prompt_id = parseInt(selectedSystemPromptId, 10);
    try {
      const result = await documentsApi.analyze(payload);
      setSuccessMsg(result.message);
      setSelectedIds(new Set());
      await loadDocuments(activeFilters);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Fehler beim Starten der KI-Analyse";
      setError(msg);
    } finally {
      setAnalyzing(false);
    }
  }

  // ─── Soft-Delete / Restore ────────────────────────────────────────────────

  async function handleDelete(docId: number) {
    try {
      await documentsApi.softDelete(docId);
      setDeleteConfirmId(null);
      setSelectedIds((prev) => { const next = new Set(prev); next.delete(docId); return next; });
      await loadDocuments(activeFilters);
    } catch (err) {
      setError("Fehler beim Löschen des Belegs");
      console.error(err);
    }
  }

  async function handleRestore(docId: number) {
    try {
      await documentsApi.restore(docId);
      await loadDocuments(activeFilters);
    } catch (err) {
      setError("Fehler beim Wiederherstellen des Belegs");
      console.error(err);
    }
  }

  // ─── Ableitungen ──────────────────────────────────────────────────────────

  const activeDocs = documents.filter((d) => !d.deleted_at);
  const allSelected = activeDocs.length > 0 && selectedIds.size === activeDocs.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < activeDocs.length;
  const availableYears = Array.from(new Set(documents.map((d) => d.year))).sort((a, b) => b - a);

  // ─── Render ───────────────────────────────────────────────────────────────

  const showPreview = previewDocId !== null;
  const previewDoc = showPreview ? documents.find((d) => d.id === previewDocId) : null;

  return (
    <>
      {/* ── Kopfbereich (max-Breite, erbt das p-6 vom Layout) ─────────── */}
      <div>
        <h1 className="mb-6 text-2xl font-bold text-gray-900">Belege</h1>

        {/* ── Meldungen ──────────────────────────────────────────────── */}
        {error && (
          <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700 border border-red-200">{error}</div>
        )}
        {successMsg && (
          <div className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-700 border border-green-200">{successMsg}</div>
        )}

        {/* ── Filter ────────────────────────────────────────────────── */}
        <div className="mb-4 rounded-lg border bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Import</label>
              <BatchMultiSelect batches={batches} selectedIds={selectedBatchIds} onChange={setSelectedBatchIds} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Firma</label>
              <input type="text" value={filterCompany} onChange={(e) => setFilterCompany(e.target.value)}
                placeholder="z.B. Müller GmbH"
                className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-40" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Jahr</label>
              <select value={filterYear} onChange={(e) => setFilterYear(e.target.value)}
                className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-28">
                <option value="">Alle Jahre</option>
                {availableYears.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Status</label>
              <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
                className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-40">
                <option value="">Alle Status</option>
                <option value="pending">Ausstehend</option>
                <option value="processing">Wird verarbeitet</option>
                <option value="done">Fertig</option>
                <option value="error">Fehler</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Betrag von (€)</label>
              <input type="number" value={filterTotalMin} onChange={(e) => setFilterTotalMin(e.target.value)}
                placeholder="0" min="0" step="0.01"
                className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-28" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Betrag bis (€)</label>
              <input type="number" value={filterTotalMax} onChange={(e) => setFilterTotalMax(e.target.value)}
                placeholder="∞" min="0" step="0.01"
                className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-28" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Seiten von</label>
              <input type="number" value={filterPageMin} onChange={(e) => setFilterPageMin(e.target.value)}
                placeholder="1" min="1"
                className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-24" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Seiten bis</label>
              <input type="number" value={filterPageMax} onChange={(e) => setFilterPageMax(e.target.value)}
                placeholder="∞" min="1"
                className="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none w-24" />
            </div>
            {/* Gelöschte anzeigen */}
            <label className="flex cursor-pointer items-center gap-2 mt-auto pb-1.5">
              <input type="checkbox" checked={includeDeleted} onChange={(e) => setIncludeDeleted(e.target.checked)}
                className="rounded border-gray-300 text-blue-600" />
              <span className="text-sm text-gray-600">Gelöschte anzeigen</span>
            </label>
            <div className="flex gap-2 mt-auto">
              <button onClick={applyFilters}
                className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors">
                Filter anwenden
              </button>
              <button onClick={resetFilters}
                className="rounded border border-gray-300 px-4 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors">
                Zurücksetzen
              </button>
            </div>
          </div>
        </div>

        {/* ── KI-Analyse (immer sichtbar) ────────────────────────────── */}
        <div className={`mb-4 rounded-lg border p-4 transition-colors ${selectedIds.size > 0 ? "border-blue-200 bg-blue-50" : "border-gray-200 bg-gray-50"}`}>
          <div className="flex flex-wrap items-center gap-4">
            <span className={`text-sm font-medium ${selectedIds.size > 0 ? "text-blue-800" : "text-gray-500"}`}>
              {selectedIds.size > 0
                ? `${selectedIds.size} Dokument${selectedIds.size !== 1 ? "e" : ""} ausgewählt`
                : "Dokumente auswählen für KI-Analyse"}
            </span>
            <div className="flex flex-col gap-1">
              <label className={`text-xs font-medium ${selectedIds.size > 0 ? "text-blue-700" : "text-gray-500"}`}>KI-Konfiguration</label>
              <select value={selectedAiConfigId} onChange={(e) => setSelectedAiConfigId(e.target.value)}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none min-w-48">
                <option value="">Standard</option>
                {aiConfigs.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}{c.is_default ? " (Standard)" : ""}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className={`text-xs font-medium ${selectedIds.size > 0 ? "text-blue-700" : "text-gray-500"}`}>Systemprompt</label>
              <select value={selectedSystemPromptId} onChange={(e) => setSelectedSystemPromptId(e.target.value)}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none min-w-48">
                <option value="">Standard</option>
                {systemPrompts.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}{p.is_default ? " (Standard)" : ""}</option>
                ))}
              </select>
            </div>
            <button onClick={startAnalysis} disabled={analyzing || selectedIds.size === 0}
              className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors mt-auto">
              {analyzing ? "Starte..." : "KI-Analyse starten"}
            </button>
          </div>
        </div>

      </div>{/* Ende Kopfbereich */}

      {/* ── Tabelle: volle Bildschirmbreite ──────────────────────────── */}
      <div className="relative left-1/2 w-screen -translate-x-1/2 px-6 mt-4">

        {/* Anzahl */}
        <div className="mb-2 text-sm text-gray-500">
          {loading ? "Lade..." : `${documents.length} Beleg${documents.length !== 1 ? "e" : ""} gefunden`}
        </div>

        {/* Split-View: Tabelle links, PDF rechts */}
        <div className={showPreview ? "flex gap-4" : ""}>

          {/* Tabelle */}
          <div className={`overflow-x-auto rounded-lg border bg-white shadow-sm ${showPreview ? "w-1/2 shrink-0" : "w-full"}`}>
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="w-10 px-3 py-3">
                    <input type="checkbox" checked={allSelected}
                      ref={(el) => { if (el) el.indeterminate = someSelected; }}
                      onChange={toggleSelectAll}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                  </th>
                  <th className="px-3 py-3 text-left font-medium text-gray-600">#</th>
                  <th className="px-3 py-3 text-left font-medium text-gray-600">Firma</th>
                  <th className="px-3 py-3 text-left font-medium text-gray-600">Jahr</th>
                  <th className="px-3 py-3 text-left font-medium text-gray-600">Dateiname</th>
                  <th className="px-3 py-3 text-right font-medium text-gray-600">Seiten</th>
                  <th className="px-3 py-3 text-right font-medium text-gray-600">Betrag</th>
                  <th className="px-3 py-3 text-left font-medium text-gray-600">Status</th>
                  <th className="px-3 py-3 text-left font-medium text-gray-600">KI</th>
                  {!showPreview && (
                    <>
                      <th className="px-3 py-3 text-left font-medium text-gray-600">Rechnungsnr.</th>
                      <th className="px-3 py-3 text-left font-medium text-gray-600">Lieferant</th>
                    </>
                  )}
                  <th className="px-3 py-3 text-left font-medium text-gray-600">Aktionen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading && documents.length === 0 && (
                  <tr><td colSpan={12} className="px-4 py-8 text-center text-gray-400">Wird geladen...</td></tr>
                )}
                {!loading && documents.length === 0 && (
                  <tr><td colSpan={12} className="px-4 py-8 text-center text-gray-400">Keine Belege gefunden</td></tr>
                )}
                {documents.map((doc) => {
                  const isDeleted = !!doc.deleted_at;
                  const isConfirmingDelete = deleteConfirmId === doc.id;
                  const isActivePreview = previewDocId === doc.id;

                  return (
                    <tr key={doc.id}
                      className={[
                        isDeleted ? "bg-red-50 opacity-60"
                          : isActivePreview ? "bg-blue-50"
                          : selectedIds.has(doc.id) ? "bg-blue-50"
                          : "hover:bg-gray-50",
                      ].join(" ")}>

                      {/* Checkbox */}
                      <td className="w-10 px-3 py-2.5">
                        {!isDeleted && (
                          <input type="checkbox" checked={selectedIds.has(doc.id)}
                            onChange={() => toggleSelect(doc.id)}
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                        )}
                      </td>

                      <td className="px-3 py-2.5 text-gray-500 tabular-nums">{doc.id}</td>
                      <td className="px-3 py-2.5 font-medium text-gray-900">{doc.company}</td>
                      <td className="px-3 py-2.5 text-gray-700">{doc.year}</td>

                      {/* Dateiname */}
                      <td className="px-3 py-2.5 text-gray-700 max-w-xs">
                        <div className="flex items-center gap-2">
                          <span className="truncate" title={doc.original_filename}>{doc.original_filename}</span>
                          {isDeleted && (
                            <span className="shrink-0 inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                              Gelöscht
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="px-3 py-2.5 text-right text-gray-700 tabular-nums">
                        {doc.page_count > 0 ? doc.page_count : "–"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-700 tabular-nums">
                        {formatCurrency(doc.total_amount)}
                      </td>
                      <td className="px-3 py-2.5"><StatusBadge status={doc.status} /></td>
                      <td className="px-3 py-2.5"><KiBadge status={doc.status} /></td>

                      {/* Rechnungsnr. + Lieferant nur ohne Preview */}
                      {!showPreview && (
                        <>
                          <td className="px-3 py-2.5 text-gray-700">{doc.invoice_number ?? "–"}</td>
                          <td className="px-3 py-2.5 text-gray-700 max-w-[140px] truncate" title={doc.supplier_name ?? ""}>
                            {doc.supplier_name ?? "–"}
                          </td>
                        </>
                      )}

                      {/* Aktionen */}
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-1.5">
                          {/* PDF */}
                          {!isDeleted && (
                            <button
                              onClick={() => setPreviewDocId(isActivePreview ? null : doc.id)}
                              disabled={!doc.stored_filename}
                              className={[
                                "rounded px-2 py-1 text-xs font-medium transition-colors",
                                isActivePreview
                                  ? "bg-blue-600 text-white hover:bg-blue-700"
                                  : "border border-gray-300 text-gray-600 hover:bg-gray-100",
                                !doc.stored_filename ? "opacity-30 cursor-not-allowed" : "",
                              ].join(" ")}
                            >
                              {isActivePreview ? "Vorschau aus" : "PDF"}
                            </button>
                          )}

                          {/* Löschen / Wiederherstellen */}
                          {isDeleted ? (
                            <button onClick={() => handleRestore(doc.id)}
                              className="rounded border border-green-300 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 transition-colors">
                              Wiederherstellen
                            </button>
                          ) : isConfirmingDelete ? (
                            <>
                              <button onClick={() => handleDelete(doc.id)}
                                className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700">
                                Ja
                              </button>
                              <button onClick={() => setDeleteConfirmId(null)}
                                className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-500 hover:bg-gray-100">
                                Nein
                              </button>
                            </>
                          ) : (
                            <button onClick={() => setDeleteConfirmId(doc.id)}
                              className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 transition-colors">
                              Löschen
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* PDF-Vorschau rechts (50%) */}
          {showPreview && (
            <div className="flex w-1/2 shrink-0 flex-col rounded-lg border bg-white shadow-sm">
              <div className="flex items-center justify-between border-b px-4 py-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-sm font-medium text-gray-800 truncate">
                    {previewDoc?.original_filename ?? `Dokument #${previewDocId}`}
                  </span>
                  <span className="shrink-0 text-xs text-gray-400">#{previewDocId}</span>
                </div>
                <button onClick={() => setPreviewDocId(null)}
                  className="ml-3 shrink-0 text-sm text-gray-400 hover:text-gray-700">
                  ✕
                </button>
              </div>
              <iframe
                src={documentsApi.previewUrl(previewDocId!)}
                className="h-[calc(100vh-16rem)] min-h-[400px] w-full rounded-b-lg"
                title={`PDF-Vorschau #${previewDocId}`}
              />
            </div>
          )}

        </div>{/* Ende Split-View */}
      </div>{/* Ende volle Breite */}
    </>
  );
}
