import io
import uuid
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from src.models.image_model import Image
from src.models.product_model import Product
from src.shared.database.session_db import SessionDep
from src.shared.storage.s3 import StorageError, upload_file

app = FastAPI()

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
# content-type permitido -> (extensiones aceptadas, extensión usada en S3)
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ({".jpg", ".jpeg"}, "jpg"),
    "image/png": ({".png"}, "png"),
    "image/webp": ({".webp"}, "webp"),
}

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


class ImageUploadResponse(BaseModel):
    id: int
    bucket: str
    s3_key: str


# Endpoint síncrono (def): FastAPI lo ejecuta en un threadpool,
# así la subida bloqueante de boto3 no congela el event loop.
@app.post("/images", status_code=status.HTTP_201_CREATED, response_model=ImageUploadResponse)
def upload_image(file: UploadFile, session: SessionDep):
    allowed = ALLOWED_IMAGE_TYPES.get(file.content_type)
    extension = Path(file.filename or "").suffix.lower()
    if allowed is None or extension not in allowed[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de archivo no permitido. Solo se aceptan imágenes JPEG, PNG o WEBP",
        )

    # Leer como máximo 5 MB + 1 byte: si sobra, el archivo es demasiado grande
    data = file.file.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La imagen supera el tamaño máximo de 5 MB",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío")

    s3_key = f"images/{uuid.uuid4()}.{allowed[1]}"
    try:
        bucket = upload_file(io.BytesIO(data), s3_key, file.content_type)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    image = Image(
        s3_key=s3_key,
        bucket=bucket,
        original_filename=file.filename,
        content_type=file.content_type,
        size_bytes=len(data),
    )
    session.add(image)
    session.commit()
    session.refresh(image)

    return image
