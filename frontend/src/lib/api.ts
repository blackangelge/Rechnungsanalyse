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
  timeout: 30000, // 30 Sekunden Timeout — verhindert ewiges Hängen bei Netzwerkproblemen
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
export type EndpointType = "openai" | "lmstudio";

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
  endpoint_type: EndpointType;
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
  endpoint_type?: EndpointType;
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

export interface BatchKiStats {
  total_input_tokens: number;
  total_output_tokens: number;
  total_duration_seconds: number;
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

  /** Aggregierte KI-Statistiken (Token-Summen + Gesamtdauer) für einen Import-Batch */
  kiStats: (id: number) =>
    apiClient.get<BatchKiStats>(`/api/imports/${id}/ki-stats`).then((r) => r.data),

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
  /** Aktuelle PDF-Version (1 = Original) und Version, auf der die letzte KI-Analyse lief */
  pdf_version?: number;
  analyzed_pdf_version?: number | null;
  /** Kurzfelder aus der Extraktion (nur in der Beleg-Liste) */
  total_amount?: number | null;
  invoice_number?: string | null;
  supplier_name?: string | null;
  /** True wenn eine KI-Extraktion für dieses Dokument existiert */
  has_extraction?: boolean;
  /** KI-Laufzeitstatistiken (direkt aus der Extraktion) */
  ki_input_tokens?: number | null;
  ki_output_tokens?: number | null;
  ki_total_duration?: number | null;
  /** Erkannter Dokumententyp (durch KI-Klassifikation) */
  document_type_id?: number | null;
  document_type_name?: string | null;
  /** Ergebnis der Plausibilitätsprüfung (nur bei Eingangsrechnungen) */
  validation_status?: ValidationStatus | null;
}

/** ok = plausibel · corrected = automatisch korrigiert · ai_corrected = durch zweite
 *  KI-Abfrage korrigiert · needs_review = manuelle Prüfung nötig · manual_ok = vom
 *  Nutzer bestätigt · unchecked = nichts prüfbar */
export type ValidationStatus =
  | "ok" | "corrected" | "ai_corrected" | "needs_review" | "manual_ok" | "unchecked";

export interface ValidationIssue {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  /** 0-basierter Positionsindex (null = betrifft die ganze Rechnung) */
  position: number | null;
  details: Record<string, unknown>;
}

export interface ValidationCorrection {
  position: number;
  field: string;
  from: number;
  to: number;
  factor: number;
  method: string;
}

export interface ValidationDetails {
  status: ValidationStatus;
  method?: "rules" | "ai_recheck";
  issues: ValidationIssue[];
  corrections: ValidationCorrection[];
  checks_run: number;
  confirmed_manually?: boolean;
  recheck?: {
    performed: boolean;
    outcome?: "corrected" | "still_inconsistent" | "failed";
    issues_before?: ValidationIssue[];
    issues_after?: ValidationIssue[];
    error?: string;
  };
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
  // KI-Statistiken
  ki_input_tokens?: number | null;
  ki_output_tokens?: number | null;
  ki_total_duration?: number | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentItem {
  extraction: InvoiceExtraction | null;
  order_positions: OrderPosition[];
  validation?: ValidationDetails | null;
  /** Wortlaut der bei der Analyse verwendeten Systemprompts */
  used_system_prompt?: string | null;
  used_doc_type_prompt?: string | null;
  used_recheck_prompt?: string | null;
  /** Bei der letzten Analyse verwendeter Workflow (Name, Graph-Snapshot) + Ablaufprotokoll */
  used_workflow_id?: number | null;
  used_workflow_name?: string | null;
  used_workflow?: WorkflowGraph | null;
  workflow_run?: WorkflowTraceEntry[] | null;
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
  has_extraction?: boolean;
  supplier_name?: string;
  doc_id?: number;
  document_type_ids?: number[];
  validation_status?: ValidationStatus[];
}

/** Eine gespeicherte PDF-Version (Original = 1, danach manuell/auto/restore) */
export interface DocumentVersion {
  /** null = Original, das noch nie bearbeitet wurde (noch nicht gespeichert) */
  id: number | null;
  version_number: number;
  page_count: number;
  file_size_bytes: number;
  source: "original" | "manual" | "auto" | "restore";
  description: string | null;
  parent_version: number | null;
  /** Entfernte Seiten (1-basiert, bezogen auf die Elternversion) */
  removed_pages: number[] | null;
  created_at: string | null;
  is_current: boolean;
}

export interface AutoTrimResult {
  trimmed: number[];
  unchanged: number[];
  errors: Record<string, string>;
}

export interface PdfSettings {
  id: number;
  auto_trim_enabled: boolean;
  auto_trim_max_pages: number;
}

export interface AnalyzeRequest {
  document_ids: number[];
  ai_config_id?: number;
  system_prompt_id?: number;
  /** Workflow (Analyse-Ablauf). Leer = automatisch: Lieferant → Standard → klassisch */
  workflow_id?: number;
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

  /** Plausibilitätsprüfung auf den gespeicherten Daten erneut ausführen */
  revalidate: (id: number) =>
    apiClient.post<DocumentDetail>(`/api/documents/${id}/validate`).then((r) => r.data),

