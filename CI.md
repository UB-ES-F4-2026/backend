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

## Release y staging

Flujo: se crea `release/x.y` desde `dev` y, con cada push a esa rama, `ci.yml` pasa los tests, publica la imagen y la despliega en staging (job `deploy-staging`, solo si la variable `STAGING_DEPLOY_ENABLED` es `true`). Las correcciones de la release se hacen con PR hacia `release/x.y` y se vuelven a llevar a `dev`. Al fusionar `release/x.y` en `main`, la CI no vuelve a construir la imagen: despliega en producción la misma que se probó en staging (job `promote`). Los hotfix siguen el mismo camino desde `hotfix/*`, sin pasar por staging. Las PR hacia `main` se fusionan con «Create a merge commit»: con squash o rebase no se despliega nada.

Staging es el proyecto Compose `fintech-staging` en `/app/fintech-staging` del servidor: `compose.production.yaml` con el override `compose.staging.yaml` y su propio `.env.staging`. No comparte contenedores, volúmenes, base de datos ni credenciales con producción. Los detalles del despliegue y los pasos manuales en el servidor están en [agents/devops.md](agents/devops.md).

Para abrirlo desde tu ordenador, con un túnel SSH (la web y la API quedan en http://localhost:8082):

```bash
ssh -N -L 8082:127.0.0.1:8082 <usuario>@<servidor>
```
