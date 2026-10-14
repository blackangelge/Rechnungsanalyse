"""
Plausibilitätsprüfung für extrahierte Rechnungsdaten.

Reine Rechenlogik ohne Datenbank- oder Netzwerkzugriff (gut testbar).

Geprüft wird:
  1. Position:  Menge × Einzelpreis  ≙  Positionspreis   (Rabatt und abweichende
                Preiseinheit wie "je t" bei Menge in kg werden berücksichtigt)
  2. Summe:     Σ Positionspreise  ≙  Netto- bzw. Brutto-Gesamtbetrag
  3. Beträge:   Netto + Steuer  ≙  Brutto,   Steuerbetrag  ≙  Netto × Steuersatz

Einheitenfehler (Tonne ↔ kg, Liter ↔ ml/hl, je 100 / je 1000 Stück …) werden
erkannt. Lässt sich der Fehler eindeutig einer Position zuordnen, wird der
Positionspreis automatisch korrigiert (Originalwert bleibt in `corrections`).
Alles Weitere meldet `status = "needs_review"` zur weiteren Behandlung
(zweite KI-Abfrage bzw. manuelle Prüfung).
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Any

# ─── Status-Werte (in invoice_extractions.validation_status gespeichert) ──────
STATUS_OK = "ok"
STATUS_CORRECTED = "corrected"            # automatisch (rechnerisch) korrigiert
STATUS_AI_CORRECTED = "ai_corrected"      # durch zweite KI-Abfrage korrigiert
STATUS_NEEDS_REVIEW = "needs_review"      # manuelle Prüfung nötig
STATUS_MANUAL_OK = "manual_ok"            # vom Nutzer als geprüft bestätigt
STATUS_UNCHECKED = "unchecked"            # nichts prüfbar (z.B. keine Positionen)

# ─── Einheiten ────────────────────────────────────────────────────────────────
# Schlüssel: normalisierte Schreibweise → (Dimension, Faktor zur Basiseinheit)
# Basiseinheiten: Masse = kg, Volumen = l, Länge = m, Fläche = m², Anzahl = 1
_UNITS: dict[str, tuple[str, float]] = {}


def _register(dimension: str, factor: float, *names: str) -> None:
    for n in names:
        _UNITS[n] = (dimension, factor)


_register("mass", 1000.0, "t", "to", "tonne", "tonnen", "tonn")
_register("mass", 1.0, "kg", "kilo", "kilogramm")
_register("mass", 0.001, "g", "gramm")
_register("mass", 0.000001, "mg")
_register("volume", 1.0, "l", "ltr", "liter", "litre")
_register("volume", 0.001, "ml", "milliliter")
_register("volume", 0.01, "cl")
_register("volume", 0.1, "dl")
_register("volume", 100.0, "hl", "hektoliter")
_register("volume", 1000.0, "m3", "cbm", "kubikmeter")
_register("length", 1.0, "m", "meter", "lfm", "lm")
_register("length", 0.01, "cm")
_register("length", 0.001, "mm")
_register("length", 1000.0, "km")
_register("area", 1.0, "m2", "qm", "quadratmeter")
_register("count", 1.0, "stk", "st", "stueck", "stück", "pcs", "pc", "ea", "x", "einheit", "e")
_register(
    "pack", 1.0,
    "palette", "pal", "paletten", "karton", "kartons", "ktn", "kiste", "kisten",
    "gebinde", "sack", "säcke", "saecke", "sk", "kanister", "kan", "fass", "fässer",
    "ibc", "eimer", "flasche", "flaschen", "fl", "dose", "dosen", "rolle", "rollen",
    "bund", "paket", "pakete", "pkt", "packung", "set", "container", "beutel", "box",
    "bag", "big-bag", "bigbag", "kasten", "tüte", "tube", "pack",
)

_UNIT_PREFIX_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(.*)$")


@dataclass(frozen=True)
class UnitInfo:
    """Aufgelöste Einheit: Dimension + Faktor zur Basiseinheit (inkl. Vorzahl)."""

    raw: str
    dimension: str | None   # None = unbekannt
    factor: float           # z.B. "100 kg" → 100.0, "t" → 1000.0


def parse_unit(raw: str | None) -> UnitInfo | None:
    """
    Normalisiert eine Einheit ("Tonne", "kg", "100 kg", "m³", "Stück" …).
    Gibt None zurück, wenn kein Text vorhanden ist.
    """
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip().lower()
    mult = 1.0
    m = _UNIT_PREFIX_RE.match(text)
    if m and m.group(2):
        mult = float(m.group(1).replace(",", "."))
        text = m.group(2)
    text = text.replace("³", "3").replace("²", "2").replace(".", "").strip()
    if text.startswith("je "):
        text = text[3:].strip()
    if text.startswith("/"):
        text = text[1:].strip()
    dim_factor = _UNITS.get(text)
    if dim_factor is None:
        return UnitInfo(raw=str(raw), dimension=None, factor=mult)
    return UnitInfo(raw=str(raw), dimension=dim_factor[0], factor=dim_factor[1] * mult)


def unit_factors(unit: UnitInfo | None) -> list[float]:
    """
    Plausible Umrechnungsfaktoren für Positionen mit dieser Einheit:
    Verhältnis zu allen anderen Einheiten derselben Dimension plus die
    typischen Preisbezüge "je 10 / 100 / 1000".
    """
    factors: set[float] = {10.0, 100.0, 1000.0, 0.1, 0.01, 0.001}
    if unit is not None and unit.dimension in ("mass", "volume", "length", "area"):
        for dim, f in _UNITS.values():
            if dim == unit.dimension and f > 0:
                ratio = unit.factor / f
                if abs(ratio - 1.0) > 1e-9:
                    factors.add(round(ratio, 9))
    return sorted(factors)


# ─── Datentypen ───────────────────────────────────────────────────────────────

@dataclass
class Issue:
    code: str
    severity: str          # "info" | "warning" | "error"
    message: str
    position: int | None = None   # 0-basierter Positionsindex
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code, "severity": self.severity, "message": self.message,
            "position": self.position, "details": self.details,
        }


@dataclass
class ValidationResult:
    status: str
    issues: list[Issue] = field(default_factory=list)
    corrections: list[dict] = field(default_factory=list)
    checks_run: int = 0

    @property
    def blocking_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.severity in ("warning", "error")]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "issues": [i.to_dict() for i in self.issues],
            "corrections": self.corrections,
            "checks_run": self.checks_run,
        }


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _tol(value: float) -> float:
    """Toleranz für Rundungsdifferenzen: min. 2 Cent, sonst 0,5 %."""
    return max(0.02, abs(value) * 0.005)


def _close(a: float, b: float, extra: float = 0.0) -> bool:
    return abs(a - b) <= _tol(max(abs(a), abs(b))) + extra


def _fmt(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


_PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_AMOUNT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:€|eur|euro)", re.IGNORECASE)


def _discounted_values(expected: float, discount: str | None) -> list[float]:
    """Mögliche Positionspreise nach Abzug des Positionsrabatts."""
    if not discount:
        return []
    values: list[float] = []
    for m in _PCT_RE.finditer(discount):
        values.append(expected * (1 - float(m.group(1).replace(",", ".")) / 100))
    for m in _AMOUNT_RE.finditer(discount):
        values.append(expected - float(m.group(1).replace(",", ".")))
    return values


def _raw_positions(raw: dict | None) -> list[dict]:
    pos = (raw or {}).get("positionen")
    return [p if isinstance(p, dict) else {} for p in pos] if isinstance(pos, list) else []


# ─── Hauptfunktion ────────────────────────────────────────────────────────────

def validate_invoice(
    fields: dict,
    positions: list[dict],
    raw: dict | None = None,
    auto_correct: bool = True,
) -> ValidationResult:
    """
    Prüft Rechnungsfelder + Positionen auf Plausibilität.

    Args:
        fields:    Extraktionsfelder (benötigt wird `total_amount` = Brutto).
        positions: Positionen als Dicts (quantity, unit, unit_price, total_price,
                   discount …). Bei auto_correct wird `total_price` in-place korrigiert.
        raw:       Geparstes KI-JSON im verschachtelten Format (optional). Liefert
                   Netto/Steuer sowie `preiseinheit` je Position.
        auto_correct: False = nur prüfen, nichts verändern.
    """
    result = ValidationResult(status=STATUS_UNCHECKED)
    raw_pos = _raw_positions(raw)
    zahlung = (raw or {}).get("zahlungsinformationen") or {}

    # ── 1. Positionsprüfung ──────────────────────────────────────────────────
    pos_scale_notes: dict[int, float] = {}
    for idx, pos in enumerate(positions):
        qty, price, total = _f(pos.get("quantity")), _f(pos.get("unit_price")), _f(pos.get("total_price"))
        if qty is None or price is None or total is None:
            continue
        result.checks_run += 1
        expected = qty * price
        if _close(expected, total):
            continue
        if any(_close(v, total) for v in _discounted_values(expected, pos.get("discount"))):
            continue

        unit = parse_unit(pos.get("unit"))
        price_unit = parse_unit((raw_pos[idx] if idx < len(raw_pos) else {}).get("preiseinheit"))
        scale = _find_scale(expected, total, unit, price_unit)
        if scale is not None:
            pos_scale_notes[idx] = scale
            result.issues.append(Issue(
                "price_unit_differs", "info",
                (f"Position {idx + 1}: Menge × Einzelpreis ({_fmt(expected)}) weicht um Faktor "
                 f"{_fmt_factor(scale)} vom Positionspreis ({_fmt(total)}) ab — der Einzelpreis "
                 f"bezieht sich vermutlich auf eine andere Einheit als die Menge "
                 f"({pos.get('unit') or '?'})."),
                position=idx,
                details={"expected": expected, "total": total, "factor": scale},
            ))
        else:
            result.issues.append(Issue(
                "position_mismatch", "warning",
                (f"Position {idx + 1}: Menge × Einzelpreis ({_fmt(expected)}) passt nicht zum "
                 f"Positionspreis ({_fmt(total)})."),
                position=idx,
                details={"expected": expected, "total": total},
            ))

    # ── 2. Summenprüfung ─────────────────────────────────────────────────────
    gross = _f(fields.get("total_amount"))
    net = _f(zahlung.get("gesamtbetrag_netto"))
    totals = [_f(p.get("total_price")) for p in positions]
    priced = [t for t in totals if t is not None]

    if priced and (net is not None or gross is not None):
        result.checks_run += 1
        target_values = [v for v in (net, gross) if v is not None]
        if not _sum_matches(sum(priced), target_values):
            corrected = (
                _try_auto_correct(positions, totals, target_values, raw_pos)
                if auto_correct else None
            )
            if corrected:
                for c in corrected:
                    result.corrections.append(c)
                    i = c["position"]
                    result.issues.append(Issue(
                        "auto_corrected", "info",
                        (f"Position {i + 1}: Positionspreis automatisch von {_fmt(c['from'])} "
                         f"auf {_fmt(c['to'])} korrigiert (Faktor {_fmt_factor(c['factor'])}), "
                         f"damit die Summe zum Rechnungsbetrag passt."),
                        position=i, details=c,
                    ))
            else:
                result.issues.append(Issue(
                    "sum_mismatch", "warning",
                    (f"Summe der Positionen ({_fmt(sum(priced))}) passt weder zum Netto- "
                     f"noch zum Brutto-Rechnungsbetrag "
                     f"({' / '.join(_fmt(v) for v in target_values)})."),
                    details={"positions_sum": sum(priced), "net": net, "gross": gross},
                ))

    # ── 3. Netto + Steuer = Brutto, Steuerbetrag = Netto × Satz ─────────────
    tax_rows = [r for r in (zahlung.get("umsatzsteuer_zusammenfassung") or []) if isinstance(r, dict)]
    tax_total = sum(_f(r.get("steuerbetrag")) or 0.0 for r in tax_rows) if tax_rows else None
    if net is not None and gross is not None and tax_total is not None:
        result.checks_run += 1
        if not _close(net + tax_total, gross):
            result.issues.append(Issue(
                "gross_mismatch", "warning",
                (f"Netto ({_fmt(net)}) + Steuer ({_fmt(tax_total)}) ergibt "
                 f"{_fmt(net + tax_total)}, Brutto laut Rechnung: {_fmt(gross)}."),
                details={"net": net, "tax": tax_total, "gross": gross},
            ))
    for row in tax_rows:
        rate, base, amount = _f(row.get("steuersatz")), _f(row.get("nettobetrag")), _f(row.get("steuerbetrag"))
        if rate is None or base is None or amount is None:
            continue
        result.checks_run += 1
        if not _close(base * rate / 100, amount):
            result.issues.append(Issue(
                "tax_mismatch", "warning",
                (f"Steuerbetrag {_fmt(amount)} passt nicht zu {_fmt(base)} × {rate:g} % "
                 f"({_fmt(base * rate / 100)})."),
                details={"rate": rate, "net": base, "tax": amount},
            ))

    # ── Status ableiten ──────────────────────────────────────────────────────
    if result.blocking_issues:
        result.status = STATUS_NEEDS_REVIEW
    elif result.corrections:
        result.status = STATUS_CORRECTED
    elif result.checks_run > 0:
        result.status = STATUS_OK
    return result


# ─── interne Helfer ───────────────────────────────────────────────────────────

def _fmt_factor(f: float) -> str:
    return f"{f:g}".replace(".", ",")


def _find_scale(
    expected: float, total: float, unit: UnitInfo | None, price_unit: UnitInfo | None,
) -> float | None:
    """
    Findet einen Faktor, der die Differenz Menge×Preis ↔ Positionspreis erklärt
    (total ≈ expected × Faktor). Bevorzugt den Faktor aus Mengen-/Preiseinheit.
    """
    if expected == 0 or total == 0:
        return None
    candidates: list[float] = []
    if unit and price_unit and unit.dimension and unit.dimension == price_unit.dimension:
        candidates.append(unit.factor / price_unit.factor)
    candidates.extend(1 / f for f in unit_factors(unit))
    for f in candidates:
        if _close(expected * f, total):
            return round(f, 9)
    return None


def _sum_matches(positions_sum: float, targets: list[float]) -> bool:
    # Mehrere Positionen runden einzeln → Toleranz wächst mit der Anzahl leicht mit
    return any(_close(positions_sum, t, extra=0.01) for t in targets)


def _try_auto_correct(
    positions: list[dict],
    totals: list[float | None],
    targets: list[float],
    raw_pos: list[dict],
) -> list[dict] | None:
    """
    Sucht die kleinste Menge von Positionen (1, dann 2), deren Positionspreis
    mit einem plausiblen Einheitenfaktor multipliziert die Summe passend macht.
    Wird nur angewendet, wenn die Lösung eindeutig ist.
    """
    idxs = [i for i, t in enumerate(totals) if t is not None and t != 0]
    current_sum = sum(t for t in totals if t is not None)
    options: dict[int, list[float]] = {}
    for i in idxs:
        unit = parse_unit(positions[i].get("unit"))
        options[i] = unit_factors(unit)

    max_size = 2 if len(idxs) <= 40 else 1   # Paarsuche begrenzen (Laufzeit)
    for size in range(1, max_size + 1):
        solutions: list[list[tuple[int, float]]] = []
        for combo in itertools.combinations(idxs, size):
            for factors in itertools.product(*(options[i] for i in combo)):
                new_sum = current_sum + sum(totals[i] * (f - 1) for i, f in zip(combo, factors))  # type: ignore[operator]
                if any(_close(new_sum, t, extra=0.01) for t in targets):
                    solutions.append(list(zip(combo, factors)))
        if len(solutions) == 1:
            corrections = []
            for i, f in solutions[0]:
                old = totals[i]
                new = round(old * f, 2)  # type: ignore[operator]
                positions[i]["total_price"] = new
                corrections.append({
                    "position": i, "field": "total_price",
                    "from": old, "to": new, "factor": f, "method": "unit_factor",
                })
            return corrections
        if solutions:
            return None  # mehrdeutig → nicht raten
    return None
