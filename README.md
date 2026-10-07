# Backend · FastAPI i PostgreSQL

Guia per executar el projecte **al teu ordinador** amb Docker. Cada membre de l'equip té la seva base de dades local: compartim el codi i les migracions amb Git, però no els registres de la base de dades.

## 1. Què arrencarem?

| Servei | Per a què serveix? |
|---|---|
| `frontend` | La web de React que obres al navegador |
| `backend` | L'API de FastAPI que rep les peticions de la web |
| `db` | PostgreSQL, on es guarden les dades |
| `pgadmin` | Una web per consultar i administrar PostgreSQL |

El fitxer `compose.yaml` és en aquest repositori, però **coordina els quatre serveis**. Per construir el frontend, llegeix el codi de la carpeta germana `../frontend`. No és FastAPI qui arrenca React: ho fa Docker Compose.

## 2. Primera vegada: preparar l'ordinador

Necessites Git i Docker Desktop obert amb el motor de contenidors Linux en marxa. En Linux també pots utilitzar Docker Engine amb Compose.

Comprova-ho des d'una terminal:

```bash
docker info
docker compose version
```

`docker info` ha de mostrar informació del servidor sense errors de connexió. Necessites Docker Compose 2.32 o posterior. No cal instal·lar Python, Node, PostgreSQL, pgAdmin ni Alembic a l'ordinador: s'instal·len dins dels contenidors.

Si encara no tens els repositoris, executa això des de la carpeta on guardes els projectes:

```bash
git clone https://github.com/UB-ES-F4-2026/backend.git
git clone https://github.com/UB-ES-F4-2026/frontend.git
cd backend
```

Si ja els tens, **no els tornis a clonar**. Obre una terminal a la carpeta `backend`. Han de quedar així:

```text
GitHub/
├── backend/       ← aquí hi ha compose.yaml; executa aquí els comandaments
└── frontend/      ← aquí hi ha el codi de React
```

Per exemple, en PowerShell, si els tens en aquesta ubicació:

```powershell
cd C:\Users\Alex\Documents\GitHub\backend
```

Adapta la ruta al teu ordinador. **Tots els comandaments següents s'executen des de `backend`**, encara que vulguis treballar en el frontend.

## 3. Arrencar tota l'aplicació

Abans del primer inici, crea **`backend/.env`** a partir de la plantilla. Des de `backend`, executa l'opció del teu sistema; aquests comandaments no sobreescriuen un `.env` existent.

PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Linux/macOS:

```bash
if [ ! -e .env ]; then cp .env.example .env; fi
```

Si ja tens `.env`, conserva'l. Compara els noms de les variables amb `.env.example` i afegeix les que faltin, mantenint les credencials de la teva instal·lació. No substitueixis el fitxer sencer.

Compose llegeix `.env` automàticament. `.env.example` només és una plantilla: no es llegeix durant l'arrencada. Si falta una variable necessària o és buida, Compose s'atura amb un missatge que n'indica el nom.

```bash
docker compose up --build --wait
```

Aquest és el comandament habitual: **arrenca frontend, backend, PostgreSQL i pgAdmin**. La primera vegada pot tardar uns minuts a descarregar i construir les imatges.

- `--build` construeix les imatges amb el codi i les dependències actuals.
- `--wait` espera que els serveis estiguin saludables i els deixa funcionant en segon pla.
- Sense noms de serveis al final, s'arrenca tot el conjunt.

Quan acabi correctament, obre:

| Què vols obrir? | Adreça amb els ports de la plantilla |
|---|---|
| Web de l'aplicació | http://localhost:5173 |
| Documentació de l'API | http://localhost:8000/docs |
| Comprovació de l'API i PostgreSQL | http://localhost:8000/api/health |
| Administració amb pgAdmin | http://localhost:5050 |

Si el teu `.env` té `BACKEND_PORT=8001`, utilitza http://localhost:8001/docs i http://localhost:8001/api/health. El port de la web continua sent 5173, llevat que també el canviïs.

La pantalla inicial de la web comprova la connexió amb l'API. A http://localhost:5173/api/health hauries de veure:

```json
{"status":"ok","service":"backend","database":"ok"}
```

