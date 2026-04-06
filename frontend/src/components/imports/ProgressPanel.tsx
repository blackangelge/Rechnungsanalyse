/**
 * Echtzeit-Fortschrittsanzeige für einen laufenden Import.
 *
 * Verbindet sich via SSE mit dem Backend und zeigt live:
 * - Fortschrittsbalken (Prozent)
 * - Verarbeitete / Gesamt-Dokumente
 * - Vergangene Zeit
 * - Verarbeitungsgeschwindigkeit (Dokumente/Minute)
 * - Aktueller Status
 */

"use client";

import { ProgressEvent } from "@/lib/api";
import { useSSE } from "@/lib/sse";

interface Props {
  batchId: number;
  initialStatus: string;
  initialTotal?: number;
  initialProcessed?: number;
}

/** Formatiert Sekunden als MM:SS oder HH:MM:SS */
function formatDuration(seconds: number): string {
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function ProgressPanel({ batchId, initialStatus, initialTotal = 0, initialProcessed = 0 }: Props) {
  // SSE nur aktiv, wenn Import läuft oder noch nicht begonnen hat
  const shouldStream = initialStatus === "running" || initialStatus === "pending";
  const sseUrl = shouldStream ? `/api/imports/${batchId}/progress` : null;

  const { data, status: sseStatus, error } = useSSE<ProgressEvent>(sseUrl);

  // Anzeige: SSE-Daten oder Fallback auf Initialstatus
  const isRunning = data?.status === "running" || initialStatus === "running";
  const isDone = data?.status === "done" || initialStatus === "done";
  const isError = data?.status === "error" || initialStatus === "error";

  const total = data?.total ?? initialTotal;
  const processed = data?.processed ?? initialProcessed;
  const percent = data?.percent ?? (total > 0 ? Math.round(initialProcessed / initialTotal * 100) : 0);
  const elapsed = data?.elapsed_seconds ?? 0;
  const speed = data?.docs_per_minute ?? 0;

  return (
    <div className="rounded-lg border bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-semibold">Import-Fortschritt</h2>
        {/* Status-Badge */}
        <span
          className={[
            "rounded-full px-3 py-1 text-xs font-medium",
            isRunning ? "bg-blue-100 text-blue-700" : "",
            isDone ? "bg-green-100 text-green-700" : "",
            isError ? "bg-red-100 text-red-700" : "",
            !isRunning && !isDone && !isError ? "bg-gray-100 text-gray-500" : "",
          ].join(" ")}
        >
          {data?.status ?? initialStatus}
        </span>
      </div>

      {/* SSE-Verbindungsfehler */}
      {error && (
        <p className="mb-3 text-sm text-red-500">{error}</p>
      )}

      {/* Fortschrittsbalken */}
      <div className="mb-4">
        <div className="mb-1 flex justify-between text-xs text-gray-500">
          <span>
            {processed} / {total} Dokumente
          </span>
          <span>{percent}%</span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
          <div
            className={[
              "h-3 rounded-full transition-all duration-500",
              isDone ? "bg-green-500" : isError ? "bg-red-400" : "bg-blue-500",
            ].join(" ")}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Statistiken */}
      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="rounded bg-gray-50 p-3">
          <p className="text-2xl font-bold text-gray-800">{processed}</p>
          <p className="text-xs text-gray-500">Verarbeitet</p>
        </div>
        <div className="rounded bg-gray-50 p-3">
          <p className="text-2xl font-bold text-gray-800">{formatDuration(elapsed)}</p>
          <p className="text-xs text-gray-500">Verstrichene Zeit</p>
        </div>
        <div className="rounded bg-gray-50 p-3">
          <p className="text-2xl font-bold text-gray-800">{speed.toFixed(1)}</p>
          <p className="text-xs text-gray-500">Dok./Minute</p>
        </div>
      </div>

      {/* Abschluss-Meldung */}
      {isDone && (
        <p className="mt-4 rounded bg-green-50 px-3 py-2 text-sm text-green-700">
          Import erfolgreich abgeschlossen — {total} Dokumente verarbeitet.
        </p>
      )}
      {isError && (
        <p className="mt-4 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          Import mit Fehlern abgeschlossen. Einzelne Dokumente können Fehler enthalten.
        </p>
      )}
    </div>
  );
}
