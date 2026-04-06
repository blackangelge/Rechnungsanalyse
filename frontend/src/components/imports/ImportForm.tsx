"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { importsApi, importSettingsApi } from "@/lib/api";

export default function ImportForm() {
  const router = useRouter();

  const [company, setCompany] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [comment, setComment] = useState("");

  const [importPath, setImportPath] = useState("");
  const [storagePath, setStoragePath] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    importSettingsApi.getPaths()
      .then((p) => { setImportPath(p.import_base_path); setStoragePath(p.storage_path); })
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
      });
      router.push(`/imports/${batch.id}`);
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } };
      setError(axiosError.response?.data?.detail ?? "Fehler beim Starten des Imports");
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