  /** Prüfung nach manueller Kontrolle als "geprüft" bestätigen */
  confirmValidation: (id: number) =>
    apiClient
      .post<DocumentDetail>(`/api/documents/${id}/validation/confirm`)
      .then((r) => r.data),

  /** Versionsverlauf der PDF (Original + Bearbeitungen) */
  versions: (id: number) =>
    apiClient.get<DocumentVersion[]>(`/api/documents/${id}/versions`).then((r) => r.data),

  /** URL zur PDF einer bestimmten Version */
  versionPreviewUrl: (id: number, version: number) =>
    `${BASE}/api/documents/${id}/versions/${version}/preview`,

  /** URL zum Vorschaubild einer Seite (1-basiert) einer Version */
  pageThumbnailUrl: (id: number, page: number, version: number, width = 240) =>
    `${BASE}/api/documents/${id}/pages/${page}/thumbnail?version=${version}&width=${width}`,

  /** Seiten entfernen ODER nur bestimmte behalten → neue Version */
  editPages: (id: number, data: { remove_pages?: number[]; keep_pages?: number[]; note?: string }) =>
    apiClient.post<DocumentVersion>(`/api/documents/${id}/pages/remove`, data).then((r) => r.data),

  /** Frühere Version als neue aktuelle Version wiederherstellen */
  restoreVersion: (id: number, version: number) =>
    apiClient
      .post<DocumentVersion>(`/api/documents/${id}/versions/${version}/restore`)
      .then((r) => r.data),