Això comprova tot el recorregut: navegador → Vite → FastAPI → PostgreSQL. L'API executa `SELECT 1`; si la base de dades no respon, retorna HTTP 503.

### Si només vols arrencar una part

Tria **una** de les opcions següents segons què necessitis:

| Què necessites? | Comandament |
|---|---|
| Tota l'aplicació (opció habitual) | `docker compose up --build --wait` |
| Backend, PostgreSQL i pgAdmin | `docker compose up --build --wait backend pgadmin` |
| Frontend, backend i PostgreSQL | `docker compose up --build --wait frontend` |

El nom del servei és `frontend`, no `front`. Compose arrenca també les dependències: el frontend necessita el backend, i el backend necessita PostgreSQL. Arrencar el backend no arrenca el frontend.

Si abans havies arrencat només el backend i pgAdmin, pots executar l'opció de tota l'aplicació per afegir-hi el frontend. No cal aturar-ho tot abans. Seleccionar uns serveis tampoc no atura els altres que ja estiguin en marxa.

## 4. Treballar cada dia

Obre Docker Desktop i una terminal a `backend`.

**Per programar i veure els canvis quan deses els fitxers:**

```bash
docker compose up --build --watch
```

Deixa aquesta terminal oberta. Compose sincronitza el codi i activa la recàrrega de FastAPI i Vite. Amb `Ctrl+C` atures aquesta execució i els serveis que ha arrencat.

Si ja havies arrencat els serveis amb `--wait`, activa la sincronització en una altra terminal:

```bash
docker compose watch
```

En aquest cas, `Ctrl+C` atura la sincronització; els serveis continuen en segon pla.

Per desenvolupar només el backend i PostgreSQL:

```bash
docker compose up --build --watch backend
```

Sense Watch, desar fitxers no actualitza el codi del contenidor. Després de rebre canvis de l'equip o modificar la configuració, executa:

```bash
docker compose up --build --wait
```

Aquest comandament també aplica les migracions pendents quan arrenca el backend. `docker compose restart` no reconstrueix les imatges ni aplica canvis de `.env`.

## 5. Aturar el projecte sense perdre les dades

Des de `backend`:

```bash
docker compose down
```

Atura i elimina els contenidors del projecte, però conserva els volums amb les dades. Per tornar-hi, executa el comandament d'arrencada habitual.

**No afegeixis `-v` a `docker compose down` ni esborris els volums des de Docker Desktop:** eliminaria les dades locals. No ho utilitzis per intentar solucionar un error.

| Volum | Què conserva? |
|---|---|
| `postgres_data` | Taules, registres i historial de migracions |
| `pgadmin_data` | Compte i configuració de pgAdmin |

Els noms complets tenen per defecte el prefix `fintech-local_`. No canviïs el nom del projecte Compose per resoldre problemes: podria seleccionar uns altres volums i semblaria que les dades han desaparegut.

## 6. Com funciona la configuració: ports i credencials

La configuració local es defineix a `backend/.env`, que no es puja a Git. El pas per crear-lo és a l'apartat 3.

| Fitxer | Funció |
|---|---|
| `.env.example` | Plantilla compartida amb els valors per preparar una instal·lació local nova |
| `.env` | Valors personals que Compose llegeix per configurar els contenidors |
| `compose.yaml` | Defineix els serveis i els passa les variables, sense duplicar els valors locals |

Compose passa les mateixes credencials al backend i a PostgreSQL. SQLAlchemy les llegeix de l'entorn del contenidor; no obre `.env.example` ni necessita una còpia de `.env` dins del contenidor. Els noms i ports interns, com `db:5432`, es mantenen a Compose.

Si has exportat una variable amb el mateix nom a la terminal, té prioritat sobre `.env`. En l'ús habitual d'aquesta guia, edita només `.env` i evita definir els mateixos valors en diversos llocs.

Edita `.env` segons les teves necessitats:

