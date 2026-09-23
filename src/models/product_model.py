from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel

class Product(SQLModel, table=True):
    __tablename__ = "app_inv_products"
    __table_args__ = (
        UniqueConstraint("name", "category", name="uq_app_inv_products_name_category"),
        CheckConstraint("price >= 0", name="ck_app_inv_products_price_non_negative"),
        CheckConstraint("quantity >= 0", name="ck_app_inv_products_quantity_non_negative"),
    )

    id: int | None = Field(primary_key=True, default=None)
    name: str
    price: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False), ge=0)
    category: str
    quantity: int = Field(ge=0)