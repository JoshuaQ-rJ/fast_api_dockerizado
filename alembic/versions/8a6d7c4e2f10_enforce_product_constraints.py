"""enforce product constraints

Revision ID: 8a6d7c4e2f10
Revises: d34b82694cc1
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a6d7c4e2f10"
down_revision: Union[str, Sequence[str], None] = "d34b82694cc1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "app_inv_products",
        "price",
        existing_type=sa.Float(),
        type_=sa.Numeric(10, 2),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        "uq_app_inv_products_name_category",
        "app_inv_products",
        ["name", "category"],
    )
    op.create_check_constraint(
        "ck_app_inv_products_price_non_negative",
        "app_inv_products",
        "price >= 0",
    )
    op.create_check_constraint(
        "ck_app_inv_products_quantity_non_negative",
        "app_inv_products",
        "quantity >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_app_inv_products_quantity_non_negative",
        "app_inv_products",
        type_="check",
    )
    op.drop_constraint(
        "ck_app_inv_products_price_non_negative",
        "app_inv_products",
        type_="check",
    )
    op.drop_constraint(
        "uq_app_inv_products_name_category",
        "app_inv_products",
        type_="unique",
    )
    op.alter_column(
        "app_inv_products",
        "price",
        existing_type=sa.Numeric(10, 2),
        type_=sa.Float(),
        existing_nullable=False,
    )