/**
 * Dokumententabelle für einen Import-Batch.
 *
 * Zeigt alle Dokumente des Batches in einer Tabelle mit:
 * - Dateiname, Größe, Seitenanzahl, Status
 * - PDF-Vorschau-Button (öffnet iframe mit dem PDF)
 * - Status-Badge (farblich kodiert)
 * - Kommentar-Feld (editierbar)
 *
 * Aktualisiert sich alle 5 Sekunden, solange der Import läuft.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { DocumentItem, documentsApi } from "@/lib/api";

interface Props {
  /** Dokumente des Batches */
  documents: DocumentItem[];
  /** Aktueller Status des Batches (für Auto-Refresh) */
  batchStatus: string;
  /** Callback zum Neuladen der Dokumente */
  onRefresh: () => void;
}

/** Formatiert Bytes in lesbare Einheit (KB, MB) */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Status-Badge Farben */
const STATUS_CLASSES: Record<string, string> = {
  pending: "bg-gray-100 text-gray-500",
  processing: "bg-blue-100 text-blue-600",
  done: "bg-green-100 text-green-700",
  error: "bg-red-100 text-red-700",
};

export default function DocumentsTable({ documents, batchStatus, onRefresh }: Props) {
  // ID des Dokuments, dessen PDF-Vorschau gerade angezeigt wird
  const [previewDocId, setPreviewDocId] = useState<number | null>(null);

  // Kommentar-Bearbeitung: welches Dokument wird gerade bearbeitet?
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [commentValue, setCommentValue] = useState("");

  // Auto-Refresh: alle 5 Sekunden, solange der Import läuft
  const refreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (batchStatus === "running" || batchStatus === "pending") {
      refreshInterval.current = setInterval(onRefresh, 5000);
    }
    return () => {
      if (refreshInterval.current) clearInterval(refreshInterval.current);
    };
  }, [batchStatus, onRefresh]);

  /** Kommentar speichern */
  async function saveComment(docId: number) {
    try {
      await documentsApi.updateComment(docId, commentValue || null);
      setEditingCommentId(null);
      onRefresh();
    } catch {
      alert("Fehler beim Speichern des Kommentars");
    }
  }

  if (documents.length === 0) {
    return (
      <p className="text-sm text-gray-500">Noch keine Dokumente vorhanden.</p>
    );
  }

  return (
    <div className={previewDocId !== null ? "flex gap-4" : ""}>
      {/* Dokumententabelle */}
      <div className={`overflow-x-auto rounded-lg border bg-white shadow-sm ${previewDocId !== null ? "w-1/2 shrink-0" : "w-full"}`}>
        <table className="w-full text-sm">
          <thead className="border-b bg-gray-50 text-left text-xs font-medium text-gray-500">
            <tr>
              <th className="px-4 py-3">#ID</th>
              <th className="px-4 py-3">Dateiname</th>
              <th className="px-4 py-3">Größe</th>
              <th className="px-4 py-3">Seiten</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Kommentar</th>
              <th className="px-4 py-3">Aktionen</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {documents.map((doc) => (
              <tr
                key={doc.id}
                className={[
                  "hover:bg-gray-50",
                  previewDocId === doc.id ? "bg-blue-50" : "",
                ].join(" ")}
              >
                {/* DB-ID */}
                <td className="px-4 py-3 font-mono text-xs text-gray-400">
                  {doc.id}
                </td>

                {/* Dateiname */}
                <td className="px-4 py-3">
                  <p className="font-medium text-gray-800">{doc.original_filename}</p>
                  {doc.stored_filename && (
                    <p className="text-xs text-gray-400">
                      gespeichert als: {doc.stored_filename}
                    </p>
                  )}
                  {doc.error_message && (
                    <p className="text-xs text-red-500 mt-0.5">{doc.error_message}</p>
                  )}
                </td>

                {/* Dateigröße */}
                <td className="px-4 py-3 text-gray-500">
                  {formatBytes(doc.file_size_bytes)}
                </td>

                {/* Seitenanzahl */}
                <td className="px-4 py-3 text-center text-gray-500">
                  {doc.page_count || "—"}
                </td>

                {/* Status */}
                <td className="px-4 py-3">
                  <span
                    className={[
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      STATUS_CLASSES[doc.status] ?? "bg-gray-100 text-gray-500",
                    ].join(" ")}
                  >
                    {doc.status}
                  </span>
                </td>

                {/* Kommentar */}
                <td className="px-4 py-3">
                  {editingCommentId === doc.id ? (
                    <div className="flex gap-1">
                      <input
                        className="rounded border px-2 py-1 text-xs"
                        value={commentValue}
                        onChange={(e) => setCommentValue(e.target.value)}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveComment(doc.id);
                          if (e.key === "Escape") setEditingCommentId(null);
                        }}
                      />
                      <button
                        onClick={() => saveComment(doc.id)}
                        className="rounded bg-blue-600 px-2 py-1 text-xs text-white"
                      >
                        OK
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setEditingCommentId(doc.id);
                        setCommentValue(doc.comment ?? "");
                      }}
                      className="text-left text-xs text-gray-400 hover:text-gray-700"
                    >
                      {doc.comment || "+ Kommentar"}
                    </button>
                  )}
                </td>

                {/* Aktionen */}
                <td className="px-4 py-3">
                  <button
                    onClick={() =>
                      setPreviewDocId(previewDocId === doc.id ? null : doc.id)
                    }
                    disabled={!doc.stored_filename}
                    className="rounded px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 disabled:opacity-30"
                  >
                    {previewDocId === doc.id ? "Vorschau aus" : "PDF anzeigen"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* PDF-Vorschau rechts */}
      {previewDocId !== null && (
        <div className="flex w-1/2 shrink-0 flex-col rounded-lg border bg-white shadow-sm">
          <div className="flex items-center justify-between border-b px-4 py-2">
            <h3 className="text-sm font-medium">PDF-Vorschau #{previewDocId}</h3>
            <button
              onClick={() => setPreviewDocId(null)}
              className="text-xs text-gray-400 hover:text-gray-700"
            >
              ✕
            </button>
          </div>
          <iframe
            src={documentsApi.previewUrl(previewDocId)}
            className="h-[calc(100vh-16rem)] min-h-[400px] w-full rounded-b-lg"
            title={`PDF-Vorschau Dokument #${previewDocId}`}
          />
        </div>
      )}
    </div>
  );
}
