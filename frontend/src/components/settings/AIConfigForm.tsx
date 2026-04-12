/**
 * Formular zum Erstellen und Bearbeiten einer KI-Konfiguration.
 *
 * Wird sowohl für das Erstellen (kein initialData) als auch für das
 * Bearbeiten (mit initialData) einer Konfiguration verwendet.
 */

"use client";

import { useState } from "react";
import { AIConfig, AIConfigCreate, aiConfigsApi, ReasoningLevel } from "@/lib/api";

interface Props {
  /** Vorhandene Konfiguration zum Bearbeiten (undefined = neue Konfiguration) */
  initialData?: AIConfig;
  /** Callback nach erfolgreichem Speichern */
  onSaved: () => void;
  /** Callback zum Abbrechen */
  onCancel: () => void;
}

export default function AIConfigForm({ initialData, onSaved, onCancel }: Props) {
  // Formularfelder — initialisiert mit vorhandenen Daten oder Standardwerten
  const [name, setName] = useState(initialData?.name ?? "");
  const [apiUrl, setApiUrl] = useState(initialData?.api_url ?? "http://localhost:1234/v1");
  const [apiKey, setApiKey] = useState(initialData?.api_key ?? "");
  const [modelName, setModelName] = useState(initialData?.model_name ?? "");
  const [isDefault, setIsDefault] = useState(initialData?.is_default ?? false);
  const [maxTokens, setMaxTokens] = useState(initialData?.max_tokens ?? 2048);
  const [temperature, setTemperature] = useState(initialData?.temperature ?? 0.1);
  const [reasoning, setReasoning] = useState<ReasoningLevel>(initialData?.reasoning ?? "off");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const data: AIConfigCreate = {
      name,
      api_url: apiUrl,
      api_key: apiKey || undefined,
      model_name: modelName,
      is_default: isDefault,
      max_tokens: maxTokens,
      temperature,
      reasoning,
    };

    try {
      if (initialData) {
        // Bestehende Konfiguration aktualisieren
        await aiConfigsApi.update(initialData.id, data);
      } else {
        // Neue Konfiguration erstellen
        await aiConfigsApi.create(data);
      }
      onSaved();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unbekannter Fehler";
      setError(`Fehler beim Speichern: ${msg}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 rounded-lg border bg-white p-6 shadow-sm"
    >
      <h2 className="text-base font-semibold">
        {initialData ? "Konfiguration bearbeiten" : "Neue KI-Konfiguration"}
      </h2>

      {error && (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
      )}

      {/* Anzeigename */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Name <span className="text-red-500">*</span>
        </label>
        <input
          className="input"
          placeholder="z.B. LM Studio - LLaVA 1.5"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>

      {/* API-URL */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          API-URL <span className="text-red-500">*</span>
        </label>
        <input
          className="input"
          placeholder="http://localhost:1234/v1"
          value={apiUrl}
          onChange={(e) => setApiUrl(e.target.value)}
          required
        />
        <p className="mt-1 text-xs text-gray-400">
          Basis-URL ohne /chat/completions (OpenAI-kompatibel)
        </p>
      </div>

      {/* Modell-Name */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Modell-ID <span className="text-red-500">*</span>
        </label>
        <input
          className="input"
          placeholder="z.B. llava-1.5-7b-hf"
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          required
        />
      </div>

      {/* API-Key (optional) */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          API-Schlüssel (optional)
        </label>
        <input
          className="input"
          type="password"
          placeholder="Für lokale APIs meist nicht benötigt"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
      </div>

      {/* Erweiterte Einstellungen */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Max. Tokens
          </label>
          <input
            className="input"
            type="number"
            min={256}
            max={32000}
            value={maxTokens}
            onChange={(e) => setMaxTokens(parseInt(e.target.value))}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Temperatur (0–1)
          </label>
          <input
            className="input"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
          />
        </div>
      </div>

      {/* Reasoning */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Reasoning
        </label>
        <select
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value as ReasoningLevel)}
          className="rounded border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none w-full"
        >
          <option value="off">off — deaktiviert (Standard)</option>
          <option value="low">low — gering</option>
          <option value="medium">medium — mittel</option>
          <option value="high">high — hoch</option>
          <option value="on">on — maximal</option>
        </select>
        <p className="mt-1 text-xs text-gray-400">
          Wird als <span className="font-mono">reasoning_effort</span> an die API übergeben. Nur von bestimmten Modellen unterstützt.
        </p>
      </div>

      {/* Standard-Konfiguration */}
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isDefault}
          onChange={(e) => setIsDefault(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300"
        />
        Als Standard für neue Imports verwenden
      </label>

      {/* Aktionsbuttons */}
      <div className="flex gap-3 pt-2">
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Speichern..." : "Speichern"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          Abbrechen
        </button>
      </div>
    </form>
  );
}
