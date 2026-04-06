"""
KI-Extraktions-Service.

Sendet PDF-Seitenbilder an eine OpenAI-kompatible Vision-LLM-API und
parst die strukturierte JSON-Antwort in ein Python-Dict.

Unterstützte API-Formate:
- LM Studio (lokal)
- Ollama mit OpenAI-Kompatibilitätsmodus
- Jede andere API mit POST /v1/chat/completions + Vision-Unterstützung

Die KI wird angewiesen, ausschließlich ein JSON-Objekt zurückzugeben.
Bei Parse-Fehlern wird die Rohantwort trotzdem gespeichert (für Debugging).
Wirft nie eine Exception — gibt bei Fehlern leeres Dict zurück.
"""

import json
import logging
import re
from typing import Any

import httpx

from app.models.ai_config import AIConfig

logger = logging.getLogger(__name__)

# Standard-System-Prompt: weist die KI an, strukturiertes JSON zurückzugeben.
# Alle Felder sind optional — fehlende Werte sollen null sein, nicht weggelassen.
DEFAULT_SYSTEM_PROMPT = """Du bist ein präziser Dokumentenanalyst für Rechnungen.
Analysiere die bereitgestellten Rechnungsbilder und extrahiere alle Daten.

Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt — ohne Markdown, ohne Erklärungen.
Nicht gefundene Werte setzt du auf null.

JSON-Struktur:
{
  "supplier_name": "Vollständige Firma des Lieferanten",
  "supplier_address": "Vollständige Anschrift",
  "hrb_number": "HRB-Nummer",
  "tax_number": "Steuernummer",
  "vat_id": "USt-IdNr.",
  "bank_name": "Name der Bank",
  "iban": "IBAN",
  "bic": "BIC",
  "customer_number": "Kundennummer",
  "invoice_number": "Rechnungsnummer",
  "invoice_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "total_amount": 0.00,
  "discount_amount": 0.00,
  "cash_discount_amount": 0.00,
  "payment_terms": "Zahlungsbedingungen als Text",
  "order_positions": [
    {
      "product_description": "Artikelbezeichnung",
      "article_number": "Artikelnummer",
      "quantity": 1.0,
      "unit": "Stück",
      "unit_price": 0.00,
      "total_price": 0.00,
      "discount": "Preisnachlass pro Position"
    }
  ]
}"""

# Timeout für einen einzelnen KI-API-Aufruf in Sekunden.
# Lokale Modelle können bei langen PDFs länger brauchen.
REQUEST_TIMEOUT_SECONDS = 120


