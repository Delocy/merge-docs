from typing import List, Optional

from pydantic import BaseModel


class Base(BaseModel):
    id: int


class Item(BaseModel):
    sku: str
    quantity: int = 1


class OrderCreate(BaseModel):
    customer_id: int
    items: List[Item]
    note: Optional[str] = None


class Order(Base):
    customer_id: int
    items: list[Item]
    status: str


class OrderList(BaseModel):
    orders: list[Order]
    total: int