| Variable | Valor de la plantilla | Ús |
|---|---|---|
| `FRONTEND_PATH` | `../frontend` | Ruta al repositori frontend |
| `BACKEND_PORT` | `8000` | Port de l'API a l'ordinador |
| `FRONTEND_PORT` | `5173` | Port de la web |
| `POSTGRES_PORT` | `5433` | Port de PostgreSQL a l'ordinador |
| `POSTGRES_DB` | `fintech` | Nom de la base de dades |
| `POSTGRES_USER` | `fintech` | Usuari de PostgreSQL |
| `POSTGRES_PASSWORD` | `fintech_local` | Contrasenya de PostgreSQL |
| `PGADMIN_PORT` | `5050` | Port de pgAdmin |
| `PGADMIN_DEFAULT_EMAIL` | `admin@example.com` | Usuari de pgAdmin |
| `PGADMIN_DEFAULT_PASSWORD` | `fintech` | Contrasenya de pgAdmin |

Si el port 8000 està ocupat, posa `BACKEND_PORT=8001` a `.env` i torna a executar `docker compose up --build --wait`. No cal canviar el codi de React.

Els ports publicats escolten només a `127.0.0.1`. Són valors per a desenvolupament local, no una configuració de producció.

**Canviar les credencials a `.env` no canvia les d'una base de dades o un compte de pgAdmin ja creats.** Els volums conserven els valors inicials. Si necessites canviar-los, coordina-ho amb la persona responsable de DevOps; no esborris els volums.

## 7. Consultar la base de dades amb pgAdmin

No cal instal·lar pgAdmin a l'ordinador.

1. Arrenca tot el projecte, o l'opció `backend pgadmin`.
2. Obre http://localhost:5050.
3. Entra amb les credencials amb què vas inicialitzar pgAdmin. En una instal·lació nova amb la plantilla actual són `admin@example.com` i `fintech`. Si el volum ja existia, conserva la contrasenya anterior encara que la plantilla hagi canviat.
4. Al panell lateral, obre **Desarrollo → Fintech local → Databases → fintech**. Els noms del grup i del servidor estan configurats així; la base pot tenir un altre nom si l'has personalitzat.

El servidor es registra automàticament en el primer inici; no cal afegir-lo manualment. El script `docker/pgadmin/bootstrap.py` prepara la connexió i el fitxer `.pgpass` amb permisos `0600`. Els inicis següents conserven la configuració.

| Des d'on et connectes a PostgreSQL? | Host i port |
|---|---|
| Des de backend o pgAdmin dins de Docker | `db:5432` |
| Des d'un programa instal·lat al teu ordinador | `localhost:5433` (o `POSTGRES_PORT`) |

El backend es connecta directament a PostgreSQL: no necessita pgAdmin per funcionar. Evita modificar l'estructura de les taules manualment amb pgAdmin; els canvis compartits d'esquema es fan amb migracions.

## 8. Models i migracions (quan canvies l'estructura de dades)

Una migració és un fitxer versionat que descriu un canvi a la base de dades, com ara crear una taula o afegir una columna. Així cada company pot aplicar el mateix canvi a la seva base local.

**Si només vols arrencar el projecte o has rebut migracions d'un company, no n'has de generar cap.** El backend executa `alembic upgrade head` abans d'iniciar FastAPI. Si falla, l'API no arrenca.

### Si has creat o modificat un model

1. Defineix el model a `app/models/`, heretant de `Base` de `app.database`. El registre importa automàticament els mòduls d'aquesta carpeta.
2. Amb Docker i PostgreSQL en marxa, genera una migració des de `backend`:

   ```bash
   docker compose run --rm --build backend alembic revision --autogenerate -m "Descripcio del canvi"
   ```

3. Revisa el fitxer nou d'`alembic/versions/` abans d'aplicar-lo. La generació automàtica pot interpretar un canvi de nom com una eliminació i una creació; comprova especialment qualsevol eliminació de taules o columnes.
4. Aplica el canvi i arrenca l'aplicació:

   ```bash
   docker compose up --build --wait
   ```

5. Inclou **el model i la migració junts** al commit.

El comandament de generació aplica les migracions anteriors abans de crear la nova. La carpeta `alembic/` està muntada al contenidor: el fitxer generat queda al repositori del teu ordinador.

No utilitzis `Base.metadata.create_all()` ni executis `alembic init`: Alembic ja està configurat. No modifiquis migracions que altres companys ja hagin aplicat. Si apareixen diversos `heads`, cal coordinar-ne la integració.

