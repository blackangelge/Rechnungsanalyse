/**
 * Zentraler API-Client für das Rechnungsanalyse-Frontend.
 *
 * Verwendet axios mit einer konfigurierbaren Basis-URL:
 * - Server-seitig (SSR/RSC): vollständige URL über NEXT_PUBLIC_API_URL
 * - Client-seitig (Browser): leere Basis → Next.js-Rewrite-Proxy übernimmt
 *
 * Alle API-Funktionen sind typisiert und geben direkt die Daten zurück (nicht Response).
 */

import axios from "axios";

// Basis-URL: Server nutzt vollständige URL, Browser nutzt den Rewrite-Proxy
const BASE =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "";

/** Globale axios-Instanz mit JSON-Header */
export const apiClient = axios.create({
  baseURL: BASE,
  headers: { "Content-Type": "application/json" },
});

// Array-Parameter ohne Klammern serialisieren: batch_ids=1&batch_ids=2
// (FastAPI erwartet dieses Format, nicht batch_ids[]=1&batch_ids[]=2)
apiClient.defaults.paramsSerializer = (params) => {
  const parts: string[] = [];
  for (const key of Object.keys(params)) {
    const val = params[key];
    if (Array.isArray(val)) {
      val.forEach((v) => parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(v)}`));
    } else if (val !== undefined && val !== null) {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(val)}`);
    }
  }
  return parts.join("&");
};

/**
 * Extrahiert eine lesbare Fehlermeldung aus einem Axios-Fehler.
 * Liest bevorzugt das `detail`-Feld aus der FastAPI-Antwort.
 */
export function extractApiError(err: unknown, fallback = "Unbekannter Fehler"): string {
  if (err && typeof err === "object") {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const detail = e.response?.data?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    const status = e.response?.status;
    if (status === 0 || e.message === "Network Error")
      return "Backend nicht erreichbar — bitte Container-Status prüfen";
    if (status) return `HTTP ${status}: ${fallback}`;
    if (e.message) return e.message;
  }
  return fallback;
}

// ─── Typen: Items (Platzhalter-CRUD) ─────────────────────────────────────────

