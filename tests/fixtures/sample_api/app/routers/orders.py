from typing import Optional

from fastapi import APIRouter

from app.models.order import Order, OrderCreate, OrderList

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=Order)
def get_order(order_id: int) -> Order:
    ...


@router.post("", response_model=Order, status_code=201)
def create_order(body: OrderCreate) -> Order:
    ...


@router.get("", response_model=OrderList)
def list_orders(status: Optional[str] = None):
    ...


@router.delete("/{order_id}")
def cancel_order(order_id: int):
    return {"cancelled": True}


def _legacy_export():
    ...


router.add_api_route("/export", _legacy_export, methods=["POST"], response_model=OrderList)