La recàrrega d'Uvicorn no aplica migracions. Si el codi i les migracions ja estan actualitzats al contenidor en marxa, pots aplicar-les amb:

```bash
docker compose exec backend alembic upgrade head
```

Consultes útils amb el backend en marxa:

```bash
# Revisió aplicada a la teva base de dades
docker compose exec backend alembic current

# Historial de migracions
docker compose exec backend alembic history

# Comprovar si els models tenen canvis sense migració
docker compose exec backend alembic check
```

Per a `check`, sincronitza o reconstrueix abans el codi perquè examini els models actuals.

En Linux, si la generació falla per permisos d'escriptura, utilitza:

```bash
docker compose run --rm --build --user "$(id -u):$(id -g)" backend alembic revision --autogenerate -m "Descripcio del canvi"
```

Actualment només hi ha la revisió inicial `0001`, que inicialitza l'historial `alembic_version`. Encara no hi ha taules de negoci ni dades d'exemple; això no és un error d'arrencada.

## 9. Si alguna cosa falla

Primer recull l'estat i els errors des de `backend`:

```bash
docker compose ps -a
docker compose logs --tail 60 backend frontend db pgadmin
```

| Què passa? | Què has de revisar? |
|---|---|
| Compose indica que falta una variable | Crea `.env` si no existeix, o afegeix-hi la variable indicada; no sobreescriguis les credencials existents |
| Docker no respon | Obre Docker Desktop, espera que el motor estigui en marxa i executa `docker info` |
| No troba `compose.yaml` | Comprova que la terminal sigui a `backend` |
| No troba el codi del frontend | Comprova la carpeta germana `frontend` o el valor de `FRONTEND_PATH` |
| El frontend no apareix a la llista | Potser només has arrencat backend i pgAdmin; executa `docker compose up --build --wait` |
| El frontend apareix aturat o no saludable | Consulta els logs de frontend i backend; no pressuposis que falta arrencar-lo |
| Un port està ocupat | Canvia el port corresponent a `.env` i torna a executar `up --build --wait` |
| El backend no arrenca | Revisa els logs de backend i db: pot fallar la connexió o una migració |
| La contrasenya falla després de canviar `.env` | La instal·lació existent conserva la contrasenya anterior |
| pgAdmin triga a estar disponible | El primer inici pot tardar; comprova l'estat i els logs |
| No apareixen els canvis de codi | Activa Watch o reconstrueix les imatges |
| Falten taules d'un model nou | Comprova que s'hagi generat, compartit i aplicat la migració |

Si necessites ajuda, comparteix **el comandament executat, la carpeta des d'on l'has executat i la sortida d'error**, indicant en quin ordinador passa. Revisa que els logs no continguin credencials abans de compartir-los. No enviïs el teu `.env`.

## 10. Referència del codi i proves

| Fitxer o carpeta | Responsabilitat |
|---|---|
| `compose.yaml` | Serveis, dependències, xarxa, ports i volums |
| `Dockerfile`, `requirements.txt` | Entorn Python i dependències |
| `app/database.py` | Base dels models, motor i sessions de SQLAlchemy |
| `app/model_registry.py`, `app/models/` | Descobriment i definició dels models |
| `app/start.py` | Aplicació de migracions abans de l'arrencada |
| `alembic/`, `alembic.ini` | Configuració i historial de migracions |
| `docker/pgadmin/` | Configuració inicial de pgAdmin |
| `tests/test_migrations.py` | Prova de migracions en una base temporal |

Les rutes poden obtenir una sessió amb `Depends(get_db)`. Les operacions d'escriptura han de confirmar la transacció amb `commit()` i gestionar els errors.

Des de `backend`, per validar la configuració de Compose:

```bash
docker compose config --quiet
```

Amb el backend i PostgreSQL en marxa, per executar les proves:

```bash
docker compose exec backend python -m unittest discover -s tests -v
```

La prova crea i elimina únicament la seva pròpia base temporal. Comprova la creació de taules, l'addició de columnes, la conservació de registres i la reaplicació de migracions.

La guia específica de React és al [README del frontend](https://github.com/UB-ES-F4-2026/frontend#readme). Aquesta configuració cobreix només el desenvolupament local.
