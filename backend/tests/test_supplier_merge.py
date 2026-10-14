"""Lieferanten zusammenführen + Dublettensuche (API, SQLite)."""

import json

import pytest
from fastapi.testclient import TestClient

from app import crud
from app.database import get_db
from app.main import app
from app.models.import_batch import ImportBatch
from app.models.invoice_extraction import InvoiceExtraction
from app.models.supplier import Supplier
from app.models.workflow import Workflow


@pytest.fixture()
def client(sqlite_session_factory):
    def _get_db():
        s = sqlite_session_factory()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def world(db):
    """Drei Lieferanten (zwei Dubletten + ein fremder) mit Belegen."""
    batch = ImportBatch(company_name="T", year=2026, folder_path="/x")
    db.add(batch)
    db.commit()
    a = Supplier(name="ACME GmbH", city="Berlin", iban="DE02120300000000202051")
    b = Supplier(name="Acme GmbH & Co. KG", street="Weg 1", zip_code="10115", iban="DE02 1203 0000 0000 2020 51",
                 vat_id="DE123456789", bank_name="Testbank")
    c = Supplier(name="Fremd AG")
    db.add_all([a, b, c])
    db.commit()

    def doc(supplier, name):
        d = crud.document.create(db, batch.id, f"{name}.pdf", 1, "T", 2026)
        crud.document.save_extraction(db, d.id, {"supplier_name": name}, [], "{}", supplier_id=supplier.id)
        return d
    docs = {"a1": doc(a, "ACME GmbH"), "a2": doc(a, "ACME GmbH"), "b1": doc(b, "Acme GmbH & Co. KG"), "c1": doc(c, "Fremd AG")}

    class W:
        pass
    w = W()
    w.db, w.a, w.b, w.c, w.docs = db, a, b, c, docs
    return w


def _supplier_ids(db):
    db.expire_all()
    return sorted(s.id for s in db.query(Supplier).all())


def test_duplicate_groups_endpoint(client, world):
    groups = client.get("/api/suppliers/duplicate-groups").json()
    assert len(groups) == 1
    g = groups[0]
    assert [s["id"] for s in g["suppliers"]] == [world.a.id, world.b.id]
    assert g["confidence"] == "high" and g["reasons"][0] == "iban"
    assert "gleiche IBAN" in g["reason_labels"] and g["suppliers"][0]["document_count"] == 2
    assert client.get("/api/suppliers/duplicates").status_code == 200       # alter Endpunkt bleibt


def test_merge_moves_documents_fills_gaps_and_deletes_sources(client, world):
    r = client.post("/api/suppliers/merge", json={"target_id": world.a.id, "source_ids": [world.b.id]})
    assert r.status_code == 200, r.text
    body = r.json()
    s = body["supplier"]
    assert body["merged_ids"] == [world.b.id] and body["moved_documents"] == 1 and body["renamed_documents"] == 0
    assert s["id"] == world.a.id and s["document_count"] == 3
    # Ziel behält seine Werte, Leeres wird aus der Quelle gefüllt
    assert s["name"] == "ACME GmbH" and s["city"] == "Berlin"
    assert s["street"] == "Weg 1" and s["vat_id"] == "DE123456789" and s["bank_name"] == "Testbank"
    assert _supplier_ids(world.db) == sorted([world.a.id, world.c.id])
    world.db.expire_all()
    assert world.db.get(InvoiceExtraction, world.docs["b1"].extraction.id).supplier_id == world.a.id
    assert client.get("/api/suppliers/duplicate-groups").json() == []


def test_merge_explicit_fields_win_and_name_update_is_optional(client, world):
    r = client.post("/api/suppliers/merge", json={
        "target_id": world.a.id, "source_ids": [world.b.id],
        "fields": {"name": "  Acme GmbH & Co. KG ", "city": "Hamburg", "bic": ""},
        "update_document_names": True,
    }).json()
    assert r["supplier"]["name"] == "Acme GmbH & Co. KG" and r["supplier"]["city"] == "Hamburg"
    assert r["renamed_documents"] == 2                       # die beiden ACME-Belege; b1 hatte den Namen schon
    world.db.expire_all()
    names = {d.extraction.supplier_name for d in world.docs.values() if d.extraction.supplier_id == world.a.id}
    assert names == {"Acme GmbH & Co. KG"}
    assert world.docs["c1"].extraction.supplier_name == "Fremd AG"        # fremde Belege unberührt


