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

## Tests E2E

El workflow `E2E Playwright Tests` ejecuta el seed y los tests de Playwright del frontend en cada PR a `dev`. Para reproducirlo en local hay dos opciones.

### Entorno aislado (recomendado)

`compose.e2e.yaml` levanta una base de datos vacía, el backend, el frontend, el seed y Playwright, sin publicar puertos ni tocar el entorno de desarrollo. No necesita `.env` ni tener Node o Playwright instalados. Desde `backend`:

```bash
docker compose -f compose.e2e.yaml run --rm --build playwright
docker compose -f compose.e2e.yaml down
```

- El comando devuelve el código de salida de Playwright.
- El informe queda en `e2e-report/playwright-report/index.html`, también si los tests fallan.
- Usa el frontend de `../frontend`. Para probar otra carpeta o rama, cambia la ruta: `FRONTEND_PATH=/ruta/al/frontend docker compose -f compose.e2e.yaml run --rm --build playwright`.
- Ejecuta siempre el `down` al terminar: si el entorno queda levantado, la siguiente ejecución reutiliza la base de datos con los datos del seed anterior.

### Sobre el entorno de desarrollo

Para probar los E2E contra el entorno levantado con `compose.yaml`, sigue [agents/backend.md](agents/backend.md#validació). El seed escribe en la base de datos de desarrollo de forma permanente y solo puede ejecutarse una vez, y hace falta Python con dependencias, Node y Chromium en el host.