  /** Mehrere Dokumente auf die ersten N Seiten kürzen */
  autoTrim: (document_ids: number[], max_pages: number) =>
    apiClient
      .post<AutoTrimResult>("/api/documents/auto-trim", { document_ids, max_pages })
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
  is_document_type_prompt: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemPromptCreate {
  name: string;
  content: string;
  is_default?: boolean;
  is_document_type_prompt?: boolean;
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

// ─── Typen: Dokumententypen ───────────────────────────────────────────────────

export interface DocumentType {
  id: number;
  name: string;
}

export const documentTypesApi = {
  list: () =>
    apiClient.get<DocumentType[]>("/api/document-types").then((r) => r.data),
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

export const pdfSettingsApi = {
  get: () => apiClient.get<PdfSettings>("/api/settings/pdf").then((r) => r.data),
  update: (data: { auto_trim_enabled: boolean; auto_trim_max_pages: number }) =>
    apiClient.put<PdfSettings>("/api/settings/pdf", data).then((r) => r.data),
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

export interface KiStats {
  total_extractions: number;
  ki_requests: number;
  sum_input_tokens: number | null;
  sum_output_tokens: number | null;
  sum_reasoning_tokens: number | null;
  avg_tokens_per_second: number | null;
  avg_time_to_first_token: number | null;
  avg_input_tokens: number | null;
  avg_output_tokens: number | null;
}

export const logsApi = {
  /** Log-Einträge laden (neueste zuerst) */
  list: (params?: { category?: string; level?: string; limit?: number }) =>
    apiClient.get<SystemLog[]>("/api/logs", { params }).then((r) => r.data),

  /** Aggregierte KI-Statistiken */
  kiStats: () =>
    apiClient.get<KiStats>("/api/logs/ki-stats").then((r) => r.data),

  /** Alle oder kategoriegefilterte Logs löschen */
  clear: (category?: string) =>
    apiClient
      .delete<{ deleted: number }>("/api/logs", { params: category ? { category } : undefined })
      .then((r) => r.data),
};

// ─── Typen: Lieferanten ───────────────────────────────────────────────────────

export interface Supplier {
  id: number;
  /** Eigener Analyse-Workflow dieses Lieferanten (null = Standard) */
  workflow_id?: number | null;
  name: string;
  street: string | null;
  zip_code: string | null;
  city: string | null;
  address: string | null;
  hrb_number: string | null;
  tax_number: string | null;
  vat_id: string | null;
  bank_name: string | null;
  iban: string | null;
  bic: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierUpdate {
  name: string;
  street?: string | null;
  zip_code?: string | null;
  city?: string | null;
  address?: string | null;
  hrb_number?: string | null;
  tax_number?: string | null;
  vat_id?: string | null;
  bank_name?: string | null;
  iban?: string | null;
  bic?: string | null;
}

export type DuplicateReason = "iban" | "vat_id" | "tax_number" | "name" | "name_similar";

export interface DuplicateGroup {
  suppliers: Supplier[];
  reasons: DuplicateReason[];
  reason_labels: string[];
  confidence: "high" | "medium" | "low";
}

export interface SupplierMergeRequest {
  target_id: number;
  source_ids: number[];
  /** Ausdrücklich gewählte Endwerte einzelner Felder */
  fields?: Record<string, string | null>;
  update_document_names?: boolean;
}

export interface SupplierMergeResult {
  supplier: Supplier;
  merged_ids: number[];
  moved_documents: number;
  renamed_documents: number;
}

export const suppliersApi = {
  list: () => apiClient.get<Supplier[]>("/api/suppliers/").then((r) => r.data),
  get: (id: number) => apiClient.get<Supplier>(`/api/suppliers/${id}`).then((r) => r.data),
  update: (id: number, data: SupplierUpdate) =>
    apiClient.put<Supplier>(`/api/suppliers/${id}`, data).then((r) => r.data),
  delete: (id: number) => apiClient.delete(`/api/suppliers/${id}`),
  duplicates: () =>
    apiClient.get<Supplier[][]>("/api/suppliers/duplicates/").then((r) => r.data),
  /** Dublettensuche: gleiche IBAN / USt-IdNr. / Steuernummer, gleicher oder ähnlicher Name */
  duplicateGroups: () =>
    apiClient.get<DuplicateGroup[]>("/api/suppliers/duplicate-groups").then((r) => r.data),
  /** Lieferanten zusammenführen (Belege der Quellen → Ziel, Quellen werden gelöscht) */
  merge: (data: SupplierMergeRequest) =>
    apiClient.post<SupplierMergeResult>("/api/suppliers/merge", data).then((r) => r.data),
  /** Analyse-Workflow des Lieferanten festlegen (null = Standard-Workflow) */
  setWorkflow: (id: number, workflow_id: number | null) =>
    apiClient.put<Supplier>(`/api/suppliers/${id}/workflow`, { workflow_id }).then((r) => r.data),
};

// ─── Typen: Workflows ─────────────────────────────────────────────────────────

export type WorkflowNodeType =
  | "start" | "trim_pages" | "detect_type" | "branch" | "extract" | "validate" | "end";

export interface WorkflowNodeConfig {
  // trim_pages
  max_pages?: number;
  // detect_type / extract
  system_prompt_id?: number | null;
  ai_config_id?: number | null;
  // validate
  auto_correct?: boolean;
  ai_recheck?: boolean;
  // branch
  field?: "document_type" | "supplier_name" | "page_count" | "validation_status";
  op?: "equals" | "not_equals" | "contains" | "gt" | "lt" | "in";
  value?: string;
}

export interface WorkflowGraphNode {
  id: string;
  type: WorkflowNodeType;
  position: { x: number; y: number };
  data: { label: string; config: WorkflowNodeConfig };
}

export interface WorkflowGraphEdge {
  id: string;
  source: string;
  target: string;
  /** "true" | "false" bei Verzweigungen, sonst null */
  sourceHandle?: string | null;
}

export interface WorkflowGraph {
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
}

export interface WorkflowListItem {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
  node_count: number;
  supplier_count: number;
  created_at: string;
  updated_at: string;
}

export interface Workflow {
  id: number;
  name: string;
  description: string | null;
  graph: WorkflowGraph;
  is_default: boolean;
  supplier_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowTemplate {
  key: string;
  name: string;
  description: string;
  graph: WorkflowGraph;
}

export interface WorkflowValidation {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

/** Ein Eintrag im Ablaufprotokoll einer Analyse */
export interface WorkflowTraceEntry {
  node_id: string;
  type: WorkflowNodeType;
  label: string;
  status: "ok" | "error";
  duration_s: number;
  detail: string | null;
  branch: "true" | "false" | null;
}

export const workflowsApi = {
  list: () => apiClient.get<WorkflowListItem[]>("/api/workflows/").then((r) => r.data),
  templates: () => apiClient.get<WorkflowTemplate[]>("/api/workflows/templates").then((r) => r.data),
  get: (id: number) => apiClient.get<Workflow>(`/api/workflows/${id}`).then((r) => r.data),
  create: (data: { name: string; description?: string | null; template?: string; graph?: WorkflowGraph }) =>
    apiClient.post<Workflow>("/api/workflows/", data).then((r) => r.data),
  update: (id: number, data: { name: string; description?: string | null; graph: WorkflowGraph }) =>
    apiClient.put<Workflow>(`/api/workflows/${id}`, data).then((r) => r.data),
  delete: (id: number) => apiClient.delete(`/api/workflows/${id}`),
  validate: (graph: WorkflowGraph) =>
    apiClient.post<WorkflowValidation>("/api/workflows/validate", { graph }).then((r) => r.data),
  setDefault: (id: number) =>
    apiClient.post<Workflow>(`/api/workflows/${id}/set-default`).then((r) => r.data),
  clearDefault: (id: number) =>
    apiClient.post<Workflow>(`/api/workflows/${id}/clear-default`).then((r) => r.data),
  duplicate: (id: number) =>
    apiClient.post<Workflow>(`/api/workflows/${id}/duplicate`).then((r) => r.data),
};

// ─── Backup / Restore ─────────────────────────────────────────────────────────

export const backupApi = {
  download: () =>
    apiClient.get("/api/settings/backup/", { responseType: "blob" }).then((r) => r.data),
  restore: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient
      .post<{ restored: Record<string, number>; message: string }>(
        "/api/settings/restore/",
        form,
        { headers: { "Content-Type": "multipart/form-data" } }
      )
      .then((r) => r.data);
  },
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
