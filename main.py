from decimal import Decimal

from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from src.models.product_model import Product
from src.shared.database.session_db import SessionDep

app = FastAPI()

class CreateProduct(BaseModel):
    name: str
    price: Decimal = Field(ge=10000)
    quantity: int = Field(ge=0)
    category: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/product", status_code=status.HTTP_201_CREATED)
def create_product(product: CreateProduct, session: SessionDep):
    name = product.name.strip().lower()
    category = product.category.strip().lower()
    existing_product = session.exec(
        select(Product).where(Product.name == name, Product.category == category)
    ).first()
    if existing_product is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product already exists")

    product_record = Product(
        name=name,
        category=category,
        price=product.price,
        quantity=product.quantity,
    )
    session.add(product_record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product already exists")
    session.refresh(product_record)

    return product_record

@app.get("/product")
def get_products(session: SessionDep):
    products = session.exec(
        select(Product)
    ).all()

    return products

@app.delete('/product/{product_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, session: SessionDep) -> Response:
    product = session.exec(
            select(Product).where(Product.id == product_id)
    ).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    session.delete(product)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)