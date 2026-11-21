# CI del backend

GitHub Actions construye el backend y comprueba el arranque y los tests de migraciones en cada push y PR a `main`. Los resultados se ven en la pestaña Actions.

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

## Análisis estático (Ruff)

El job `lint` de `ci.yml` pasa Ruff en cada push y PR, y forma parte de «Backend required checks»: un error de Ruff impide fusionar en `main`. Las reglas están en `ruff.toml` (E4, E7, E9 y F, sin las migraciones de `alembic/versions/`).

Para ejecutarlo en local con la misma versión que la CI, sin instalar nada, desde `backend`:

```bash
docker run --rm -v "$PWD":/io:z -w /io ghcr.io/astral-sh/ruff:0.17.4 check
```

En PowerShell, cambia `"$PWD":/io:z` por `"${PWD}:/io"`. Para corregir automáticamente lo que se pueda, añade `--fix` al final; revisa el diff antes de hacer commit.

Si se actualiza la versión de Ruff, cámbiala a la vez en `ci.yml` y aquí.
