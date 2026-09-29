# API de inventario con FastAPI en AWS

API FastAPI de productos e imágenes. Guarda los datos en PostgreSQL y las imágenes en Amazon S3, y todo corre en Docker sobre AWS (región `us-east-2`).

- **Stack:** FastAPI, SQLModel, Alembic, boto3 y uv (Python 3.12).
- **Guía paso a paso del despliegue:** [docs/DEPLOY.md](docs/DEPLOY.md).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado de la API: `{"status": "ok"}` (no depende de S3 ni de la BD) |
| POST | `/product` | Crea un producto (409 si ya existe ese nombre + categoría) |
| GET | `/product` | Lista los productos |
| DELETE | `/product/{id}` | Borra un producto (204, o 404 si no existe) |
| POST | `/images` | Sube una imagen JPEG, PNG o WEBP (máximo 5 MB) a S3 y guarda la referencia. Devuelve 201 |
| GET | `/docs` | Documentación interactiva (Swagger) |

## Arquitectura

```
                        Internet
                           │  80 / 443
                           ▼
┌──────────────────────── VPC (us-east-2) ─────────────────────────┐
│                                                                  │
│  Subred pública                                                  │
│  ┌────────────────────────────────┐                              │
│  │ EC2 #1 · Nginx Proxy Manager   │  (también bastión SSH)       │
│  │ sg-proxy                       │                              │
│  └───────────────┬────────────────┘                              │
│                  │ HTTP :8000 (IP privada)                       │
│  Subred privada  ▼                                               │
│  ┌────────────────────────────────┐      HTTPS (IAM Role)        │
│  │ EC2 #2 · API FastAPI (Docker)  │ ───────────────────────────────►  Amazon S3
│  │ sg-fastapi                     │      vía NAT Gateway         │   (bucket privado,
│  └───────────────┬────────────────┘                              │    carpeta images/)
│                  │ TCP :5432 (IP privada)                        │
│  Subred privada  ▼                                               │
│  ┌────────────────────────────────┐                              │
│  │ EC2 #3 · PostgreSQL 16 (Docker)│                              │
│  │ volumen pgdata · sg-postgres   │                              │
│  └────────────────────────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
```

## Estructura del proyecto

```
main.py                         Rutas de la API
src/shared/config.py            Lee las variables de entorno (falla si falta una obligatoria)
src/shared/database/session_db.py   Engine y sesión de SQLModel
src/shared/storage/s3.py        Cliente de S3 (boto3) y subida de archivos
src/models/                     Modelos Product e Image
alembic/                        Migraciones de la base de datos
Dockerfile, docker-compose.yml  API (EC2 #2)
deploy/postgres/                PostgreSQL (EC2 #3)
docs/DEPLOY.md                  Guía de despliegue
```

## Variables de entorno

