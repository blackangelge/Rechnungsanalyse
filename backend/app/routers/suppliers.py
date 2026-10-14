"""
Router für Lieferanten-Stammdaten.

Endpunkte:
  GET    /api/suppliers              — alle Lieferanten (mit Dokumentanzahl)
  GET    /api/suppliers/duplicates   — potenzielle Duplikate (nur gleicher Name, veraltet)
  GET    /api/suppliers/duplicate-groups — Dublettensuche (IBAN, USt-IdNr., Steuernr., Name)
  POST   /api/suppliers/merge        — Lieferanten zusammenführen
  GET    /api/suppliers/{id}         — einzelner Lieferant
  PUT    /api/suppliers/{id}         — Lieferant aktualisieren
  PUT    /api/suppliers/{id}/workflow — Analyse-Workflow des Lieferanten festlegen
  DELETE /api/suppliers/{id}         — Lieferant löschen
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.supplier import (
    DuplicateGroupRead, SupplierMergeRequest, SupplierMergeResult, SupplierRead, SupplierUpdate,
)
from app.schemas.workflow import SupplierWorkflowUpdate
from app.services import supplier_dedup

router = APIRouter(prefix="/api/suppliers", tags=["Lieferanten"])


def _with_count(db: Session, supplier) -> dict:
    """Ergänzt einen Lieferanten um die Dokumentanzahl."""
    data = {c.name: getattr(supplier, c.name) for c in supplier.__table__.columns}
    data["document_count"] = crud.supplier.get_document_count(db, supplier.id)
    return data


@router.get("", response_model=list[SupplierRead])
def list_suppliers(db: Session = Depends(get_db)):
    """Gibt alle Lieferanten mit Dokumentanzahl zurück."""
    suppliers = crud.supplier.get_all(db)
    return [_with_count(db, s) for s in suppliers]


@router.get("/duplicates", response_model=list[list[SupplierRead]])
def get_duplicates(db: Session = Depends(get_db)):
    """Findet potenzielle Duplikate (gleicher Name)."""
    groups = crud.supplier.find_duplicates(db)
    return [
        [_with_count(db, s) for s in group]
        for group in groups
    ]


@router.get("/duplicate-groups", response_model=list[DuplicateGroupRead])
def get_duplicate_groups(db: Session = Depends(get_db)):
    """
    Dublettensuche: gleiche IBAN / USt-IdNr. / Steuernummer (hohe Konfidenz), gleicher Name ohne
    Rechtsform (mittel), sehr ähnlicher Name (niedrig). Es wird nichts verändert.
    """
    by_id = {s.id: s for s in crud.supplier.get_all(db)}
    groups = supplier_dedup.find_duplicate_groups(by_id.values())
    return [
        DuplicateGroupRead(
            suppliers=[_with_count(db, by_id[i]) for i in g.supplier_ids],
            reasons=g.reasons,
            reason_labels=[supplier_dedup.REASON_LABELS[r] for r in g.reasons],
            confidence=g.confidence,
        )
        for g in groups
    ]


@router.post("/merge", response_model=SupplierMergeResult)
def merge_suppliers(payload: SupplierMergeRequest, db: Session = Depends(get_db)):
    """
    Führt Lieferanten zusammen: Belege der Quellen werden dem Ziel zugeordnet, leere Stammdaten
    aufgefüllt, die Quellen gelöscht. Alles in einer Transaktion.
    """
    try:
        result = crud.supplier.merge(
            db, payload.target_id, payload.source_ids,
            fields=payload.fields, update_document_names=payload.update_document_names,
        )
    except crud.supplier.MergeError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    crud.system_log.add(
        db, category="system", level="info",
        message=(f"Lieferanten zusammengeführt: {', '.join('#' + str(i) for i in result.merged_ids)} → "
                 f"#{result.supplier.id} '{result.supplier.name}' ({result.moved_documents} Beleg(e) umgehängt"
                 + (f", {result.renamed_documents} Name(n) vereinheitlicht" if result.renamed_documents else "") + ")"),
    )
    return SupplierMergeResult(
        supplier=_with_count(db, result.supplier), merged_ids=result.merged_ids,
        moved_documents=result.moved_documents, renamed_documents=result.renamed_documents,
    )


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    """Gibt einen einzelnen Lieferanten zurück."""
    obj = crud.supplier.get_by_id(db, supplier_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Lieferant nicht gefunden")
    return _with_count(db, obj)


@router.put("/{supplier_id}", response_model=SupplierRead)
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)):
    """Aktualisiert einen Lieferanten."""
    obj = crud.supplier.update(db, supplier_id, payload.model_dump())
    if obj is None:
        raise HTTPException(status_code=404, detail="Lieferant nicht gefunden")
    return _with_count(db, obj)


@router.put("/{supplier_id}/workflow", response_model=SupplierRead)
def set_supplier_workflow(supplier_id: int, payload: SupplierWorkflowUpdate, db: Session = Depends(get_db)):
    """Legt den Analyse-Workflow für diesen Lieferanten fest (None = Standard-Workflow)."""
    if payload.workflow_id is not None and crud.workflow.get_by_id(db, payload.workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow nicht gefunden")
    obj = crud.workflow.set_supplier_workflow(db, supplier_id, payload.workflow_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Lieferant nicht gefunden")
    return _with_count(db, obj)


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    """Löscht einen Lieferanten (supplier_id in Extraktionen wird auf NULL gesetzt)."""
    if not crud.supplier.delete(db, supplier_id):
        raise HTTPException(status_code=404, detail="Lieferant nicht gefunden")
