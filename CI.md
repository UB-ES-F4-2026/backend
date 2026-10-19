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
