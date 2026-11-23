# CI del backend

GitHub Actions pasa el análisis estático (Ruff), construye el backend y ejecuta todos los tests en cada push a cualquier rama y en cada PR hacia `main`. Los resultados se ven en la pestaña Actions.

## Qué se ejecuta en cada fase

| Cuándo | Qué se ejecuta | ¿Impide fusionar? |
|---|---|---|
| Push a cualquier rama | Ruff y todos los tests (`ci.yml`) | No: solo informa |
| Push a `release/*` o `hotfix/*` | Además, publica la imagen; desde `release/*` la despliega en staging (ver «Release y staging») | — |
| PR hacia `dev` o `release/*` | E2E de Playwright (`e2e-playwright.yml`) | No: la PR sale en rojo, pero `dev` y `release/*` no tienen checks obligatorios |
| PR hacia `main` | Ruff, tests, origen de la PR y E2E | Sí, «Backend required checks» (Ruff, tests y origen). Los E2E salen en rojo si fallan, pero no son obligatorios |

- Los E2E usan el frontend de la misma rama que el destino de la PR (`dev`, `release/x.y` o `main`). En una PR de `release/*` o `hotfix/*` hacia `main`, si el frontend tiene una rama con el mismo nombre, usan esa: es la combinación que se desplegará. Si el frontend no tiene la rama necesaria, fallan con un mensaje que lo indica.
- A `main` solo se llega desde `release/*` o `hotfix/*`. Una PR de `dev` directamente a `main` falla: hay que crear `release/x.y` desde `dev`.
- Un hotfix sale de `main` y, después de fusionarlo, se lleva también a `dev` con una PR desde `hotfix/*`. Si no, la siguiente release lo desharía.
- Proteger `dev` y `release/*` con checks obligatorios requiere permisos de administrador del repositorio, que el equipo no tiene.

## Análisis estático (Ruff)

El job `lint` de `ci.yml` pasa Ruff en cada push y PR, y forma parte de «Backend required checks»: un error de Ruff impide fusionar en `main`. Las reglas están en `ruff.toml` (E4, E7, E9 y F, sin las migraciones de `alembic/versions/`).

Para ejecutarlo en local con la misma versión que la CI, sin instalar nada, desde `backend`:

```bash
docker run --rm -v "$PWD":/io:z -w /io ghcr.io/astral-sh/ruff:0.17.4 check
```

En PowerShell, cambia `"$PWD":/io:z` por `"${PWD}:/io"`. Para corregir automáticamente lo que se pueda, añade `--fix` al final; revisa el diff antes de hacer commit.

Si se actualiza la versión de Ruff, cámbiala a la vez en `ci.yml` y aquí.

## Tests

Para probarlo en local, abre Docker Desktop y ejecuta desde `backend`:

```bash
docker compose -f compose.ci.yaml up --build --wait --wait-timeout 180
docker compose -f compose.ci.yaml exec -T backend python -m unittest discover -s tests -v
```

Si falla, consulta los logs:

```bash
docker compose -f compose.ci.yaml logs --no-color
```

Al terminar, elimina el entorno de prueba:

```bash
docker compose -f compose.ci.yaml down --volumes --remove-orphans
```

La base de datos de prueba es temporal. Mantén `-f compose.ci.yaml` en los comandos para no tocar el entorno de desarrollo.

## Tests E2E

El workflow `E2E Playwright Tests` ejecuta el seed y los tests de Playwright del frontend en cada PR a `dev`. Para reproducirlo en local hay dos opciones.

### Entorno aislado (recomendado)

`compose.e2e.yaml` levanta una base de datos vacía, el backend, el frontend, el seed y Playwright, sin publicar puertos ni tocar el entorno de desarrollo. No necesita `.env` ni tener Node o Playwright instalados. Desde `backend`:

```bash
sh scripts/run-e2e.sh
```

- El script para el entorno antes y después de cada ejecución, así que la base de datos empieza siempre vacía, aunque una ejecución anterior se interrumpiera.
- Devuelve el código de salida de Playwright.
- El informe queda en `e2e-report/playwright-report/index.html`, también si los tests fallan.
- Usa el frontend de `../frontend`. Para probar otra carpeta o rama: `FRONTEND_PATH=/ruta/al/frontend sh scripts/run-e2e.sh`.
- En PowerShell, el equivalente está en el [README](README.md#11-tests-e2e-amb-playwright).

### Sobre el entorno de desarrollo

Para probar los E2E contra el entorno levantado con `compose.yaml`, sigue [agents/backend.md](agents/backend.md#validació). El seed escribe en la base de datos de desarrollo de forma permanente y solo puede ejecutarse una vez, y hace falta Python con dependencias, Node y Chromium en el host.

## Release y staging

Flujo: se crea `release/x.y` desde `dev` y, con cada push a esa rama, `ci.yml` pasa los tests, publica la imagen y la despliega en staging (job `deploy-staging`, solo si la variable `STAGING_DEPLOY_ENABLED` es `true`). Las correcciones de la release se hacen con PR hacia `release/x.y` y se vuelven a llevar a `dev`. Al fusionar `release/x.y` en `main`, la CI no vuelve a construir la imagen: despliega en producción la misma que se probó en staging (job `promote`). Los hotfix siguen el mismo camino desde `hotfix/*`, sin pasar por staging. Las PR hacia `main` se fusionan con «Create a merge commit»: con squash o rebase no se despliega nada.

Staging es el proyecto Compose `fintech-staging` en `/app/fintech-staging` del servidor: `compose.production.yaml` con el override `compose.staging.yaml` y su propio `.env.staging`. No comparte contenedores, volúmenes, base de datos ni credenciales con producción. Los detalles del despliegue y los pasos manuales en el servidor están en [agents/devops.md](agents/devops.md).

Para abrirlo desde tu ordenador, con un túnel SSH (la web y la API quedan en http://localhost:8082):

```bash
ssh -N -L 8082:127.0.0.1:8082 <usuario>@<servidor>
```
