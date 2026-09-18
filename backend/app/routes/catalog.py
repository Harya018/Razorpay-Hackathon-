from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.audit import write_audit_log
from app.auth import AuthUser, require_merchant_admin
from app.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter()


# Public storefront listing: active products only. Merchants pass
# include_inactive=1 (gated) to see soft-deleted rows in Inventory.
@router.get("/catalog", response_model=list[ProductResponse])
def list_catalog(db: Session = Depends(get_db), include_inactive: bool = Query(default=False)):
    q = db.query(Product)
    if not include_inactive:
        q = q.filter(Product.is_active.is_(True))
    return q.order_by(Product.id).all()


# Serves inactive products too — orders, invoices, audit traces and
# policy-gate's price re-check on a still-open negotiation all need the
# row to keep resolving; the response's is_active flag tells the reader.
@router.get("/product/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/product", response_model=ProductResponse, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), _admin=Depends(require_merchant_admin)):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/product/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), admin: AuthUser = Depends(require_merchant_admin)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    before = {k: getattr(product, k) for k in changes}
    for k, v in changes.items():
        setattr(product, k, v)
    db.commit()
    db.refresh(product)
    # Inventory/price edits are money-adjacent merchant actions — they go
    # into the same hash-chained audit log as everything else, attributed.
    write_audit_log(
        db,
        order_id=None,
        event_type="product_updated",
        payload={"product_id": product.id, "changes": {k: {"from": before[k], "to": v} for k, v in changes.items()}, "actor": admin.email or admin.sub},
    )
    return product


@router.delete("/product/{product_id}", response_model=ProductResponse)
def delete_product(product_id: int, db: Session = Depends(get_db), admin: AuthUser = Depends(require_merchant_admin)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if not product.is_active:
        raise HTTPException(status_code=409, detail="Product is already deleted")
    product.is_active = False
    db.commit()
    db.refresh(product)
    write_audit_log(db, order_id=None, event_type="product_deleted", payload={"product_id": product.id, "name": product.name, "actor": admin.email or admin.sub})
    return product
