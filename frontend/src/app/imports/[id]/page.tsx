/**
 * Seite: Import-Detailansicht (/imports/[id])
 *
 * Zeigt für einen Import-Batch:
 * - Fortschrittsanzeige mit SSE-Echtzeit-Updates
 * - Debug-Fenster mit rohen SSE-Events
 * - Dokumententabelle (paginiert, 50 pro Seite) — NUR nach Abschluss des Imports
 *
 * WICHTIG: Während der Import läuft, wird die Dokumentliste NICHT geladen
 * und NICHT alle 5 Sekunden gepolt. Das SSE-Protokoll liefert den Fortschritt.
 * Erst wenn der Import abgeschlossen ist (done/error), wird die Dokumentliste
 * einmalig geladen und paginiert angezeigt.
 *
 * Warum? Mit 1000 Dokumenten wäre ein 5-Sekunden-Poll ein 1000-Zeilen-JSON
 * bei jeder Anfrage — das friert den Browser ein und belastet den Server.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ImportBatch, DocumentItem, importsApi } from "@/lib/api";
import ProgressPanel from "@/components/imports/ProgressPanel";
import DebugWindow from "@/components/imports/DebugWindow";
import DocumentsTable from "@/components/imports/DocumentsTable";

export default function ImportDetailPage() {
  const params = useParams();
  const batchId = parseInt(params.id as string);

  // Batch-Metadaten (ohne Dokumente) — immer geladen
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  // Dokumente — nur nach Abschluss des Imports
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [docsLoading, setDocsLoading] = useState(false);

  const [metaLoading, setMetaLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Ref to track whether batch was ever successfully loaded (avoids `batch` in deps)
  const batchLoadedRef = useRef(false);

  /** Nur Batch-Metadaten laden (schnell, kein JOIN über alle Dokumente) */
  const loadMeta = useCallback(async () => {
    try {
      setError(null);
      const data = await importsApi.getStatus(batchId);
      setBatch(data);
      batchLoadedRef.current = true;
      return data;
    } catch (err: unknown) {
      // ECONNRESET / Netzwerkfehler während laufendem Import → kein harter Fehler
      const isNetworkErr =
        err instanceof Error &&
        (err.message.includes("Network Error") ||
          err.message.includes("ECONNRESET") ||
          err.message.includes("socket hang up"));
      if (isNetworkErr && !batchLoadedRef.current) {
        // Noch kein Batch geladen → Fallback: Seite zeigt Ladezustand
        setError("Backend kurzzeitig nicht erreichbar — bitte Seite neu laden.");
      } else if (!isNetworkErr) {
        setError("Fehler beim Laden des Imports");
      }
      // Bei bereits geladenem Batch + Netzwerkfehler: alten Stand behalten
      return null;
    } finally {
      setMetaLoading(false);
    }
  }, [batchId]);

  /** Dokumente laden — einmalig nach Import-Abschluss */
  const loadDocuments = useCallback(async () => {
    setDocsLoading(true);
    try {
      const data = await importsApi.get(batchId);
      setDocuments(data.documents);
      setBatch(data); // ImportBatchWithDocuments ist Subtyp von ImportBatch
    } catch {
      setError("Fehler beim Laden der Dokumente");
    } finally {
      setDocsLoading(false);
    }
  }, [batchId]);

  // Initialer Ladevorgang
  useEffect(() => {
    loadMeta().then((data) => {
      // Falls Import bereits abgeschlossen → Dokumente sofort laden
      if (data && (data.status === "done" || data.status === "error")) {
        loadDocuments();
      }
    });
  }, [loadMeta, loadDocuments]);

  /** Callback vom ProgressPanel: Import ist abgeschlossen → Dokumente laden */
  const handleImportDone = useCallback(() => {
    loadDocuments();
  }, [loadDocuments]);

  if (metaLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-gray-500">
        <span className="animate-spin">⟳</span> Lade Import…
      </div>
    );
  }

  if (error && !batch) {
    return <p className="text-sm text-red-500">{error}</p>;
  }

  if (!batch) return null;

  const isActive = batch.status === "running" || batch.status === "pending";

  return (
    <div className="space-y-6">
      {/* Kopfzeile */}
      <div>
        <h1 className="text-xl font-semibold text-gray-900">
          Import: {batch.company_name} {batch.year}
        </h1>
        <p className="text-sm text-gray-500">
          {batch.folder_path}
          {batch.comment && (
            <> · <span className="italic">{batch.comment}</span></>
          )}
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Fortschrittsanzeige + Debug nebeneinander */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ProgressPanel
          batchId={batchId}
          initialStatus={batch.status}
          initialTotal={batch.total_docs}
          initialProcessed={batch.processed_docs}
          onDone={handleImportDone}
        />
        <DebugWindow batchId={batchId} initialStatus={batch.status} />
      </div>

      {/* Während Import läuft: Hinweis statt Dokumententabelle */}
      {isActive && (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-5 py-4 text-sm text-blue-700">
          <span className="mr-2 animate-spin inline-block">⟳</span>
          Import läuft — die Dokumentenliste wird nach Abschluss automatisch geladen.
          {batch.total_docs > 0 && (
            <span className="ml-1 text-blue-500">
              ({batch.processed_docs.toLocaleString("de-DE")} / {batch.total_docs.toLocaleString("de-DE")} verarbeitet)
            </span>
          )}
        </div>
      )}

      {/* Dokumententabelle — nur nach Abschluss */}
      {!isActive && (
        <div className="relative left-1/2 w-screen -translate-x-1/2 px-6">
          <div className="mb-3 flex items-center gap-3">
            <h2 className="font-semibold text-gray-900">
              Dokumente
              {batch.total_docs > 0 && (
                <span className="ml-1 text-sm font-normal text-gray-500">
                  ({batch.total_docs.toLocaleString("de-DE")})
                </span>
              )}
            </h2>
            <button
              onClick={loadDocuments}
              disabled={docsLoading}
              className="rounded border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              {docsLoading ? "Lade…" : "↻ Aktualisieren"}
            </button>
          </div>

          {docsLoading && !documents && (
            <div className="rounded-lg border bg-white px-6 py-10 text-center text-sm text-gray-400 shadow-sm">
              <span className="animate-spin inline-block mr-2">⟳</span>
              Lade {batch.total_docs.toLocaleString("de-DE")} Dokumente…
            </div>
          )}

          {documents !== null && (
            <DocumentsTable
              documents={documents}
              onRefresh={loadDocuments}
            />
          )}
        </div>
      )}
    </div>
  );
}
