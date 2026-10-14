"""Tests für die Plausibilitätsprüfung (reine Rechenlogik, keine DB nötig)."""

from app.services.plausibility_service import (
    STATUS_CORRECTED, STATUS_NEEDS_REVIEW, STATUS_OK, STATUS_UNCHECKED,
    parse_unit, validate_invoice,
)


def _raw(net, tax_rate=19.0, positions=None):
    tax = round(net * tax_rate / 100, 2)
    return {
        "positionen": positions or [],
        "zahlungsinformationen": {
            "gesamtbetrag_netto": net,
            "umsatzsteuer_zusammenfassung": [
                {"steuersatz": tax_rate, "nettobetrag": net, "steuerbetrag": tax}
            ],
            "gesamtbetrag_brutto": round(net + tax, 2),
        },
    }


def test_parse_unit_variants():
    assert parse_unit("Tonne").factor == 1000
    assert parse_unit("kg").dimension == "mass"
    assert parse_unit("100 kg").factor == 100
    assert parse_unit("m³").dimension == "volume"
    assert parse_unit("Liter").dimension == "volume"
    assert parse_unit("Palette").dimension == "pack"
    assert parse_unit("Stück").dimension == "count"
    assert parse_unit("Foo").dimension is None
    assert parse_unit(None) is None and parse_unit("  ") is None


def test_consistent_invoice_is_ok():
    pos = [{"quantity": 2, "unit": "Stück", "unit_price": 10.0, "total_price": 20.0}]
    r = validate_invoice({"total_amount": 23.8}, pos, _raw(20.0))
    assert r.status == STATUS_OK and not r.issues


def test_nothing_to_check():
    assert validate_invoice({}, [], None).status == STATUS_UNCHECKED


def test_ton_price_with_kg_quantity_is_explained_not_flagged():
    """1 t = 50 €, 500 kg → Rechnung weist korrekt 25 € aus."""
    pos = [{"quantity": 500, "unit": "kg", "unit_price": 50.0, "total_price": 25.0}]
    raw = _raw(25.0, positions=[{"preiseinheit": "t"}])
    r = validate_invoice({"total_amount": 29.75}, pos, raw)
    assert r.status == STATUS_OK
    assert [i.code for i in r.issues] == ["price_unit_differs"]
    assert pos[0]["total_price"] == 25.0   # nichts verändert


def test_ton_price_with_kg_quantity_even_without_preiseinheit():
    pos = [{"quantity": 500, "unit": "kg", "unit_price": 50.0, "total_price": 25.0}]
    r = validate_invoice({"total_amount": 29.75}, pos, _raw(25.0))
    assert r.status == STATUS_OK


def test_wrongly_multiplied_total_is_auto_corrected():
    """KI hat 500 × 50 = 25000 gerechnet, Rechnung weist aber 25 € aus."""
    pos = [
        {"quantity": 500, "unit": "kg", "unit_price": 50.0, "total_price": 25000.0},
        {"quantity": 1, "unit": "Stück", "unit_price": 10.0, "total_price": 10.0},
    ]
    r = validate_invoice({"total_amount": 41.65}, pos, _raw(35.0))
    assert r.status == STATUS_CORRECTED
    assert pos[0]["total_price"] == 25.0
    assert r.corrections[0]["from"] == 25000.0 and r.corrections[0]["factor"] == 0.001


def test_auto_correct_disabled_only_reports():
    pos = [
        {"quantity": 500, "unit": "kg", "unit_price": 50.0, "total_price": 25000.0},
        {"quantity": 1, "unit": "Stück", "unit_price": 10.0, "total_price": 10.0},
    ]
    r = validate_invoice({"total_amount": 41.65}, pos, _raw(35.0), auto_correct=False)
    assert r.status == STATUS_NEEDS_REVIEW and pos[0]["total_price"] == 25000.0
    assert not r.corrections


def test_liter_vs_hektoliter_factor():
    pos = [
        {"quantity": 2, "unit": "hl", "unit_price": 100.0, "total_price": 200.0},
        {"quantity": 1, "unit": "Stück", "unit_price": 5.0, "total_price": 5.0},
    ]
    # Rechnung: 2 hl à 100 € je 100 l?? → tatsächlich 2.00 € + 5 € = 7 € (Faktor 0.01)
    r = validate_invoice({}, pos, _raw(7.0))
    assert r.status == STATUS_CORRECTED and pos[0]["total_price"] == 2.0


def test_ambiguous_solution_is_not_guessed():
    # Zwei gleiche Positionen → beide Korrekturen wären gleich gut → nicht raten
    pos = [
        {"quantity": 1, "unit": "kg", "unit_price": 1000.0, "total_price": 1000.0},
        {"quantity": 1, "unit": "kg", "unit_price": 1000.0, "total_price": 1000.0},
    ]
    r = validate_invoice({}, pos, _raw(1001.0))
    assert r.status == STATUS_NEEDS_REVIEW
    assert [p["total_price"] for p in pos] == [1000.0, 1000.0]


def test_unexplained_position_mismatch_needs_review():
    pos = [{"quantity": 3, "unit": "Stück", "unit_price": 7.0, "total_price": 99.0}]
    r = validate_invoice({"total_amount": 117.81}, pos, _raw(99.0))
    assert r.status == STATUS_NEEDS_REVIEW
    assert r.issues[0].code == "position_mismatch"


def test_discount_percent_explains_difference():
    pos = [{"quantity": 10, "unit": "Stück", "unit_price": 10.0, "total_price": 90.0,
            "discount": "10%"}]
    r = validate_invoice({"total_amount": 107.1}, pos, _raw(90.0))
    assert r.status == STATUS_OK


def test_gross_net_tax_mismatch():
    raw = _raw(100.0)
    raw["zahlungsinformationen"]["gesamtbetrag_brutto"] = 190.0
    r = validate_invoice({"total_amount": 190.0}, [], raw)
    assert r.status == STATUS_NEEDS_REVIEW
    assert "gross_mismatch" in [i.code for i in r.issues]


def test_sum_matches_gross_when_positions_are_gross():
    pos = [{"quantity": 1, "unit": "Stück", "unit_price": 119.0, "total_price": 119.0}]
    r = validate_invoice({"total_amount": 119.0}, pos, None)
    assert r.status == STATUS_OK