def test_names_untouched_without_flag(client, world):
    client.post("/api/suppliers/merge", json={"target_id": world.a.id, "source_ids": [world.b.id]})
    world.db.expire_all()
    assert world.docs["b1"].extraction.supplier_name == "Acme GmbH & Co. KG"


def test_merge_multiple_sources_and_workflow_carry_over(client, world):
    wf = Workflow(name="WF", graph=json.dumps({"nodes": [], "edges": []}))
    world.db.add(wf)
    world.db.commit()
    world.b.workflow_id = wf.id
    world.db.commit()
    r = client.post("/api/suppliers/merge", json={"target_id": world.a.id, "source_ids": [world.c.id, world.b.id, world.b.id]})
    assert r.status_code == 200
    assert r.json()["merged_ids"] == [world.c.id, world.b.id]            # Duplikate in der Liste ignoriert
    assert r.json()["supplier"]["workflow_id"] == wf.id and r.json()["moved_documents"] == 2
    assert _supplier_ids(world.db) == [world.a.id]


def test_merge_keeps_target_workflow(client, world):
    w1, w2 = (Workflow(name=n, graph=json.dumps({"nodes": [], "edges": []})) for n in ("W1", "W2"))
    world.db.add_all([w1, w2])
    world.db.commit()
    world.a.workflow_id, world.b.workflow_id = w1.id, w2.id
    world.db.commit()
    r = client.post("/api/suppliers/merge", json={"target_id": world.a.id, "source_ids": [world.b.id]}).json()
    assert r["supplier"]["workflow_id"] == w1.id


@pytest.mark.parametrize("payload, status, text", [
    ({"target_id": 1, "source_ids": []}, 422, None),
    ({"target_id": 1, "source_ids": [1]}, 400, "nicht gleichzeitig"),
    ({"target_id": 9999, "source_ids": [1]}, 404, "Ziel-Lieferant #9999"),
    ({"target_id": 1, "source_ids": [8888]}, 404, "#8888"),
    ({"target_id": 1, "source_ids": [2], "fields": {"unbekannt": "x"}}, 400, "Unbekannte Felder"),
    ({"target_id": 1, "source_ids": [2], "fields": {"name": " "}}, 400, "Name darf nicht leer"),
])
def test_merge_validation_errors_change_nothing(client, world, payload, status, text):
    before = _supplier_ids(world.db)
    r = client.post("/api/suppliers/merge", json=payload)
    assert r.status_code == status
    if text:
        assert text in r.json()["detail"]
    assert _supplier_ids(world.db) == before


def test_merge_is_atomic_on_failure(world, monkeypatch):
    real_delete = world.db.delete

    def boom(obj):
        raise RuntimeError("db down")
    monkeypatch.setattr(world.db, "delete", boom)
    with pytest.raises(RuntimeError):
        crud.supplier.merge(world.db, world.a.id, [world.b.id], update_document_names=True)
    monkeypatch.setattr(world.db, "delete", real_delete)
    world.db.expire_all()
    assert _supplier_ids(world.db) == sorted([world.a.id, world.b.id, world.c.id])
    assert world.docs["b1"].extraction.supplier_id == world.b.id           # nichts umgehängt
    assert world.docs["b1"].extraction.supplier_name == "Acme GmbH & Co. KG"
    assert world.db.get(Supplier, world.a.id).vat_id is None               # nichts aufgefüllt


def test_merge_writes_system_log(client, world):
    client.post("/api/suppliers/merge", json={"target_id": world.a.id, "source_ids": [world.b.id]})
    logs = client.get("/api/logs").json()
    assert any("Lieferanten zusammengeführt" in l["message"] and f"#{world.a.id}" in l["message"] for l in logs)
