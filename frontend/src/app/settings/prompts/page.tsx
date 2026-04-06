/**
 * Seite: Systemprompts verwalten (/settings/prompts)
 *
 * Systemprompts werden der KI als Systemanweisung mitgegeben,
 * wenn Dokumente zur Rechnungserkennung gesendet werden.
 */

"use client";

import { useEffect, useState } from "react";
import { SystemPrompt, systemPromptsApi } from "@/lib/api";

export default function SystemPromptsPage() {
  const [prompts, setPrompts] = useState<SystemPrompt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Formular-Zustand
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [formName, setFormName] = useState("");
  const [formContent, setFormContent] = useState("");
  const [formDefault, setFormDefault] = useState(false);
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      setError(null);
      const data = await systemPromptsApi.list();
      setPrompts(data);
    } catch {
      setError("Fehler beim Laden der Systemprompts");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function openNew() {
    setEditingId("new");
    setFormName("");
    setFormContent("");
    setFormDefault(prompts.length === 0);
  }

  function openEdit(p: SystemPrompt) {
    setEditingId(p.id);
    setFormName(p.name);
    setFormContent(p.content);
    setFormDefault(p.is_default);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function save() {
    if (!formName.trim() || !formContent.trim()) return;
    setSaving(true);
    try {
      if (editingId === "new") {
        await systemPromptsApi.create({ name: formName, content: formContent, is_default: formDefault });
      } else if (editingId !== null) {
        await systemPromptsApi.update(editingId, { name: formName, content: formContent, is_default: formDefault });
      }
      setEditingId(null);
      await load();
    } catch {
      alert("Fehler beim Speichern");
    } finally {
      setSaving(false);
    }
  }

  async function setDefault(id: number) {
    try {
      await systemPromptsApi.setDefault(id);
      await load();
    } catch {
      alert("Fehler beim Setzen des Standards");
    }
  }

  async function remove(id: number) {
    if (!confirm("Systemprompt löschen?")) return;
    try {
      await systemPromptsApi.delete(id);
      await load();
    } catch {
      alert("Fehler beim Löschen");
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Systemprompts</h1>
          <p className="text-sm text-gray-500">
            Systemanweisungen, die bei der KI-Extraktion mitgesendet werden.
          </p>
        </div>
        <button
          onClick={openNew}
          disabled={editingId !== null}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          + Neuer Prompt
        </button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {loading && <p className="text-sm text-gray-500">Lade...</p>}

      {/* Formular */}
      {editingId !== null && (
        <div className="rounded-lg border bg-white p-5 shadow-sm space-y-4">
          <h2 className="text-sm font-semibold">
            {editingId === "new" ? "Neuer Systemprompt" : "Systemprompt bearbeiten"}
          </h2>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Name</label>
            <input
              className="input"
              placeholder="z.B. Rechnungsextraktion Standard"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Prompt-Inhalt</label>
            <textarea
              className="input font-mono text-xs"
              rows={10}
              placeholder="Du bist ein Experte für die Analyse von Rechnungen..."
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={formDefault}
              onChange={(e) => setFormDefault(e.target.checked)}
            />
            Als Standard verwenden
          </label>
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={saving || !formName.trim() || !formContent.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Speichern..." : "Speichern"}
            </button>
            <button
              onClick={cancelEdit}
              className="rounded border px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {/* Liste */}
      {prompts.length === 0 && !loading ? (
        <div className="rounded-lg border bg-white p-8 text-center text-sm text-gray-400">
          Noch keine Systemprompts vorhanden.
        </div>
      ) : (
        <div className="space-y-3">
          {prompts.map((p) => (
            <div key={p.id} className="rounded-lg border bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-800">{p.name}</span>
                    {p.is_default && (
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                        Standard
                      </span>
                    )}
                  </div>
                  <pre className="mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-600 font-mono">
                    {p.content}
                  </pre>
                </div>
                <div className="flex shrink-0 gap-2">
                  {!p.is_default && (
                    <button
                      onClick={() => setDefault(p.id)}
                      className="rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
                    >
                      Standard
                    </button>
                  )}
                  <button
                    onClick={() => openEdit(p)}
                    disabled={editingId !== null}
                    className="rounded px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 disabled:opacity-40"
                  >
                    Bearbeiten
                  </button>
                  <button
                    onClick={() => remove(p.id)}
                    className="rounded px-2 py-1 text-xs text-red-500 hover:bg-red-50"
                  >
                    Löschen
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