async def extract_invoice_data(
    images_b64: list[str],
    config: AIConfig,
    system_prompt_text: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """
    Sendet Rechnungsbilder an die Vision-LLM und gibt die extrahierten Daten zurück.

    Args:
        images_b64: Liste von Base64-kodierten PNG-Bildern (eine pro Seite).
        config: KI-Konfiguration mit API-URL, Modell-Name und Authentifizierung.
        system_prompt_text: Optionaler System-Prompt-Text. Falls None, wird
                            DEFAULT_SYSTEM_PROMPT verwendet.

    Returns:
        Tuple aus:
          - extracted_fields: Dict mit allen Rechnungsfeldern (ohne order_positions)
          - order_positions: Liste von Dicts für die Bestellpositionen
          - raw_response: Vollständige KI-Antwort als String (für Debugging)

    Raises nie eine Exception — gibt bei Fehlern leere Dicts zurück.
    """
    logger.info(
        "Starte KI-Extraktion: Modell='%s', Seiten=%d", config.model_name, len(images_b64)
    )

    # System-Prompt auswählen
    active_system_prompt = system_prompt_text if system_prompt_text else DEFAULT_SYSTEM_PROMPT

    # ─── Nachricht zusammenbauen ────────────────────────────────────────────
    # Alle Seiten werden als separate image_url-Parts in EINER Nachricht gesendet.
    content_parts: list[dict] = []

    # Einleitungstext vor den Bildern
    content_parts.append({
        "type": "text",
        "text": (
            f"Die folgende Rechnung besteht aus {len(images_b64)} Seite(n). "
            "Analysiere alle Seiten und extrahiere die Daten gemäß der Anweisung."
        ),
    })

    # Jede Seite als Bild anhängen
    for idx, data_url in enumerate(images_b64):
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": data_url,
                "detail": "high",
            },
        })
        logger.debug("  Seite %d/%d in Anfrage eingebettet", idx + 1, len(images_b64))

    # ─── API-Aufruf ─────────────────────────────────────────────────────────
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    request_body = {
        "model": config.model_name,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "messages": [
            {"role": "system", "content": active_system_prompt},
            {"role": "user", "content": content_parts},
        ],
    }

    endpoint = config.api_url.rstrip("/") + "/chat/completions"
    logger.debug("Sende Anfrage an: %s", endpoint)

    raw_text = ""

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint, json=request_body, headers=headers)

        status_code = response.status_code

        # ─── HTTP-Fehlerbehandlung ohne raise_for_status ──────────────────
        if status_code == 200:
            # Erfolg — normal verarbeiten
            pass
        elif status_code in (429, 503, 502, 504):
            raw_text = f"KI überlastet: HTTP {status_code}"
            logger.warning("KI-API überlastet (HTTP %d): %s", status_code, endpoint)
            return {}, [], raw_text
        elif status_code == 500:
            raw_text = f"KI-Fehler: HTTP 500"
            logger.error("KI-API interner Fehler (HTTP 500): %s", endpoint)
            return {}, [], raw_text
        else:
            raw_text = f"KI-Fehler: HTTP {status_code}"
            logger.error("KI-API unerwarteter Status (HTTP %d): %s", status_code, endpoint)
            return {}, [], raw_text

        # ─── Antwort auslesen ────────────────────────────────────────────
        try:
            response_data = response.json()
            raw_text = (
                response_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
        except Exception as parse_exc:
            raw_text = f"Antwort-Parse-Fehler: {parse_exc}"
            logger.error("Fehler beim Parsen der API-Antwort: %s", parse_exc)
            return {}, [], raw_text

        logger.debug("KI-Antwort (erste 300 Zeichen): %s", raw_text[:300])

    except httpx.TimeoutException as exc:
        raw_text = f"KI-Timeout nach {REQUEST_TIMEOUT_SECONDS}s: {exc}"
        logger.error("KI-API Timeout: %s", exc)
        return {}, [], raw_text
    except httpx.ConnectError as exc:
        raw_text = f"KI-Verbindungsfehler: {exc}"
        logger.error("KI-API Verbindungsfehler: %s", exc)
        return {}, [], raw_text
    except Exception as exc:
        raw_text = f"Unerwarteter KI-Fehler: {exc}"
        logger.exception("Unerwarteter Fehler bei KI-API-Aufruf: %s", exc)
        return {}, [], raw_text

    # ─── JSON aus der Antwort extrahieren ────────────────────────────────────
    try:
        parsed = _parse_json_response(raw_text)
    except Exception as exc:
        logger.error("JSON-Parse-Fehler: %s", exc)
        return {}, [], raw_text

    # Bestellpositionen aus dem Ergebnis herauslösen
    order_positions: list[dict] = parsed.pop("order_positions", []) or []

    # Felder bereinigen
    try:
        extracted_fields = _clean_fields(parsed)
    except Exception as exc:
        logger.error("Fehler beim Bereinigen der Felder: %s", exc)
        extracted_fields = {}

    logger.info(
        "Extraktion erfolgreich: %d Felder, %d Positionen",
        len([v for v in extracted_fields.values() if v is not None]),
        len(order_positions),
    )

    return extracted_fields, order_positions, raw_text


def _parse_json_response(raw_text: str) -> dict:
    """
    Extrahiert JSON aus der KI-Antwort.

    Versucht zunächst direktes Parsing. Falls die KI Markdown-Blöcke
    (```json ... ```) zurückgibt, wird der JSON-Teil herausgefiltert.

    Returns:
        Geparste Dict-Struktur oder leeres Dict bei Fehlern.
    """
    # Versuch 1: Direkt als JSON parsen
    try:
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        pass

    # Versuch 2: JSON aus Markdown-Codeblock extrahieren
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Versuch 3: Erstes { ... } in der Antwort suchen
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("KI-Antwort konnte nicht als JSON geparst werden")
    return {}


def _clean_fields(data: dict) -> dict:
    """
    Bereinigt die extrahierten Felder:
    - Leere Strings → None
    - Zahlenfelder: Kommas durch Punkte ersetzen
    - Nur bekannte Felder durchlassen (kein Datenmüll in die DB)
    """
    # Erlaubte Felder für invoice_extractions (ohne order_positions)
    allowed_fields = {
        "supplier_name", "supplier_address", "hrb_number", "tax_number",
        "vat_id", "bank_name", "iban", "bic", "customer_number",
        "invoice_number", "invoice_date", "due_date", "total_amount",
        "discount_amount", "cash_discount_amount", "payment_terms",
    }

    cleaned = {}
    for key in allowed_fields:
        value = data.get(key)

        # Leere Strings als None behandeln
        if isinstance(value, str) and not value.strip():
            value = None

        # Europäische Zahlenformate normalisieren ("1.234,56" → "1234.56")
        if isinstance(value, str) and key.endswith(("_amount",)):
            value = value.replace(".", "").replace(",", ".")
            try:
                value = float(value)
            except ValueError:
                value = None

        cleaned[key] = value

    return cleaned