export interface Item {
  id: number;
  title: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ItemCreate {
  title: string;
  description?: string;
}

export const itemsApi = {
  list: () => apiClient.get<Item[]>("/api/items/").then((r) => r.data),
  get: (id: number) => apiClient.get<Item>(`/api/items/${id}`).then((r) => r.data),
  create: (data: ItemCreate) =>
    apiClient.post<Item>("/api/items/", data).then((r) => r.data),
  update: (id: number, data: Partial<ItemCreate>) =>
    apiClient.put<Item>(`/api/items/${id}`, data).then((r) => r.data),
  delete: (id: number) => apiClient.delete(`/api/items/${id}`),
};

// ─── Typen: KI-Konfigurationen ───────────────────────────────────────────────

export type ReasoningLevel = "off" | "low" | "medium" | "high" | "on";

export interface AIConfig {
  id: number;
  name: string;
  api_url: string;
  api_key: string | null;
  model_name: string;
  is_default: boolean;
  max_tokens: number;
  temperature: number;
  reasoning: ReasoningLevel;
  created_at: string;
  updated_at: string;
}

export interface AIConfigCreate {
  name: string;
  api_url: string;
  api_key?: string;
  model_name: string;
  is_default?: boolean;
  max_tokens?: number;
  temperature?: number;
  reasoning?: ReasoningLevel;
}

export const aiConfigsApi = {
  /** Alle KI-Konfigurationen laden */
  list: () => apiClient.get<AIConfig[]>("/api/ai-configs/").then((r) => r.data),

  /** Einzelne KI-Konfiguration */
  get: (id: number) =>
    apiClient.get<AIConfig>(`/api/ai-configs/${id}`).then((r) => r.data),

  /** Neue Konfiguration erstellen */
  create: (data: AIConfigCreate) =>
    apiClient.post<AIConfig>("/api/ai-configs/", data).then((r) => r.data),

  /** Konfiguration vollständig aktualisieren */
  update: (id: number, data: AIConfigCreate) =>
    apiClient.put<AIConfig>(`/api/ai-configs/${id}`, data).then((r) => r.data),

  /** Konfiguration löschen */
  delete: (id: number) => apiClient.delete(`/api/ai-configs/${id}`),

  /** Als Standard setzen */
  setDefault: (id: number) =>
    apiClient.post<AIConfig>(`/api/ai-configs/${id}/set-default`).then((r) => r.data),
};

// ─── Typen: Import-Batches ────────────────────────────────────────────────────

export interface ImportBatch {
  id: number;
  folder_path: string;
  company_name: string;
  year: number;
  comment: string | null;
  status: "pending" | "running" | "done" | "error";
  total_docs: number;
  processed_docs: number;
  ai_config_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ImportBatchWithDocuments extends ImportBatch {
  documents: DocumentItem[];
}

export interface ImportBatchCreate {
  folder_path: string;
  comment?: string;
  company_name?: string;
  year?: number;
  ai_config_id?: number;
  system_prompt_id?: number;
  analyze_after_import?: boolean;
  delete_source_files?: boolean;
}

export const importsApi = {
  /** Alle Batches laden (optional gefiltert) */
  list: (params?: { company_name?: string; year?: number }) =>
    apiClient.get<ImportBatch[]>("/api/imports/", { params }).then((r) => r.data),

  /** Batch mit Dokumenten laden */
  get: (id: number) =>
    apiClient
      .get<ImportBatchWithDocuments>(`/api/imports/${id}`)
      .then((r) => r.data),

  /** Neuen Import starten */
  create: (data: ImportBatchCreate) =>
    apiClient.post<ImportBatch>("/api/imports/", data).then((r) => r.data),

  /**
   * Nur Status + Metadaten eines Batches laden — OHNE Dokumentliste.
   * Für leichtgewichtiges Polling während eines laufenden Imports.
   */
  getStatus: (id: number) =>
    apiClient.get<ImportBatch>(`/api/imports/${id}/status`).then((r) => r.data),

  /** Import-Batch löschen */
  delete: (id: number) => apiClient.delete(`/api/imports/${id}`),
};

// ─── Typen: Dokumente ─────────────────────────────────────────────────────────

export interface DocumentItem {
  id: number;
  batch_id: number;
  original_filename: string;
  stored_filename: string | null;
  file_size_bytes: number;
  page_count: number;
  company: string;
  year: number;
  comment: string | null;
  status: "pending" | "processing" | "done" | "error";
  error_message: string | null;
  created_at: string;
  deleted_at: string | null;
  /** Kurzfelder aus der Extraktion (nur in der Beleg-Liste) */
  total_amount?: number | null;
  invoice_number?: string | null;
  supplier_name?: string | null;
}

export interface OrderPosition {
  id: number;
  document_id: number;
  position_index: number;
  product_description: string | null;
  article_number: string | null;
  unit_price: number | null;
  total_price: number | null;
  quantity: number | null;
  unit: string | null;
  discount: string | null;
}

export interface InvoiceExtraction {
  id: number;
  document_id: number;
  supplier_name: string | null;
  supplier_address: string | null;
  hrb_number: string | null;
  tax_number: string | null;
  vat_id: string | null;
  bank_name: string | null;
  iban: string | null;
  bic: string | null;
  customer_number: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  total_amount: number | null;
  discount_amount: number | null;
  cash_discount_amount: number | null;
  payment_terms: string | null;
  raw_response: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentItem {
  extraction: InvoiceExtraction | null;
  order_positions: OrderPosition[];
}

export interface DocumentFilter {
  company?: string;
  year?: number;
  status?: string;
  total_min?: number;
  total_max?: number;
  page_min?: number;
  page_max?: number;
  batch_ids?: number[];
  include_deleted?: boolean;
}

export interface AnalyzeRequest {
  document_ids: number[];
  ai_config_id?: number;
  system_prompt_id?: number;
}

export const documentsApi = {
  /** Alle Dokumente laden (optional gefiltert) */
  list: (filters?: DocumentFilter) =>
    apiClient
      .get<DocumentItem[]>("/api/documents/", { params: filters })
      .then((r) => r.data),

  /** Dokument mit Extraktion und Positionen laden */
  get: (id: number) =>
    apiClient.get<DocumentDetail>(`/api/documents/${id}`).then((r) => r.data),

  /** URL zur PDF-Vorschau (für <iframe src=...>) */
  previewUrl: (id: number) => `${BASE}/api/documents/${id}/preview`,

  /** Kommentar aktualisieren */
  updateComment: (id: number, comment: string | null) =>
    apiClient
      .patch<DocumentDetail>(`/api/documents/${id}/comment`, { comment })
      .then((r) => r.data),

  /** Soft-Delete: Dokument als gelöscht markieren (PDF bleibt erhalten) */
  softDelete: (id: number) =>
    apiClient.delete<DocumentDetail>(`/api/documents/${id}`).then((r) => r.data),

  /** Soft-gelöschtes Dokument wiederherstellen */
  restore: (id: number) =>
    apiClient.post<DocumentDetail>(`/api/documents/${id}/restore`).then((r) => r.data),

  /** KI-Analyse für ausgewählte Dokumente starten */
  analyze: (data: AnalyzeRequest) =>
    apiClient
      .post<{ started: number; message: string }>("/api/documents/analyze", data)
      .then((r) => r.data),
};

// ─── Typen: Bildkonvertierungseinstellungen ───────────────────────────────────

export interface ImageSettings {
  id: number;
  dpi: number;
  image_format: "PNG" | "JPEG";
  jpeg_quality: number;
}

export interface ImageSettingsUpdate {
  dpi: number;
  image_format: "PNG" | "JPEG";
  jpeg_quality: number;
}

export const importSettingsApi = {
  getPaths: () =>
    apiClient
      .get<{ import_base_path: string; storage_path: string }>("/api/settings/paths")
      .then((r) => r.data),
};

// ─── Typen: Systemprompts ─────────────────────────────────────────────────────

export interface SystemPrompt {
  id: number;
  name: string;
  content: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemPromptCreate {
  name: string;
  content: string;
  is_default?: boolean;
}

export const systemPromptsApi = {
  list: () =>
    apiClient.get<SystemPrompt[]>("/api/settings/system-prompts").then((r) => r.data),
  create: (data: SystemPromptCreate) =>
    apiClient.post<SystemPrompt>("/api/settings/system-prompts", data).then((r) => r.data),
  update: (id: number, data: SystemPromptCreate) =>
    apiClient.put<SystemPrompt>(`/api/settings/system-prompts/${id}`, data).then((r) => r.data),
  setDefault: (id: number) =>
    apiClient.post<SystemPrompt>(`/api/settings/system-prompts/${id}/set-default`).then((r) => r.data),
  delete: (id: number) => apiClient.delete(`/api/settings/system-prompts/${id}`),
};

export const imageSettingsApi = {
  /** Aktuelle Bildeinstellungen laden */
  get: () =>
    apiClient.get<ImageSettings>("/api/settings/image-conversion").then((r) => r.data),

  /** Bildeinstellungen speichern */
  update: (data: ImageSettingsUpdate) =>
    apiClient
      .put<ImageSettings>("/api/settings/image-conversion", data)
      .then((r) => r.data),
};

// ─── Typen: Verarbeitungseinstellungen ───────────────────────────────────────

export interface ProcessingSettings {
  id: number;
  import_concurrency: number;
  ai_concurrency: number;
}

export interface ProcessingSettingsUpdate {
  import_concurrency: number;
  ai_concurrency: number;
}

export const processingSettingsApi = {
  /** Aktuelle Verarbeitungseinstellungen laden */
  get: () =>
    apiClient
      .get<ProcessingSettings>("/api/settings/processing")
      .then((r) => r.data),

  /** Verarbeitungseinstellungen speichern */
  update: (data: ProcessingSettingsUpdate) =>
    apiClient
      .put<ProcessingSettings>("/api/settings/processing", data)
      .then((r) => r.data),
};

// ─── Typen: Systemlogs ───────────────────────────────────────────────────────

export interface SystemLog {
  id: number;
  category: "import" | "ki" | string;
  level: "info" | "warning" | "error" | string;
  message: string;
  batch_id: number | null;
  document_id: number | null;
  created_at: string;
}

export const logsApi = {
  /** Log-Einträge laden (neueste zuerst) */
  list: (params?: { category?: string; level?: string; limit?: number }) =>
    apiClient.get<SystemLog[]>("/api/logs", { params }).then((r) => r.data),

  /** Alle oder kategoriegefilterte Logs löschen */
  clear: (category?: string) =>
    apiClient
      .delete<{ deleted: number }>("/api/logs", { params: category ? { category } : undefined })
      .then((r) => r.data),
};

// ─── Typen: SSE-Fortschritts-Event ───────────────────────────────────────────

export interface ProgressEvent {
  total: number;
  processed: number;
  percent: number;
  elapsed_seconds: number;
  docs_per_minute: number;
  status: string;
  message?: string;
}
