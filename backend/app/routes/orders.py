"""Customer-facing order history. Ownership is derived ONLY from the
verified token's `sub` (Order.user_id) — the URL's order id is looked up
and then checked against that identity, and a mismatch is a 404 (never a
403, so the existence of other customers' orders isn't disclosed either).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import AuthUser, require_user
from app.database import get_db
from app.models.order import Order
from app.models.product import Product
from app.order_detail import build_order_detail, order_list_item

router = APIRouter(prefix="/orders")


def _owned_order(order_id: int, user: AuthUser, db: Session) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.user_id != user.sub:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("")
def list_my_orders(user: AuthUser = Depends(require_user), db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_id == user.sub).order_by(Order.id.desc()).all()
    products = {p.id: p for p in db.query(Product).all()}
    return [order_list_item(db, o, products) for o in orders]


@router.get("/{order_id}")
def get_my_order(order_id: int, user: AuthUser = Depends(require_user), db: Session = Depends(get_db)):
    return build_order_detail(db, _owned_order(order_id, user, db), for_customer=True)
