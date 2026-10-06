# Backend · FastAPI y PostgreSQL

Guía para levantar el backend y su base de datos en local con Docker. El repositorio incluye SQLAlchemy, Alembic y la configuración de pgAdmin, además de Docker Compose para arrancar también el [frontend](https://github.com/UB-ES-F4-2026/frontend).

## 1. Requisitos

- Git.
- Docker Desktop abierto, con el motor de contenedores Linux iniciado; en Linux también sirve Docker Engine.
- Docker Compose 2.32 o posterior. Compruébalo con `docker compose version`.

Python, PostgreSQL y Alembic se instalan dentro de los contenedores. No necesitas instalarlos en tu ordenador, crear un entorno virtual ni ejecutar `alembic init`.

## 2. Preparar los repositorios

Si todavía no los tienes, ejecuta estos comandos desde la carpeta donde guardas tus proyectos:

```bash
git clone https://github.com/UB-ES-F4-2026/backend.git
git clone https://github.com/UB-ES-F4-2026/frontend.git
cd backend
```

Si ya están clonados, abre una terminal en `backend`. La estructura para arrancar la aplicación completa debe ser:

```text
GitHub/
├── backend/       ← compose.yaml y los comandos de esta guía
└── frontend/
```

Los comandos siguientes se ejecutan desde **backend**, salvo indicación contraria.

## 3. Configuración local

Puedes arrancar con los valores predeterminados sin crear ningún archivo. Para personalizar puertos o credenciales, copia `.env.example` a `.env` **solo si no tienes ya un `.env`**.

PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Edita `.env` con los valores que necesites. Este archivo está excluido de Git.

| Variable | Valor predeterminado | Uso |
|---|---|---|
| `FRONTEND_PATH` | `../frontend` | Ubicación del otro repositorio, relativa a backend |
| `BACKEND_PORT` | `8000` | Puerto de la API en tu ordenador |
| `FRONTEND_PORT` | `5173` | Puerto de la web |
| `POSTGRES_PORT` | `5433` | Puerto de PostgreSQL en tu ordenador |
| `POSTGRES_DB` | `fintech` | Base de datos |
| `POSTGRES_USER` | `fintech` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | `fintech_local` | Contraseña local de PostgreSQL |
| `PGADMIN_PORT` | `5050` | Puerto de pgAdmin |
| `PGADMIN_DEFAULT_EMAIL` | `admin@example.com` | Usuario de pgAdmin |
| `PGADMIN_DEFAULT_PASSWORD` | `admin_local_change_me` | Contraseña local de pgAdmin |

Si el puerto 8000 está ocupado, establece `BACKEND_PORT=8001`: entonces la API estará en http://localhost:8001 y su documentación en http://localhost:8001/docs. Esto no cambia la conexión interna entre contenedores.

Las credenciales de ejemplo son para desarrollo local. Los puertos publicados escuchan solo en `127.0.0.1`.

## 4. Levantar backend, base de datos y pgAdmin

```bash
docker compose up --build --wait backend pgadmin
```

Compose también arranca `db`, porque el backend y pgAdmin dependen de él. El comando termina cuando los servicios están saludables y los deja en segundo plano. La primera construcción y el primer inicio de pgAdmin pueden tardar varios minutos.

Para arrancar también React:

```bash
docker compose up --build --wait
```

No necesitas crear la base de datos ni conectar el backend manualmente:

1. PostgreSQL crea el usuario y la base indicados en la configuración cuando su volumen está vacío.
2. Compose espera a que PostgreSQL esté disponible.
3. El backend ejecuta `alembic upgrade head` y aplica las migraciones pendientes.
4. FastAPI arranca si las migraciones terminan correctamente.
5. pgAdmin crea su cuenta y registra el servidor en su primer arranque.

## 5. Comprobar la conexión con PostgreSQL

Con los puertos predeterminados:

- API y documentación: http://localhost:8000/docs
- Comprobación de API y base de datos: http://localhost:8000/api/health
- pgAdmin: http://localhost:5050
- Web, si has arrancado todo: http://localhost:5173

Si usas `BACKEND_PORT=8001`, cambia el 8000 de las URLs de la API por 8001.

La ruta `/api/health` consulta PostgreSQL con `SELECT 1`. Debe responder:

```json
{"status":"ok","service":"backend","database":"ok"}
```

También puedes comprobar los servicios y sus logs:

```bash
docker compose ps
docker compose logs --tail 50 backend db
```

La conexión interna usa `db:5432`; desde una aplicación instalada en tu ordenador se usa `localhost:5433`, o el valor de `POSTGRES_PORT`. Cambiar ese puerto publicado no cambia el puerto interno 5432.

## 6. Acceder a pgAdmin

Abre http://localhost:5050 e inicia sesión con `admin@example.com` / `admin_local_change_me`, salvo que hayas configurado otros valores.

En el explorador, abre el grupo **Desarrollo**, el servidor **Fintech local** y la base **fintech**. El servidor ya tiene el host, puerto, usuario y archivo de contraseña configurados; no hace falta añadir una conexión manualmente. pgAdmin es la herramienta de administración: el backend se conecta directamente a PostgreSQL y no necesita pgAdmin para funcionar.

La configuración de pgAdmin también persiste entre arranques.

## 7. Desarrollo y actualización del código

Para desarrollar el backend con recarga automática:

```bash
docker compose up --build --watch backend
```

Para desarrollar ambos repositorios:

```bash
docker compose up --build --watch
```

Si ya están arrancados en segundo plano, puedes activar la sincronización en otra terminal con `docker compose watch`. Los cambios de `app/` se copian al contenedor y Uvicorn recarga la API.

Después de obtener cambios del equipo, o de modificar dependencias/configuración:

```bash
docker compose up --build --wait
```

Sin Watch activo, los cambios de código requieren reconstruir la imagen. Cambiar `.env` también requiere volver a ejecutar `up`; `restart` no actualiza las variables del contenedor.

## 8. Modelos SQLAlchemy y migraciones Alembic

Los modelos se definen en `app/models/` y heredan de `Base` de `app.database`. Alembic importa automáticamente los módulos de esa carpeta.

**Definir un modelo no crea su tabla por sí solo:** quien cambie el esquema debe generar y revisar una migración. Los demás la aplicarán automáticamente al arrancar.

Desde backend, después de modificar los modelos:

```bash
docker compose run --rm --build backend alembic revision --autogenerate -m "Descripcion del cambio"
```

Este comando construye la imagen con los modelos actuales, aplica las revisiones anteriores y guarda una revisión nueva en `alembic/versions/`, que está montado desde el repositorio.

Revisa el archivo antes de aplicarlo. En especial, los cambios de nombre pueden aparecer como borrados y creaciones y necesitar corrección. No modifiques revisiones que otros compañeros ya hayan aplicado.

Para aplicar la revisión y arrancar el código actualizado:

```bash
docker compose up --build --wait
```

Sube a Git **el modelo y su migración juntos**. La recarga de Uvicorn no ejecuta migraciones; si el contenedor ya contiene el código actualizado, puedes aplicarlas directamente con `docker compose exec backend alembic upgrade head`.

Comandos de consulta:

```bash
docker compose exec backend alembic current
docker compose exec backend alembic history
docker compose exec backend alembic check
```

`alembic check` compara la base con los modelos presentes en el contenedor; sincronízalos o reconstruye antes. Si se generan varias ramas de migraciones, hay que resolver sus heads antes de integrar.

En Linux, si aparecen errores de permisos al generar revisiones, ejecuta el comando con tu UID/GID:

```bash
docker compose run --rm --build --user "$(id -u):$(id -g)" backend alembic revision --autogenerate -m "Descripcion del cambio"
```

Actualmente la revisión `0001` inicializa el historial `alembic_version`. Aún no hay modelos de negocio ni datos de ejemplo.

## 9. Parar y conservar los datos

```bash
docker compose down
```

Este comando detiene el conjunto y elimina sus contenedores, conservando los volúmenes:

- `postgres_data`: tablas, registros e historial Alembic.
- `pgadmin_data`: cuenta y configuración de pgAdmin.

Por defecto, sus nombres completos llevan el prefijo `fintech-local_`. Al arrancar otra vez se reutilizan.

**No añadas `-v` a `docker compose down` si quieres conservar los datos:** esa opción elimina los volúmenes. Cambiar el nombre del proyecto Compose selecciona otros volúmenes. Una actualización de la versión mayor de PostgreSQL debe planificarse.

Las variables `POSTGRES_DB`, `POSTGRES_USER` y las contraseñas inicializan una instalación nueva; cambiarlas en `.env` no modifica automáticamente usuarios o contraseñas de una base ya creada. Lo mismo ocurre con la cuenta inicial de pgAdmin. Actualiza esos datos en el servicio correspondiente sin borrar los volúmenes.

## 10. Archivos y pruebas

| Archivo/carpeta | Responsabilidad |
|---|---|
| `compose.yaml` | Servicios, red, puertos y volúmenes |
| `Dockerfile`, `requirements.txt` | Entorno Python y dependencias fijadas |
| `app/database.py` | Base de modelos, conexión y sesiones SQLAlchemy |
| `app/models/` | Modelos del proyecto |
| `app/start.py` | Migraciones antes del arranque |
| `alembic/`, `alembic.ini` | Configuración e historial de migraciones |
| `docker/pgadmin/` | Registro automático del servidor |
| `tests/test_migrations.py` | Prueba de migraciones en una base temporal aislada |

Las rutas pueden usar `Depends(get_db)` de `app.database` para recibir una sesión por petición. Las escrituras deben confirmar su transacción con `commit()` y gestionar los errores según corresponda.

```bash
docker compose config --quiet
docker compose exec backend python -m unittest discover -s tests -v
```

La prueba crea una base temporal propia, comprueba creación de tablas, cambios de columnas y conservación de datos, y elimina únicamente esa base al terminar.

## Problemas frecuentes

| Problema | Qué revisar |
|---|---|
| Docker no responde | Abre Docker Desktop y ejecuta `docker info` |
| Puerto ocupado | Cambia el puerto publicado en `.env` y vuelve a ejecutar `up` |
| Backend no arranca | Consulta `docker compose logs backend db`; puede haber un error de conexión o migración |
| Faltan tablas | Genera, revisa y aplica la migración del modelo |
| Contraseña PostgreSQL incorrecta tras editar `.env` | El volumen conserva la contraseña anterior |
| pgAdmin tarda en responder | Espera a que aparezca saludable en `docker compose ps` |
| No aparecen cambios de código | Activa Watch o reconstruye la imagen |
| Frontend no encontrado | Revisa la carpeta hermana o `FRONTEND_PATH` |

El despliegue descrito es local. Para cambiar de tecnología, adapta el Dockerfile, el arranque, el healthcheck y las migraciones del servicio afectado; PostgreSQL y sus volúmenes pueden conservarse. La guía de la web está en el [README de frontend](https://github.com/UB-ES-F4-2026/frontend#readme).