**API (EC2 #2), archivo `.env` en la raíz** (plantilla: [.env.example](.env.example)):

| Variable | Obligatoria | Ejemplo | Descripción |
|---|---|---|---|
| `Database_url` | Sí | `postgresql://app_user:Clave123@10.0.2.15:5432/app_db` | URL de PostgreSQL. El host es la **IP privada** de la EC2 #3 y la contraseña debe tener solo letras y números |
| `AWS_REGION` | No | `us-east-2` | Región del bucket (por defecto `us-east-2`) |
| `S3_BUCKET_NAME` | Sí | `mi-bucket-imagenes` | Bucket donde se guardan las imágenes |

**PostgreSQL (EC2 #3), archivo `deploy/postgres/.env`** (plantilla: [deploy/postgres/.env.example](deploy/postgres/.env.example)): `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB`.

**No hay credenciales de AWS en el código ni en `.env`.** boto3 usa su cadena de credenciales por defecto, que en la EC2 obtiene credenciales temporales del **IAM Role** asociado a la instancia. Los archivos `.env` están en `.gitignore`.

## Cómo levantar cada servicio

**PostgreSQL (EC2 #3):**
```bash
cd deploy/postgres
cp .env.example .env && nano .env
docker compose up -d
```

**API (EC2 #2):**
```bash
cp .env.example .env && nano .env
docker compose up -d --build     # al arrancar aplica "alembic upgrade head"
docker compose logs -f api
```

**En local (desarrollo):**
```bash
uv sync
uv run alembic upgrade head
uv run fastapi dev main.py
```

## Puertos y reglas de acceso

| Servicio | Puerto | Quién puede acceder |
|---|---|---|
| Nginx Proxy Manager (EC2 #1) | 80, 443 | Cualquiera en Internet |
| Panel de NPM (EC2 #1) | 81 | Solo mi IP |
| SSH (EC2 #1) | 22 | Solo mi IP |
| API FastAPI (EC2 #2) | 8000 | Solo el SG del proxy (`sg-proxy`) |
| SSH (EC2 #2) | 22 | Solo el SG del proxy (entrando a través del bastión) |
| PostgreSQL (EC2 #3) | 5432 | Solo el SG de la API (`sg-fastapi`) |
| SSH (EC2 #3) | 22 | Solo el SG del proxy (entrando a través del bastión) |

Las reglas usan **Security Groups como origen** y no IPs. Así siguen siendo válidas aunque cambie la IP de una instancia, y solo dejan pasar tráfico de instancias con ese SG. El detalle está en [docs/DEPLOY.md](docs/DEPLOY.md#d-security-groups-mínimo-privilegio).

## Preguntas frecuentes (evaluación)

**1. ¿Por qué FastAPI está en subred privada?**
Porque no necesita recibir tráfico directo de Internet: todas las peticiones pasan por Nginx Proxy Manager. Así se reduce la superficie de ataque. La API no tiene IP pública, solo acepta el puerto 8000 desde el proxy, y sale a Internet (por ejemplo, hacia S3) a través del NAT Gateway.

**2. ¿Por qué PostgreSQL está en subred privada?**
Porque contiene los datos, que es lo más sensible, y el único que necesita hablar con ella es la API. Sin IP pública y con el puerto 5432 abierto solo para `sg-fastapi`, no se puede llegar a la base de datos desde fuera de la VPC.

**3. ¿Por qué NPM está en subred pública?**
Porque es la puerta de entrada: necesita IP pública y una ruta al Internet Gateway para recibir las peticiones HTTP/HTTPS de los usuarios. Desde ahí las reenvía a la API por la red privada. También sirve de bastión para entrar por SSH a las EC2 privadas.

**4. ¿Qué puertos están abiertos?**
- 80 y 443 (web) y 81 (panel de NPM) en la EC2 #1.
- 8000 (API) en la EC2 #2.
- 5432 (PostgreSQL) en la EC2 #3.
- 22 (SSH) en las tres.

Ver la tabla de arriba.

**5. ¿Quién puede acceder a cada puerto?**
- 80/443: cualquiera.
- 81 y el SSH de la EC2 #1: solo mi IP.
- 8000 y el SSH de las EC2 privadas: solo el SG del proxy.
- 5432: solo el SG de la API.

**6. ¿Cómo se comunica FastAPI con PostgreSQL?**
Por TCP al puerto 5432, usando la **IP privada** de la EC2 #3 dentro de la VPC. La URL de conexión llega a la API por la variable `Database_url`. SQLModel/SQLAlchemy usan el driver `psycopg2` para conectarse, y Alembic crea las tablas al arrancar el contenedor.

**7. ¿Cómo se comunica FastAPI con S3?**
Con **boto3** (`upload_fileobj`), por HTTPS hacia el endpoint de S3, saliendo por el NAT Gateway. No usa access keys: boto3 obtiene credenciales temporales del **IAM Role** de la EC2 #2 a través del servicio de metadatos (IMDSv2). Ese rol solo permite `s3:PutObject` en `images/*` del bucket.

**8. ¿Por qué no se expone PostgreSQL a Internet?**
- Una base de datos expuesta recibe constantemente escaneos automáticos e intentos de fuerza bruta contra el usuario y la contraseña.
- Si tuviera una vulnerabilidad, quedaría a la vista de todo Internet.
- Nadie aparte de la API necesita llegar a ella.

Mantenerla privada y aceptar solo el SG de la API aplica el principio de **mínimo privilegio**.
