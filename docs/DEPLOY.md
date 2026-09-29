# Guía de despliegue en AWS

Pasos en orden para desplegar la API en AWS (región `us-east-2`). Las tres EC2 usan **Ubuntu** y el usuario por defecto `ubuntu`.

Reemplaza estos marcadores con tus datos:

| Marcador | Qué es |
|---|---|
| `<IP_PUBLICA_EC2_1>` | IP pública de la EC2 #1 (Nginx Proxy Manager) |
| `<IP_PRIVADA_EC2_2>` | IP privada de la EC2 #2 (API FastAPI) |
| `<IP_PRIVADA_EC2_3>` | IP privada de la EC2 #3 (PostgreSQL) |
| `<NOMBRE_DEL_BUCKET>` | Nombre del bucket de S3 |
| `<MI_IP>` | Tu IP pública (la ves en https://checkip.amazonaws.com) |
| `<ID_INSTANCIA_EC2_2>` | ID de la instancia EC2 #2 (`i-0...`) |
| `mi-llave.pem` | Tu par de claves SSH |

**Orden recomendado:** primero la parte **C** (S3 e IAM) y la **D** (Security Groups). Después la **A** (base de datos), luego la **B** (API) y al final la **E** (proxy).

> **Requisito de red:** las subredes privadas necesitan salida a Internet mediante un **NAT Gateway**. Es decir, su tabla de rutas debe tener `0.0.0.0/0 → nat-xxxx`. Sin eso, `apt`, `docker pull` y `git clone` no funcionan en la EC2 #2 ni en la EC2 #3.

---

## Cómo entrar por SSH a las EC2 privadas

Las EC2 privadas no tienen IP pública, así que se entra *saltando* a través de la EC2 #1, que actúa de bastión. Desde tu PC:

```bash
# Carga la llave en el agente SSH (una sola vez por sesión)
eval "$(ssh-agent -s)"
ssh-add mi-llave.pem

# -J = "jump host": primero conecta a la EC2 #1 y desde allí a la privada
ssh -J ubuntu@<IP_PUBLICA_EC2_1> ubuntu@<IP_PRIVADA_EC2_2>
ssh -J ubuntu@<IP_PUBLICA_EC2_1> ubuntu@<IP_PRIVADA_EC2_3>
```

## Instalar Docker Engine y Docker Compose en Ubuntu

Esto es igual en la EC2 #2 y en la EC2 #3. Son los pasos de la documentación oficial ("Install Docker Engine on Ubuntu", instalación con el repositorio `apt` de Docker):

```bash
# 1. Añadir la llave GPG y el repositorio oficial de Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 2. Instalar Docker Engine y el plugin de Compose
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Usar docker sin sudo (aplica el grupo en esta sesión)
sudo usermod -aG docker $USER
newgrp docker

# 4. Verificar
docker --version
docker compose version
```

---

## A) EC2 #3: PostgreSQL

```bash
# 1. Conéctate e instala Docker (ver sección anterior)
ssh -J ubuntu@<IP_PUBLICA_EC2_1> ubuntu@<IP_PRIVADA_EC2_3>

# 2. Trae el compose de PostgreSQL (solo hace falta la carpeta deploy/postgres)
git clone https://github.com/JoshuaQ-rJ/fast_api_dockerizado.git
cd fast_api_dockerizado/deploy/postgres

# 3. Crea el .env con tus valores (contraseña solo con letras y números)
cp .env.example .env
nano .env

# 4. Levanta PostgreSQL
docker compose up -d

# 5. Verifica: el estado debe pasar a "(healthy)"
docker compose ps
docker compose logs db

# 6. Prueba la conexión con psql (dentro del contenedor)
docker exec -it postgres_db psql -U app_user -d app_db -c "SELECT version();"

# 7. Comprueba que el volumen existe (aquí viven los datos)
docker volume ls | grep pgdata
```

El volumen `pgdata` guarda los datos fuera del contenedor. Si borras el contenedor con `docker compose down`, los datos siguen ahí. **No uses `docker compose down -v`**, porque la opción `-v` borra el volumen y con él todos los datos.

---

## B) EC2 #2: API FastAPI

```bash
# 1. Conéctate e instala Docker (ver sección de instalación)
ssh -J ubuntu@<IP_PUBLICA_EC2_1> ubuntu@<IP_PRIVADA_EC2_2>

# 2. Clona el repo
git clone https://github.com/JoshuaQ-rJ/fast_api_dockerizado.git
cd fast_api_dockerizado

# 3. Crea el .env
cp .env.example .env
nano .env
#   Database_url=postgresql://app_user:<CLAVE>@<IP_PRIVADA_EC2_3>:5432/app_db
#   AWS_REGION=us-east-2
#   S3_BUCKET_NAME=<NOMBRE_DEL_BUCKET>

# 4. (Opcional) Comprueba que llegas al puerto 5432 de la EC2 #3
nc -zv <IP_PRIVADA_EC2_3> 5432

# 5. Construye y levanta la API. Al arrancar ejecuta "alembic upgrade head".
docker compose up -d --build

# 6. Revisa los logs: debe verse "Running upgrade ..." y "Uvicorn running on http://0.0.0.0:8000"
docker compose logs -f api      # Ctrl+C para salir
docker compose ps               # el estado debe pasar a "(healthy)"
```

### Probar con curl (desde la EC2 #2)

```bash
# Health
curl http://localhost:8000/health
# {"status":"ok"}

# Crear un producto
curl -X POST http://localhost:8000/product \
  -H "Content-Type: application/json" \
  -d '{"name":"Teclado","price":50000,"quantity":3,"category":"perifericos"}'

# Listar productos
curl http://localhost:8000/product

# Borrar un producto (cambia 1 por el id)
curl -i -X DELETE http://localhost:8000/product/1

# Subir una imagen: primero se crea un PNG de 1x1 píxel para la prueba
echo iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg== | base64 -d > prueba.png
curl -X POST http://localhost:8000/images -F "file=@prueba.png;type=image/png"
# {"id":1,"bucket":"<NOMBRE_DEL_BUCKET>","s3_key":"images/<uuid>.png"}
```

Después, en la consola de S3, abre el bucket: el archivo debe aparecer dentro de la carpeta `images/`. También puedes ver la referencia en la base de datos desde la EC2 #3:

```bash
docker exec -it postgres_db psql -U app_user -d app_db -c "SELECT * FROM app_inv_images;"
```

---

## C) Consola de AWS: S3 e IAM

### 1. Crear el bucket privado

1. S3 → **Create bucket**.
2. Nombre: `<NOMBRE_DEL_BUCKET>`. Región: **US East (Ohio) us-east-2**.
3. Object Ownership: **ACLs disabled**.
4. **Block all public access: activado** (las 4 casillas).
5. Deja el cifrado por defecto (SSE-S3) y pulsa **Create bucket**.

### 2. Crear la política IAM de mínimo privilegio

IAM → Policies → **Create policy** → pestaña **JSON**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SubirImagenes",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::<NOMBRE_DEL_BUCKET>/images/*"
    }
  ]
}
```

Nombre: `fastapi-s3-put-images`.

Esta política solo permite **subir** objetos dentro de `images/` en ese bucket: no permite leer, listar ni borrar. Es suficiente porque las imágenes son de máximo 5 MB y boto3 las sube con un único `PutObject`. Solo usa subida multiparte, que necesita más permisos, a partir de 8 MB.

### 3. Crear el IAM Role y asociarlo a la EC2 #2

1. IAM → Roles → **Create role**.
2. Trusted entity: **AWS service** → Use case: **EC2**.
3. Adjunta la política `fastapi-s3-put-images`.
4. Nombre: `fastapi-ec2-role` → **Create role**.
5. EC2 → selecciona la EC2 #2 → **Actions → Security → Modify IAM role** → elige `fastapi-ec2-role` → **Update IAM role**.
6. En la EC2 #2 reinicia la API para que boto3 cargue las credenciales:
   ```bash
   docker compose restart api
   ```

### 4. Si boto3 dice "Unable to locate credentials" dentro de Docker

boto3 obtiene las credenciales del rol desde el servicio de metadatos de la instancia (IMDSv2, `169.254.169.254`). IMDSv2 limita cuántos "saltos" de red puede dar la respuesta, y su valor por defecto es 1. Desde un contenedor Docker hay un salto extra (el contenedor y luego el host), así que la respuesta no llega. La solución es subir el límite a 2:

- **Consola:** EC2 → EC2 #2 → **Actions → Instance settings → Modify instance metadata options** → *Metadata response hop limit* = **2** → Save.
- **o AWS CLI:**
  ```bash
  aws ec2 modify-instance-metadata-options \
    --instance-id <ID_INSTANCIA_EC2_2> \
    --http-tokens required \
    --http-put-response-hop-limit 2 \
    --http-endpoint enabled \
    --region us-east-2
  ```

Después: `docker compose restart api`.

---

## D) Security Groups (mínimo privilegio)

Crea tres Security Groups en tu VPC y asigna cada uno a su EC2:

| Security Group | EC2 | Tipo | Puerto | Origen | Para qué |
|---|---|---|---|---|---|
| `sg-proxy` | #1 NPM | HTTP | 80 | `0.0.0.0/0` | Tráfico web público |
| `sg-proxy` | #1 NPM | HTTPS | 443 | `0.0.0.0/0` | Tráfico web público con TLS |
| `sg-proxy` | #1 NPM | Custom TCP | 81 | `<MI_IP>/32` | Panel de administración de NPM |
| `sg-proxy` | #1 NPM | SSH | 22 | `<MI_IP>/32` | Tu acceso SSH (bastión) |
| `sg-fastapi` | #2 API | Custom TCP | 8000 | `sg-proxy` | Solo NPM puede llamar a la API |
| `sg-fastapi` | #2 API | SSH | 22 | `sg-proxy` | SSH solo saltando desde el bastión |
| `sg-postgres` | #3 BD | PostgreSQL | 5432 | `sg-fastapi` | Solo la API puede consultar la BD |
| `sg-postgres` | #3 BD | SSH | 22 | `sg-proxy` | SSH solo saltando desde el bastión |

Deja las reglas de **salida** (outbound) como vienen por defecto, que permiten todo. Las EC2 privadas las necesitan para llegar al NAT (apt, Docker Hub, GitHub) y a S3.

**¿Por qué se usa un Security Group como origen en vez de una IP?**
- **Sigue a las instancias:** si la EC2 se reemplaza o cambia de IP privada, la regla sigue funcionando sin tocarla.
- **Es más preciso:** "desde `sg-fastapi`" significa "solo desde instancias que tengan ese SG". Una IP o un rango CIDR puede incluir otras máquinas de la misma subred.
- **Se lee mejor:** cada regla dice *quién* puede entrar, no *desde qué número*. Así queda a la vista la cadena Internet → proxy → API → BD.

---

## E) Nginx Proxy Manager: Proxy Host hacia la API

En el panel de NPM (`http://<IP_PUBLICA_EC2_1>:81`) → **Hosts → Proxy Hosts → Add Proxy Host**:

| Campo | Valor |
|---|---|
| Domain Names | tu dominio, o `<IP_PUBLICA_EC2_1>.nip.io` si no tienes uno |
| Scheme | `http` |
| Forward Hostname / IP | `<IP_PRIVADA_EC2_2>` |
| Forward Port | `8000` |
| Block Common Exploits | activado |
| Websockets Support | desactivado (la API no los usa) |

Pestaña **SSL** (opcional): *Request a new SSL Certificate* con Let's Encrypt, y activa *Force SSL*.

`nip.io` es un DNS gratuito: `1.2.3.4.nip.io` resuelve a `1.2.3.4`. Sirve para tener un nombre de dominio sin comprar uno.

**Probar desde tu PC:**

```bash
curl http://<IP_PUBLICA_EC2_1>.nip.io/health
curl http://<IP_PUBLICA_EC2_1>.nip.io/product
```

La documentación interactiva queda en `http://<IP_PUBLICA_EC2_1>.nip.io/docs`.

**Si NPM devuelve 502 Bad Gateway:** revisa que `sg-fastapi` permita el puerto 8000 desde `sg-proxy` y que `docker compose ps` en la EC2 #2 muestre la API como `healthy`.
