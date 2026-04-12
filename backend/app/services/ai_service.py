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
  "lieferant": {
    "name": "Vollständige Bezeichnung des Lieferanten",
    "anschrift": {
      "strasse": "Straße und Hausnummer",
      "plz": "PLZ",
      "ort": "Ort",
      "land": "Land (falls angegeben)"
    },
    "hrb_nummer": "HRB-Nummer des Handelsregisters",
    "steuernummer": "Steuernummer des Lieferanten",
    "ust_id_nr": "USt-IdNr. des Lieferanten",
    "bankverbindung": {
      "bank_name": "Name der Bank",
      "iban": "IBAN-Nummer",
      "bic": "BIC-Nummer"
    }
  },
  "rechnungsdaten": {
    "rechnungsnummer": "Rechnungsnummer",
    "rechnungsdatum": "YYYY-MM-DD",
    "faelligkeit": "YYYY-MM-DD",
    "kundennummer": "Kundennummer des Rechnungsempfängers"
  },
  "positionen": [
    {
      "position_nr": 1,
      "artikelbezeichnung": "Vollständige Produkt-/Artikelbezeichnung",
      "artikelnummer_lieferant": "Artikelnummer des Lieferanten",
      "menge": 0,
      "mengeneinheit": "Stück/kg/Liter/Palette/etc.",
      "einzelpreis": 0.00,
      "gesamtpreis": 0.00,
      "waehrung": "EUR",
      "steuersatz": 19.0,
      "preisnachlass": {
        "betrag": 0.00,
        "prozent": null,
        "bezeichnung": "Art des Nachlasses, z.B. Rabatt, Mengenrabatt"
      }
    }
  ],
  "zahlungsinformationen": {
    "gesamtbetrag_netto": 0.00,
    "umsatzsteuer_zusammenfassung": [
      {
        "steuersatz": 19.0,
        "nettobetrag": 0.00,
        "steuerbetrag": 0.00
      }
    ],
    "gesamtbetrag_brutto": 0.00,
    "waehrung": "EUR",
    "skonto": {
      "prozent": null,
      "betrag": null,
      "frist_tage": null
    },
    "zahlungsbedingungen": "Freitextfeld mit den vollständigen Zahlungsbedingungen"
  }
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
                # "detail" weglassen — LM Studio und viele lokale APIs ignorieren
                # oder lehnen diesen Parameter ab, was zu Channel-Warnungen führt.
            },
        })
        logger.debug("  Seite %d/%d in Anfrage eingebettet", idx + 1, len(images_b64))

    # ─── API-Aufruf ─────────────────────────────────────────────────────────
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    request_body: dict = {
        "model": config.model_name,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "stream": False,  # Explizit deaktivieren — LM Studio löst sonst Channel-Warnungen aus
        "messages": [
            {"role": "system", "content": active_system_prompt},
            {"role": "user", "content": content_parts},
        ],
    }

    # Reasoning-Modus immer an API weiterleiten
    reasoning = getattr(config, "reasoning", "off") or "off"
    # "on" wird als "high" übermittelt (OpenAI-kompatibel: off/low/medium/high)
    request_body["reasoning"] = "high" if reasoning == "on" else reasoning

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

    # Währungswerte normalisieren: Dezimalkomma → Dezimalpunkt (79,99 → 79.99)
    parsed = _normalize_decimal_commas(parsed)
    raw_text = json.dumps(parsed, ensure_ascii=False, indent=2)

    # Neues verschachteltes Format vs. altes flaches Format erkennen
    try:
        if "lieferant" in parsed or "rechnungsdaten" in parsed or "zahlungsinformationen" in parsed:
            extracted_fields, order_positions = _map_new_format(parsed)
        else:
            # Altes flaches Format (Rückwärtskompatibilität)
            order_positions: list[dict] = parsed.pop("order_positions", []) or []
            extracted_fields = _clean_flat_fields(parsed)
    except Exception as exc:
        logger.error("Fehler beim Verarbeiten der Felder: %s", exc)
        extracted_fields, order_positions = {}, []

    logger.info(
        "Extraktion erfolgreich: %d Felder, %d Positionen",
        len([v for v in extracted_fields.values() if v is not None]),
        len(order_positions),
    )

    return extracted_fields, order_positions, raw_text


