"use client";

import { useCallback, useEffect, useState } from "react";
import { Supplier, SupplierUpdate, suppliersApi, extractApiError } from "@/lib/api";

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
  const [duplicates, setDuplicates] = useState<Supplier[][] | null>(null);
  const [dupeLoading, setDupeLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

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

  async function handleFindDuplicates() {
    setDupeLoading(true);
    try {
      const groups = await suppliersApi.duplicates();
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
          {dupeLoading ? "Suche..." : "🔍 Duplikate suchen"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
      )}

      {/* Duplikate-Anzeige */}
      {duplicates !== null && (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-amber-800">
              {duplicates.length === 0
                ? "✓ Keine Duplikate gefunden"
                : `⚠ ${duplicates.length} Duplikatgruppe(n) gefunden`}
            </h2>
            <button onClick={() => setDuplicates(null)} className="text-xs text-amber-600 hover:underline">
              Schließen
            </button>
          </div>
          {duplicates.map((group, gi) => (
            <div key={gi} className="mb-3 rounded border border-amber-300 bg-white p-3">
              <p className="mb-2 text-xs font-medium text-amber-700">Duplikatgruppe {gi + 1}:</p>
              <div className="space-y-1">
                {group.map((s) => (
                  <div key={s.id} className="flex items-center justify-between text-sm">
                    <span>
                      <strong>#{s.id}</strong> {s.name} —{" "}
                      {[s.street, s.zip_code, s.city].filter(Boolean).join(", ") || s.address || "—"}{" "}
                      • {s.document_count} Beleg(e)
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
          ))}
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
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Straße</th>
                <th className="px-4 py-3 text-left">PLZ</th>
                <th className="px-4 py-3 text-left">Stadt</th>
                <th className="px-4 py-3 text-left">Bank</th>
                <th className="px-4 py-3 text-left">IBAN</th>
                <th className="px-4 py-3 text-left">BIC</th>
                <th className="px-4 py-3 text-center">Belege</th>
                <th className="px-4 py-3 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {suppliers.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-6 text-center text-gray-400">
                    Noch keine Lieferanten vorhanden. Starte eine KI-Analyse um Lieferanten zu extrahieren.
                  </td>
                </tr>
              )}
              {suppliers.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50">
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
