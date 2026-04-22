/**
 * Seite: KI-Konfigurationen verwalten (/settings/ai)
 *
 * Zeigt eine Liste aller konfigurierten Vision-LLM-APIs und erlaubt:
 * - Neue Konfiguration erstellen
 * - Bestehende Konfiguration bearbeiten
 * - Konfiguration löschen
 * - Konfiguration als Standard setzen
 */

"use client";

import { useEffect, useState } from "react";
import { AIConfig, aiConfigsApi, extractApiError } from "@/lib/api";
import AIConfigForm from "@/components/settings/AIConfigForm";

export default function AISettingsPage() {
  const [configs, setConfigs] = useState<AIConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Zeigt das Formular: undefined = neues Erstellen, AIConfig = Bearbeiten
  const [editTarget, setEditTarget] = useState<AIConfig | undefined | null>(null);

  /** Konfigurationen vom Server laden */
  async function load() {
    try {
      setError(null);
      const data = await aiConfigsApi.list();
      setConfigs(data);
    } catch (err) {
      setError(extractApiError(err, "Fehler beim Laden der KI-Konfigurationen"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  /** Konfiguration löschen */
  async function handleDelete(config: AIConfig) {
    if (!confirm(`"${config.name}" wirklich löschen?`)) return;
    try {
      await aiConfigsApi.delete(config.id);
      await load();
    } catch (err) {
      alert(extractApiError(err, "Fehler beim Löschen"));
    }
  }

  /** Als Standard setzen */
  async function handleSetDefault(config: AIConfig) {
    try {
      await aiConfigsApi.setDefault(config.id);
      await load();
    } catch (err) {
      alert(extractApiError(err, "Fehler beim Setzen des Standards"));
    }
  }

  /** Konfiguration duplizieren */
  async function handleCopy(config: AIConfig) {
    try {
      await aiConfigsApi.create({
        name: `Kopie von ${config.name}`,
        api_url: config.api_url,
        api_key: config.api_key ?? undefined,
        model_name: config.model_name,
        max_tokens: config.max_tokens,
        temperature: config.temperature,
        reasoning: config.reasoning,
        endpoint_type: config.endpoint_type,
      });
      await load();
    } catch (err) {
      alert(extractApiError(err, "Fehler beim Kopieren der Konfiguration"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">KI-Konfigurationen</h1>
        {/* Formular anzeigen, falls noch nicht geöffnet */}
        {editTarget === null && (
          <button
            onClick={() => setEditTarget(undefined)}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            + Neue Konfiguration
          </button>
        )}
      </div>

      {/* Formular: Erstellen oder Bearbeiten */}
      {editTarget !== null && (
        <AIConfigForm
          initialData={editTarget}
          onSaved={() => {
            setEditTarget(null);
            load();
          }}
          onCancel={() => setEditTarget(null)}
        />
      )}

      {/* Lade- und Fehlerzustand */}
      {loading && <p className="text-sm text-gray-500">Lade...</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Konfigurationsliste */}
      {!loading && configs.length === 0 && !error && (
        <p className="text-sm text-gray-500">
          Noch keine KI-Konfigurationen vorhanden. Erstelle eine oben.
        </p>
      )}

      <div className="space-y-3">
        {configs.map((config) => (
          <div
            key={config.id}
            className="flex items-start justify-between rounded-lg border bg-white p-4 shadow-sm"
          >
            <div>
              <div className="flex items-center gap-2">
                <p className="font-medium">{config.name}</p>
                {/* Standard-Badge */}
                {config.is_default && (
                  <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                    Standard
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-gray-500">
                <span className="font-mono">{config.model_name}</span>
                {" · "}
                <span className="text-gray-400">{config.api_url}</span>
              </p>
              <p className="mt-0.5 text-xs text-gray-400">
                Max. Tokens: {config.max_tokens} · Temperatur: {config.temperature} · Reasoning: {config.reasoning ?? "off"}
              </p>
            </div>

            {/* Aktionsbuttons */}
            <div className="flex gap-2">
              {!config.is_default && (
                <button
                  onClick={() => handleSetDefault(config)}
                  className="rounded px-2 py-1 text-xs text-blue-600 hover:bg-blue-50"
                >
                  Als Standard
                </button>
              )}
              <button
                onClick={() => setEditTarget(config)}
                className="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
              >
                Bearbeiten
              </button>
              <button
                onClick={() => handleCopy(config)}
                className="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
              >
                Kopieren
              </button>
              <button
                onClick={() => handleDelete(config)}
                className="rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
              >
                Löschen
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
