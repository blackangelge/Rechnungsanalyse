/**
 * Seite: Import-Detailansicht (/imports/[id])
 *
 * Zeigt für einen Import-Batch:
 * - Fortschrittsanzeige mit SSE-Echtzeit-Updates
 * - Debug-Fenster mit rohen SSE-Events
 * - Tabelle aller importierten Dokumente mit PDF-Vorschau
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ImportBatchWithDocuments, importsApi } from "@/lib/api";
import ProgressPanel from "@/components/imports/ProgressPanel";
import DebugWindow from "@/components/imports/DebugWindow";
import DocumentsTable from "@/components/imports/DocumentsTable";

export default function ImportDetailPage() {
  // Next.js App Router: ID aus der URL holen
  const params = useParams();
  const batchId = parseInt(params.id as string);

  const [batch, setBatch] = useState<ImportBatchWithDocuments | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /** Batch-Daten vom Server laden */
  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await importsApi.get(batchId);
      setBatch(data);
    } catch {
      setError("Fehler beim Laden des Imports");
    } finally {
      setLoading(false);
    }
  }, [batchId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <p className="text-sm text-gray-500">Lade Import...</p>;
  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (!batch) return null;

  return (
    <div className="space-y-6">
      {/* Kopfzeile */}
      <div>
        <h1 className="text-xl font-semibold">
          Import: {batch.company_name} {batch.year}
        </h1>
        <p className="text-sm text-gray-500">
          {batch.folder_path}
          {batch.comment && (
            <> · <span className="italic">{batch.comment}</span></>
          )}
        </p>
      </div>

      {/* Fortschrittsanzeige und Debug-Fenster nebeneinander */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ProgressPanel
          batchId={batchId}
          initialStatus={batch.status}
          initialTotal={batch.total_docs}
          initialProcessed={batch.processed_docs}
        />
        <DebugWindow batchId={batchId} initialStatus={batch.status} />
      </div>

      {/* Dokumententabelle — volle Fensterbreite */}
      <div className="relative left-1/2 w-screen -translate-x-1/2 px-6">
        <h2 className="mb-3 font-semibold">
          Dokumente ({batch.documents.length})
        </h2>
        <DocumentsTable
          documents={batch.documents}
          batchStatus={batch.status}
          onRefresh={load}
        />
      </div>
    </div>
  );
}
