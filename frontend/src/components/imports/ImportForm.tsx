"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AIConfig, aiConfigsApi, extractApiError, importsApi, importSettingsApi, SystemPrompt, systemPromptsApi } from "@/lib/api";

export default function ImportForm() {
  const router = useRouter();

  const [company, setCompany] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [comment, setComment] = useState("");

  const [importPath, setImportPath] = useState("");
  const [storagePath, setStoragePath] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // KI-Analyse nach Import
  const [analyzeAfterImport, setAnalyzeAfterImport] = useState(false);
  const [aiConfigs, setAiConfigs] = useState<AIConfig[]>([]);
  const [selectedAiConfigId, setSelectedAiConfigId] = useState<string>("");
  const [systemPrompts, setSystemPrompts] = useState<SystemPrompt[]>([]);
  const [selectedSystemPromptId, setSelectedSystemPromptId] = useState<string>("");

  // Import-Optionen
  const [deleteSourceFiles, setDeleteSourceFiles] = useState(false);

  useEffect(() => {
    importSettingsApi.getPaths()
      .then((p) => { setImportPath(p.import_base_path); setStoragePath(p.storage_path); })
      .catch(() => {});
    aiConfigsApi.list()
      .then((configs) => {
        setAiConfigs(configs);
        const def = configs.find((c) => c.is_default);
        if (def) setSelectedAiConfigId(String(def.id));
      })
      .catch(() => {});
    systemPromptsApi.list()
      .then((prompts) => {
        setSystemPrompts(prompts);
        const def = prompts.find((p) => p.is_default);
        if (def) setSelectedSystemPromptId(String(def.id));
      })
      .catch(() => {});
  }, []);

  const storagePreview = company.trim() && year.trim()
    ? `${company.trim()}_${year.trim()}`
    : null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const batch = await importsApi.create({
        folder_path: "",
        company_name: company.trim(),
        year: parseInt(year),
        comment: comment || undefined,
        analyze_after_import: analyzeAfterImport,
        ai_config_id: analyzeAfterImport && selectedAiConfigId ? parseInt(selectedAiConfigId) : undefined,
        system_prompt_id: analyzeAfterImport && selectedSystemPromptId ? parseInt(selectedSystemPromptId) : undefined,
        delete_source_files: deleteSourceFiles,
      });
      router.push(`/imports/${batch.id}`);
    } catch (err: unknown) {
      setError(extractApiError(err, "Fehler beim Starten des Imports"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6 rounded-lg border bg-white p-6 shadow-sm">
      <h2 className="text-base font-semibold">Import-Einstellungen</h2>

      {error && (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
      )}

      <div className="flex gap-4">
        <div className="flex-1">
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Firmenname <span className="text-red-500">*</span>
          </label>
          <input
            className="input"
            placeholder="z.B. Lieferant GmbH"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            required
          />
        </div>
        <div className="w-32">
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Jahr <span className="text-red-500">*</span>
          </label>
          <input
            className="input"
            placeholder="2025"
            value={year}
            onChange={(e) => setYear(e.target.value)}
            required
            pattern="\d{4}"
            inputMode="numeric"
            maxLength={4}
          />
        </div>
      </div>

      {storagePreview && (
        <div className="space-y-1 rounded bg-gray-50 px-3 py-2 text-xs text-gray-500">
          <div>
            <span className="font-medium">Quelle:</span>{" "}
            <span className="font-mono">{importPath || "…"}</span>
          </div>
          <div>
            <span className="font-medium">Ziel:</span>{" "}
            <span className="font-mono">{storagePath || "…"}/{storagePreview}/</span>
          </div>
        </div>
      )}

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Kommentar (optional)
        </label>
        <textarea
          className="input"
          placeholder="Notizen zu diesem Import..."
          rows={2}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </div>

      {/* Import-Optionen */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Import-Optionen</p>

        {/* Quelldateien löschen */}
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={deleteSourceFiles}
            onChange={(e) => setDeleteSourceFiles(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
          />
          <div>
            <span className="text-sm font-medium text-gray-800">Quelldateien nach Import löschen</span>
            <p className="text-xs text-gray-500 mt-0.5">
              Die Original-PDFs werden aus dem Import-Ordner gelöscht, sobald sie erfolgreich kopiert wurden.
            </p>
          </div>
        </label>

        {/* KI-Analyse nach Import */}
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={analyzeAfterImport}
            onChange={(e) => setAnalyzeAfterImport(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <div>
            <span className="text-sm font-medium text-gray-800">Dokumente direkt an KI senden</span>
            <p className="text-xs text-gray-500 mt-0.5">
              Nach Abschluss des Imports wird automatisch die KI-Analyse für alle Dokumente gestartet.
            </p>
          </div>
        </label>

        {analyzeAfterImport && (
          <div className="pl-7 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">KI-Konfiguration</label>
              <select
                value={selectedAiConfigId}
                onChange={(e) => setSelectedAiConfigId(e.target.value)}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
              >
                <option value="">Standard-Konfiguration</option>
                {aiConfigs.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}{c.is_default ? " (Standard)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Systemprompt</label>
              <select
                value={selectedSystemPromptId}
                onChange={(e) => setSelectedSystemPromptId(e.target.value)}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
              >
                <option value="">Standard-Prompt</option>
                {systemPrompts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.is_default ? " (Standard)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={loading || !company.trim() || !year.trim()}
        className="rounded bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Starte Import..." : "Import starten"}
      </button>
    </form>
  );
}
