import logging
from typing import BinaryIO

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from src.shared.config import settings

logger = logging.getLogger(__name__)

# Sin access keys: boto3 usa su cadena de credenciales por defecto,
# que en la EC2 obtiene credenciales temporales del IAM Role (vía IMDS).
s3_client = boto3.client("s3", region_name=settings.aws_region)


class StorageError(Exception):
    """Error al subir un archivo a S3, con un mensaje seguro para el cliente."""


def upload_file(fileobj: BinaryIO, key: str, content_type: str) -> str:
    """Sube fileobj a S3 bajo `key` y devuelve el nombre del bucket."""
    bucket = settings.s3_bucket_name
    try:
        s3_client.upload_fileobj(
            fileobj, bucket, key, ExtraArgs={"ContentType": content_type}
        )
    except NoCredentialsError as exc:
        logger.error("S3: no se encontraron credenciales de AWS")
        raise StorageError("El servidor no tiene credenciales para acceder al almacenamiento") from exc
    except (ClientError, S3UploadFailedError) as exc:
        logger.error("S3: fallo al subir %s: %s", key, exc)
        raise StorageError("No se pudo subir la imagen al almacenamiento") from exc
    except BotoCoreError as exc:
        logger.error("S3: error de conexión al subir %s: %s", key, exc)
        raise StorageError("No se pudo conectar con el almacenamiento") from exc
    return bucket
