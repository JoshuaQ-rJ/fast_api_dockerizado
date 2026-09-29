import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Falta la variable de entorno obligatoria '{name}'. "
            "Defínela en el archivo .env (ver .env.example)."
        )
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    aws_region: str
    s3_bucket_name: str


settings = Settings(
    database_url=_required("Database_url"),
    aws_region=os.getenv("AWS_REGION", "us-east-2"),
    s3_bucket_name=_required("S3_BUCKET_NAME"),
)
