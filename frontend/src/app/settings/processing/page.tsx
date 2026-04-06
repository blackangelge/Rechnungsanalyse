"use client";

import { useEffect, useState } from "react";
import { ProcessingSettings, processingSettingsApi } from "@/lib/api";

export default function ProcessingSettingsPage() {
  const [settings, setSettings] = useState<ProcessingSettings | null>(null);
  const [importConcurrency, setImportConcurrency] = useState(10);
  const [aiConcurrency, setAiConcurrency] = useState(4);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await processingSettingsApi.get();
        setSettings(data);
        setImportConcurrency(data.import_concurrency);
        setAiConcurrency(data.ai_concurrency);
      } catch {
        // Standardwerte behalten, Seite bleibt nutzbar
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg(null);
    setErrorMsg(null);
    try {
      const updated = await processingSettingsApi.update({
        import_concurrency: importConcurrency,
        ai_concurrency: aiConcurrency,
      });
      setSettings(updated);
      setSuccessMsg("Einstellungen gespeichert.");
    } catch {
      setErrorMsg("Fehler beim Speichern der Einstellungen.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold text-gray-900">Verarbeitungseinstellungen</h1>
      <p className="mb-6 text-sm text-gray-500">
        Steuert, wie viele Vorgänge gleichzeitig ausgeführt werden.
      </p>

      {successMsg && (
        <div className="mb-4 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700">
          {successMsg}
        </div>
      )}
      {errorMsg && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      {loading ? (
        <div className="py-8 text-center text-sm text-gray-400">Lade Einstellungen…</div>
      ) : (
        <form onSubmit={handleSave} className="space-y-6">

          {/* ── PDF-Import ─────────────────────────────────────────────────── */}
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="mb-1 text-base font-semibold text-gray-800">PDF-Import</h2>
            <p className="mb-5 text-sm text-gray-500">
              Maximale Anzahl gleichzeitig verarbeiteter PDFs beim Import.
              Höhere Werte verkürzen die Importzeit, erhöhen aber die CPU- und
              Festplattenlast auf dem NAS.
            </p>

            <div className="flex items-end gap-6">
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-gray-700">
                  Parallele PDF-Verarbeitung
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={1}
                    max={32}
                    value={importConcurrency}
                    onChange={(e) => setImportConcurrency(Number(e.target.value))}
                    className="w-56 accent-blue-600"
                  />
                  <input
                    type="number"
                    min={1}
                    max={32}
                    value={importConcurrency}
                    onChange={(e) =>
                      setImportConcurrency(
                        Math.max(1, Math.min(32, Number(e.target.value)))
                      )
                    }
                    className="w-20 rounded border border-gray-300 px-3 py-1.5 text-center text-sm font-semibold focus:border-blue-500 focus:outline-none"
                  />
                  <span className="text-sm text-gray-500">von max. 32</span>
                </div>
              </div>
            </div>

            {/* Hinweis-Badges */}
            <div className="mt-4 flex gap-2 flex-wrap">
              {importConcurrency <= 3 && (
                <span className="inline-flex items-center rounded-full bg-yellow-100 px-3 py-1 text-xs font-medium text-yellow-800">
                  Niedrig — langsamer Import, wenig Last
                </span>
              )}
              {importConcurrency >= 4 && importConcurrency <= 10 && (
                <span className="inline-flex items-center rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-800">
                  ✓ Empfohlen für NAS
                </span>
              )}
              {importConcurrency > 10 && (
                <span className="inline-flex items-center rounded-full bg-orange-100 px-3 py-1 text-xs font-medium text-orange-800">
                  Hoch — schnell, aber hohe I/O-Last
                </span>
              )}
            </div>
          </div>

          {/* ── KI-Analyse ─────────────────────────────────────────────────── */}
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="mb-1 text-base font-semibold text-gray-800">KI-Analyse</h2>
            <p className="mb-5 text-sm text-gray-500">
              Maximale Anzahl gleichzeitiger KI-Anfragen. Bei lokalen Modellen
              (LM Studio, Ollama) wird 1–2 empfohlen, da diese meist nur einen
              Request gleichzeitig verarbeiten können.
            </p>

            <div className="flex items-end gap-6">
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-gray-700">
                  Parallele KI-Aufrufe
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={1}
                    max={16}
                    value={aiConcurrency}
                    onChange={(e) => setAiConcurrency(Number(e.target.value))}
                    className="w-56 accent-blue-600"
                  />
                  <input
                    type="number"
                    min={1}
                    max={16}
                    value={aiConcurrency}
                    onChange={(e) =>
                      setAiConcurrency(
                        Math.max(1, Math.min(16, Number(e.target.value)))
                      )
                    }
                    className="w-20 rounded border border-gray-300 px-3 py-1.5 text-center text-sm font-semibold focus:border-blue-500 focus:outline-none"
                  />
                  <span className="text-sm text-gray-500">von max. 16</span>
                </div>
              </div>
            </div>

            {/* Hinweis-Badges */}
            <div className="mt-4 flex gap-2 flex-wrap">
              {aiConcurrency === 1 && (
                <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-800">
                  Sequenziell — ideal für lokale Modelle
                </span>
              )}
              {aiConcurrency >= 2 && aiConcurrency <= 4 && (
                <span className="inline-flex items-center rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-800">
                  ✓ Empfohlen
                </span>
              )}
              {aiConcurrency > 4 && aiConcurrency <= 8 && (
                <span className="inline-flex items-center rounded-full bg-yellow-100 px-3 py-1 text-xs font-medium text-yellow-800">
                  Hoch — nur für externe APIs geeignet
                </span>
              )}
              {aiConcurrency > 8 && (
                <span className="inline-flex items-center rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-800">
                  Sehr hoch — Ratelimits möglich
                </span>
              )}
            </div>
          </div>

          {/* ── Aktuelle Werte (Info) ───────────────────────────────────────── */}
          {settings && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-5 py-3 text-sm text-gray-600">
              <span className="font-medium">Gespeicherte Werte: </span>
              Import {settings.import_concurrency}× parallel · KI {settings.ai_concurrency}× parallel
            </div>
          )}

          {/* ── Speichern ──────────────────────────────────────────────────── */}
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {saving ? "Speichere…" : "Einstellungen speichern"}
            </button>
            <button
              type="button"
              onClick={() => {
                setImportConcurrency(10);
                setAiConcurrency(4);
              }}
              className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
            >
              Auf Standard zurücksetzen (10 / 4)
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
