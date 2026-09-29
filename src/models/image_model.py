from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel

class Image(SQLModel, table=True):
    __tablename__ = "app_inv_images"

    id: int | None = Field(primary_key=True, default=None)
    s3_key: str = Field(max_length=255, unique=True)
    bucket: str = Field(max_length=63)
    original_filename: str = Field(max_length=255)
    content_type: str = Field(max_length=50)
    size_bytes: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