def _normalize_decimal_commas(obj):
    """
    Normalisiert Dezimalkommas in Zahlenwerten rekursiv im gesamten geparsten JSON.

    Wandelt Strings wie "79,99" → 79.99, "1.234,56" → 1234.56,
    und auch "719,99 €" / "€ 719,99" → 719.99 um (Währungssymbol wird ignoriert).
    Freitexte wie "Musterstraße 1, Ort" bleiben unberührt.
    """
    if isinstance(obj, dict):
        return {k: _normalize_decimal_commas(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_decimal_commas(item) for item in obj]
    if isinstance(obj, str):
        s = obj.strip()
        # Währungssymbole und Leerzeichen entfernen (€, $, £, ¥)
        cleaned = re.sub(r'[€$£¥\s]', '', s)
        # Muster: optional Tausender-Trennpunkte, dann Komma + 1–2 Dezimalstellen
        # Beispiele: "79,99" | "1.234,56" | "719,99 €" (nach Bereinigung)
        # Kein Match: "Muster,Text" | "Straße 1, Ort"
        if _DECIMAL_COMMA_RE.match(cleaned):
            try:
                return float(cleaned.replace(".", "").replace(",", "."))
            except ValueError:
                pass
    return obj


_DECIMAL_COMMA_RE = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{1,2}$')


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


def _str(val) -> str | None:
    """Gibt None zurück bei leeren Strings, sonst den getrimmten Wert."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _date(val) -> str | None:
    """
    Normalisiert ein Datum auf ISO-Format (YYYY-MM-DD) oder gibt None zurück.
    Akzeptiert: "2024-01-15", "15.01.2024", "01/15/2024".
    Unbekannte Formate → None (verhindert DB-Fehler durch ungültige Strings).
    """
    s = _str(val)
    if s is None:
        return None
    # Bereits ISO
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    # Deutsches Format DD.MM.YYYY
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # US-Format MM/DD/YYYY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', s)
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    logger.warning("Unbekanntes Datumsformat ignoriert: '%s'", s)
    return None


def _num(val) -> float | None:
    """Konvertiert einen Wert in float, normalisiert europäische Formate."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(" ", "")
    # Europäisches Format: "1.234,56" → "1234.56"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _map_new_format(data: dict) -> tuple[dict, list[dict]]:
    """
    Mappt das neue verschachtelte KI-JSON-Format auf die flachen DB-Felder.
    Gibt (extracted_fields, order_positions) zurück.
    """
    lieferant = data.get("lieferant") or {}
    anschrift = lieferant.get("anschrift") or {}
    bank = lieferant.get("bankverbindung") or {}
    rechnung = data.get("rechnungsdaten") or {}
    zahlung = data.get("zahlungsinformationen") or {}
    skonto = zahlung.get("skonto") or {}

    # Anschrift zusammensetzen
    adress_parts = [
        _str(anschrift.get("strasse")),
        " ".join(filter(None, [_str(anschrift.get("plz")), _str(anschrift.get("ort"))])) or None,
        _str(anschrift.get("land")),
    ]
    supplier_address = "\n".join(p for p in adress_parts if p) or None

    extracted_fields = {
        "supplier_name":      _str(lieferant.get("name")),
        "supplier_address":   supplier_address,
        "hrb_number":         _str(lieferant.get("hrb_nummer")),
        "tax_number":         _str(lieferant.get("steuernummer")),
        "vat_id":             _str(lieferant.get("ust_id_nr")),
        "bank_name":          _str(bank.get("bank_name")),
        "iban":               _str(bank.get("iban")),
        "bic":                _str(bank.get("bic")),
        "customer_number":    _str(rechnung.get("kundennummer")),
        "invoice_number":     _str(rechnung.get("rechnungsnummer")),
        "invoice_date":       _date(rechnung.get("rechnungsdatum")),
        "due_date":           _date(rechnung.get("faelligkeit")),
        "total_amount":       _num(zahlung.get("gesamtbetrag_brutto")),
        "discount_amount":    None,  # nicht im neuen Format vorhanden
        "cash_discount_amount": _num(skonto.get("betrag")),
        "payment_terms":      _str(zahlung.get("zahlungsbedingungen")),
    }

    # Positionen mappen
    order_positions = []
    for pos in (data.get("positionen") or []):
        nachlass = pos.get("preisnachlass") or {}
        # Preisnachlass als lesbaren String zusammenfassen
        discount_parts = []
        if nachlass.get("betrag") is not None:
            discount_parts.append(f"{nachlass['betrag']} {pos.get('waehrung', 'EUR')}")
        if nachlass.get("prozent") is not None:
            discount_parts.append(f"{nachlass['prozent']}%")
        if nachlass.get("bezeichnung"):
            discount_parts.append(str(nachlass["bezeichnung"]))
        discount_str = " / ".join(discount_parts) if discount_parts else None

        order_positions.append({
            "product_description": _str(pos.get("artikelbezeichnung")),
            "article_number":      _str(pos.get("artikelnummer_lieferant")),
            "quantity":            _num(pos.get("menge")),
            "unit":                _str(pos.get("mengeneinheit")),
            "unit_price":          _num(pos.get("einzelpreis")),
            "total_price":         _num(pos.get("gesamtpreis")),
            "discount":            discount_str,
        })

    return extracted_fields, order_positions


def _clean_flat_fields(data: dict) -> dict:
    """
    Bereinigt das alte flache KI-Format (Rückwärtskompatibilität).
    - Leere Strings → None
    - Zahlenfelder: Kommas durch Punkte ersetzen
    - Datumsfelder: auf ISO-Format normalisieren
    - Nur bekannte Felder durchlassen
    """
    allowed_fields = {
        "supplier_name", "supplier_address", "hrb_number", "tax_number",
        "vat_id", "bank_name", "iban", "bic", "customer_number",
        "invoice_number", "invoice_date", "due_date", "total_amount",
        "discount_amount", "cash_discount_amount", "payment_terms",
    }
    date_fields = {"invoice_date", "due_date"}
    cleaned = {}
    for key in allowed_fields:
        value = data.get(key)
        if isinstance(value, str) and not value.strip():
            value = None
        elif key in date_fields:
            value = _date(value)
        elif isinstance(value, str) and key.endswith(("_amount",)):
            value = _num(value)
        cleaned[key] = value
    return cleaned
