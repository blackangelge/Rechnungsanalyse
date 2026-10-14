"use client";

import { useCallback, useEffect, useState } from "react";
import MergeModal from "@/components/suppliers/MergeModal";
import {
  DuplicateGroup, Supplier, SupplierMergeResult, SupplierUpdate, WorkflowListItem,
  suppliersApi, workflowsApi, extractApiError,
} from "@/lib/api";

function SupplierEditModal({
  supplier,
  onSaved,
  onCancel,
}: {
  supplier: Supplier;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<SupplierUpdate>({
    name: supplier.name,
    street: supplier.street ?? "",
    zip_code: supplier.zip_code ?? "",
    city: supplier.city ?? "",
    address: supplier.address ?? "",
    hrb_number: supplier.hrb_number ?? "",
    tax_number: supplier.tax_number ?? "",
    vat_id: supplier.vat_id ?? "",
    bank_name: supplier.bank_name ?? "",
    iban: supplier.iban ?? "",
    bic: supplier.bic ?? "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setLoading(true);
    setError(null);
    try {
      await suppliersApi.update(supplier.id, form);
      onSaved();
    } catch (err) {
      setError(extractApiError(err, "Fehler beim Speichern"));
    } finally {
      setLoading(false);
    }
  }

  function field(label: string, key: keyof SupplierUpdate) {
    return (
      <div>
        <label className="mb-1 block text-xs font-medium text-gray-600">{label}</label>
        <input
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          value={(form[key] as string) ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-base font-semibold text-gray-900">
          Lieferant bearbeiten — {supplier.name}
        </h2>
        {error && <p className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
        <div className="space-y-3">
          {field("Name *", "name")}
          <div className="grid grid-cols-2 gap-3">
            {field("Straße + Hausnummer", "street")}
            {field("PLZ", "zip_code")}
          </div>
          {field("Stadt", "city")}
          <div className="grid grid-cols-2 gap-3">
            {field("USt-IdNr.", "vat_id")}
            {field("Steuernummer", "tax_number")}
          </div>
          {field("HRB-Nummer", "hrb_number")}
          <div className="grid grid-cols-3 gap-3">
            {field("Bank", "bank_name")}
            {field("IBAN", "iban")}
            {field("BIC", "bic")}
          </div>
        </div>
        <div className="mt-5 flex gap-3">
          <button
            onClick={handleSave}
            disabled={loading}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Speichern..." : "Speichern"}
          </button>
          <button
            onClick={onCancel}
            className="rounded border px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            Abbrechen
          </button>
        </div>
      </div>
    </div>
  );
}

export default function LieferantenPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editSupplier, setEditSupplier] = useState<Supplier | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateGroup[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [mergeSuppliers, setMergeSuppliers] = useState<Supplier[] | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [dupeLoading, setDupeLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);

  useEffect(() => {
    workflowsApi.list().then(setWorkflows).catch(() => { /* Spalte bleibt ohne Auswahl nutzbar */ });
  }, []);

  async function handleWorkflowChange(supplierId: number, value: string) {
    try {
      const updated = await suppliersApi.setWorkflow(supplierId, value ? Number(value) : null);
      setSuppliers((prev) => prev.map((s) => (s.id === supplierId ? { ...s, workflow_id: updated.workflow_id } : s)));
    } catch (err) {
      setError(extractApiError(err, "Workflow konnte nicht zugewiesen werden"));
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await suppliersApi.list();
      setSuppliers(data);
    } catch (err) {
      setError(extractApiError(err, "Fehler beim Laden der Lieferanten"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleDelete(id: number) {
    try {
      await suppliersApi.delete(id);
      setDeleteConfirm(null);
      await load();
    } catch (err) {
      setError(extractApiError(err, "Fehler beim Löschen"));
    }
  }

  function toggleSelected(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function handleMerged(result: SupplierMergeResult) {
    setMergeSuppliers(null);
    setSelected(new Set());
    setSuccessMsg(
      `${result.merged_ids.length} Lieferant(en) in „${result.supplier.name}" zusammengeführt — ` +
      `${result.moved_documents} Beleg(e) umgehängt` +
      (result.renamed_documents ? `, ${result.renamed_documents} Name(n) vereinheitlicht.` : "."),
    );
    await load();
    if (duplicates !== null) {          // Dublettenliste aktuell halten
      try { setDuplicates(await suppliersApi.duplicateGroups()); } catch { /* bleibt sichtbar */ }
    }
  }

  async function handleFindDuplicates() {
    setDupeLoading(true);
    setSuccessMsg(null);
    try {
      const groups = await suppliersApi.duplicateGroups();
      setDuplicates(groups);
    } catch (err) {
      setError(extractApiError(err, "Fehler bei Duplikatsuche"));
    } finally {
      setDupeLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Lieferanten</h1>
          <p className="mt-1 text-sm text-gray-500">{suppliers.length} Lieferant(en)</p>
        </div>
        <button
          onClick={handleFindDuplicates}
          disabled={dupeLoading}
          className="rounded bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {dupeLoading ? "Suche..." : "🔍 Dubletten suchen"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
      )}
      {successMsg && (
        <div className="mb-4 rounded bg-green-50 px-4 py-3 text-sm text-green-700" data-testid="merge-success">{successMsg}</div>
      )}

      {/* Dubletten-Anzeige */}
      {duplicates !== null && (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4" data-testid="duplicates-panel">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-amber-800">
              {duplicates.length === 0
                ? "✓ Keine Dubletten gefunden"
                : `⚠ ${duplicates.length} Dublettengruppe(n) gefunden`}
            </h2>
            <button onClick={() => setDuplicates(null)} className="text-xs text-amber-600 hover:underline">
              Schließen
            </button>
          </div>
          {duplicates.length > 0 && (
            <p className="mb-3 text-xs text-amber-700">
              Verglichen werden IBAN, USt-IdNr., Steuernummer und Name (ohne Rechtsform, auch ähnliche Schreibweisen).
              Es wird nichts automatisch zusammengeführt — du entscheidest je Gruppe.
            </p>
          )}
          {duplicates.map((group, gi) => {
            const conf = {
              high: { label: "sehr wahrscheinlich", cls: "bg-red-100 text-red-700" },
              medium: { label: "wahrscheinlich", cls: "bg-amber-200 text-amber-900" },
              low: { label: "möglich", cls: "bg-gray-200 text-gray-700" },
            }[group.confidence];
            return (
              <div key={gi} className="mb-3 rounded border border-amber-300 bg-white p-3" data-testid="duplicate-group">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium text-amber-700">Gruppe {gi + 1}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${conf.cls}`}>{conf.label}</span>
                  {group.reason_labels.map((l) => (
                    <span key={l} className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">{l}</span>
                  ))}
                  <button
                    onClick={() => setMergeSuppliers(group.suppliers)}
                    className="ml-auto rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700"
                  >
                    Zusammenführen…
                  </button>
                </div>
                <div className="space-y-1">
                  {group.suppliers.map((s) => (
                    <div key={s.id} className="flex items-center justify-between text-sm">
                      <span>
                        <strong>#{s.id}</strong> {s.name} —{" "}
                        {[s.street, s.zip_code, s.city].filter(Boolean).join(", ") || s.address || "—"}
                        {s.iban ? ` • ${s.iban}` : ""} • {s.document_count} Beleg(e)
                      </span>
                      <button
                        onClick={() => setEditSupplier(s)}
                        className="ml-3 rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700 hover:bg-blue-200"
                      >
                        Bearbeiten
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Mehrfachauswahl → manuell zusammenführen */}
      {selected.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5" data-testid="selection-bar">
          <span className="text-sm font-medium text-blue-800">{selected.size} Lieferant(en) ausgewählt</span>
          <button
            onClick={() => setMergeSuppliers(suppliers.filter((s) => selected.has(s.id)))}
            disabled={selected.size < 2}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
          >
            Zusammenführen…
          </button>
          {selected.size < 2 && <span className="text-xs text-blue-700">Wähle mindestens zwei aus.</span>}
          <button onClick={() => setSelected(new Set())} className="ml-auto text-xs text-blue-700 hover:underline">Auswahl aufheben</button>
        </div>
      )}

      {/* Tabelle */}
      {loading ? (
        <p className="text-sm text-gray-500">Lade Lieferanten...</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="w-8 px-3 py-3"></th>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Straße</th>
                <th className="px-4 py-3 text-left">PLZ</th>
                <th className="px-4 py-3 text-left">Stadt</th>
                <th className="px-4 py-3 text-left">Bank</th>
                <th className="px-4 py-3 text-left">IBAN</th>
                <th className="px-4 py-3 text-left">BIC</th>
                <th className="px-4 py-3 text-center">Belege</th>
                <th className="px-4 py-3 text-left" title="Analyse-Ablauf (Workflow) für diesen Lieferanten">Workflow</th>
                <th className="px-4 py-3 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {suppliers.length === 0 && (
                <tr>
                  <td colSpan={11} className="px-4 py-6 text-center text-gray-400">
                    Noch keine Lieferanten vorhanden. Starte eine KI-Analyse um Lieferanten zu extrahieren.
                  </td>
                </tr>
              )}
              {suppliers.map((s) => (
                <tr key={s.id} className={selected.has(s.id) ? "bg-blue-50" : "hover:bg-gray-50"}>
                  <td className="px-3 py-3">
                    <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSelected(s.id)}
                      aria-label={`${s.name} auswählen`} className="rounded border-gray-300 text-blue-600" />
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">{s.name}</td>
                  <td className="px-4 py-3 text-gray-600">{s.street ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{s.zip_code ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{s.city ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{s.bank_name ?? "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{s.iban ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{s.bic ?? "—"}</td>
                  <td className="px-4 py-3 text-center">
                    <span className="inline-block rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                      {s.document_count}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={s.workflow_id ?? ""}
                      onChange={(e) => handleWorkflowChange(s.id, e.target.value)}
                      aria-label={`Workflow für ${s.name}`}
                      className={`w-44 rounded border px-2 py-1 text-xs focus:border-blue-500 focus:outline-none ${
                        s.workflow_id ? "border-blue-300 bg-blue-50 text-blue-800" : "border-gray-300 text-gray-500"
                      }`}
                    >
                      <option value="">Standard</option>
                      {workflows.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setEditSupplier(s)}
                        className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700"
                      >
                        Bearbeiten
                      </button>
                      {deleteConfirm === s.id ? (
                        <>
                          <button
                            onClick={() => handleDelete(s.id)}
                            className="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700"
                          >
                            Bestätigen
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(null)}
                            className="rounded border px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
                          >
                            Abbrechen
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirm(s.id)}
                          className="rounded border border-red-300 px-3 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                        >
                          Löschen
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {mergeSuppliers && (
        <MergeModal
          suppliers={mergeSuppliers}
          onClose={() => setMergeSuppliers(null)}
          onMerged={handleMerged}
        />
      )}

      {editSupplier && (
        <SupplierEditModal
          supplier={editSupplier}
          onSaved={async () => {
            setEditSupplier(null);
            await load();
          }}
          onCancel={() => setEditSupplier(null)}
        />
      )}
    </main>
  );
}
