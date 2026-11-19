# Rol Backend

Implementes canvis a l'API: rutes, esquemes, models, migracions i tests. Treballes dins de `app/` seguint els patrons existents; la lògica nova s'assembla a la que ja hi ha.

## Procediment

1. **Llegeix la issue** (`gh issue view <n> -R UB-ES-F4-2026/backend`). Extreu els criteris d'acceptació: cada un acabarà cobert per un test o per una comprovació descrita al PR. Si un criteri és ambigu, tria la interpretació més conservadora i deixa-la escrita al PR.
2. **Localitza el codi afectat** amb el mapa de sota i llegeix els mòduls que tocaràs i els tests que els cobreixen.
3. **Implementa** seguint les convencions. Un canvi d'esquema de dades porta model i migració al mateix commit.
4. **Escriu o amplia tests** a `tests/` per a cada criteri i per a cada codi d'error nou.
5. **Actualitza el seed E2E** segons [Seed E2E](#seed-e2e). Està fet quan, amb el codi de la branca i sobre una BD buida, `seed_e2e_testing_data.py` acaba sense cap ❌ i deixa totes les dades que els fluxos de `../frontend/e2e/` necessiten. Si el canvi no afecta cap dada del seed, digues-ho al PR amb el motiu.
6. **Valida** amb les ordres de la secció final. Fins que no passa tot, la tasca no està feta.
7. **Entrega**: PR cap a la branca `feat/US…` de la història d'usuari (les `feat` es fusionen a `dev`, i `dev` a `main` a cada release) amb `Closes #n`, resum del contracte de l'API (rutes, camps, codis d'estat) perquè el frontend el pugui consumir, els canvis al seed i les decisions preses sobre criteris ambigus.

## Mapa del codi

| Què | On |
|---|---|
| Aplicació, routers inclosos, `/api/health` | `app/main.py` |
| Rutes: un mòdul per recurs, `APIRouter` amb prefix `/api/<recurs>` | `app/api/routes/` |
| Dependències `DbSession` i `CurrentUser` (sessió per cookie) | `app/api/deps.py` |
| Esquemes Pydantic (`*Create`, `*Read`, requests) | `app/schemas/` |
| Models SQLAlchemy, un fitxer per taula, registrats automàticament | `app/models/` |
| Hash de contrasenyes i tokens de sessió | `app/core/security.py` |
| Motor, `Base`, `get_db` | `app/database.py` |
| Migracions `<hash>_descripcio.py` | `alembic/versions/` |
| Seed de dades per als E2E i el desenvolupament local | `seed_e2e_testing_data.py` |
| Workflow E2E (Playwright del frontend `dev` contra aquest backend) | `.github/workflows/e2e-playwright.yml` |
| Tests `unittest`, un fitxer per recurs | `tests/` |

## Convencions

### Rutes

- Un router per recurs, prefix `/api/<recurs>`, registrat a `app/main.py`.
- Les rutes públiques són només les de `PUBLIC_ROUTES` a `tests/test_route_protection.py`; qualsevol altra depèn de `CurrentUser`. Una ruta pública nova s'afegeix a aquesta llista de manera deliberada i justificada al PR.
- La sessió viatja a la cookie `session` (`HttpOnly`, `Secure`, `SameSite=Lax`): mai en URL ni en cos de resposta.
- Errors amb `HTTPException` i `detail` curt en anglès; el frontend els tradueix a missatges d'usuari. Codis: 401 sessió, 403 recurs d'un altre usuari, 404 no trobat, 409 conflicte d'unicitat; 422 el posa Pydantic.
- La sessió de BD arriba per `DbSession`. Les escriptures fan `commit()` explícit i capturen `IntegrityError` amb `rollback()`.

### Esquemes

- `XRead` amb `model_config = ConfigDict(from_attributes=True)`; `XCreate` amb restriccions a `Field` (`min_length`, `gt`, …).
- Camps en `snake_case` i amb el mateix nom que al model: el frontend els copia tal qual als seus tipus.
- Correus normalitzats a minúscules amb `field_validator`.

### Models

- `Mapped[...]` + `mapped_column`, heretant de `Base` d'`app.database`, que ja fixa la convenció de noms d'índexs i restriccions.
- Diners en cèntims (`int` amb `CheckConstraint >= 0`). Dates `DateTime(timezone=True)` en UTC. Enumeracions `class X(str, Enum)` mapejades amb `SqlEnum(..., native_enum=True, values_callable=...)`.
- Claus foranes amb `ondelete` explícit i `index=True`.

### Migracions

- Genera-la amb la BD en marxa: `docker compose run --rm --build backend alembic revision --autogenerate -m "Descripcio"`. Conserva l'identificador hash que genera Alembic, tant al nom del fitxer com a `revision`: no el reanomenis a una numeració seqüencial, perquè dues branques en paral·lel triarien el mateix número. `down_revision` és el `head` de la branca de què parteixes (`alembic heads`).
- Revisa el resultat: l'autogeneració pot convertir un canvi de nom en drop + create. Columnes `NOT NULL` sobre taules existents porten `server_default`. Les enumeracions de PostgreSQL es creen i s'esborren explícitament (model: `0006_add_opportunity_status.py`). `downgrade()` desfà exactament `upgrade()`.
- Un sol `head`. Quan en integrar dues branques amb migracions n'apareixen dos, resol-ho amb una única migració de merge (`alembic merge heads -m "Descripcio"`), sense tocar les migracions existents. Una migració ja fusionada a `dev` és immutable: els canvis van en una de nova. L'esquema el creen només les migracions, mai `Base.metadata.create_all()`.
- Una variable d'entorn nova s'afegeix alhora a `compose.yaml`, `compose.ci.yaml`, `compose.production.yaml` i `production.env.example`; avisa DevOps al PR.

### Tests

- `unittest`, un fitxer per recurs. Patró de `tests/test_auth.py`: cada classe crea la seva base de dades (`CREATE DATABASE` + `alembic upgrade head`), sobreescriu `get_db` amb `app.dependency_overrides` i l'esborra a `tearDownClass`. Per saltar l'autenticació, sobreescriu `get_current_user` com a `tests/test_opportunities.py`.
- `TestClient(app, base_url="https://testserver")` quan la prova depèn de la cookie de sessió, que és `Secure`.
- Cobreix el camí correcte, cada codi d'error i les regles de negoci (límits, estats, propietat). `test_route_protection.py` falla sol si una ruta nova queda sense protegir.

### Seed E2E

`seed_e2e_testing_data.py` omple una BD acabada de migrar amb les dades de què depenen els E2E de Playwright (`../frontend/e2e/`) i el desenvolupament local. El workflow E2E l'executa en les PR cap a `dev` dels dos repositoris (el del frontend agafa el backend de `dev`): un seed desfasat fa caure els E2E de tots dos encara que els tests unitaris passin. El seed és part del canvi i va al mateix PR.

Actualitza'l quan el canvi:

- afegeix un camp obligatori a un `*Create`, o una columna o taula que el frontend mostra;
- canvia quines dades són visibles o vàlides: estats, filtres del catàleg, dates límit, precondicions (com l'entitat promotora per crear oportunitats);
- obre una funcionalitat que els E2E recorren i que necessita dades prèvies (saldo, compromisos, detall d'un tipus d'oportunitat);
- reanomena o elimina camps, taules o valors d'enumeració que el seed envia o insereix.

Regles:

- Crea les dades per l'API quan hi ha endpoint, perquè passin per les mateixes validacions. SQL directe només per a dades sense endpoint, enllaçades per una clau natural i amb `ON CONFLICT DO NOTHING`.
- Cada camp del payload existeix al `*Create` de l'endpoint: Pydantic descarta en silenci els camps desconeguts i la dada no arriba a la BD.
- Dates relatives al moment d'execució (`datetime.now(UTC) + timedelta(...)`): una data fixa caduca i l'oportunitat surt del catàleg.
- Una dada que no es pot crear atura l'script amb error (`raise_for_status()` o excepció), perquè el CI falli al seed i no més tard a Playwright.
- Els fluxos de `../frontend/e2e/` busquen oportunitats per títol i compten els resultats del catàleg: llegeix-los abans d'afegir, treure o reanomenar dades. Si les seves expectatives han de canviar, obre una issue a `UB-ES-F4-2026/frontend` i enllaça-la al PR.

## Validació

Des de `backend`, amb Docker en marxa:

```bash
docker compose config --quiet
docker compose up --build --wait
docker compose exec backend alembic check
docker compose exec backend python -m unittest discover -s tests -v
```

Fet vol dir: tot verd, `alembic check` sense diferències i cada criteri de la issue amb el seu test o comprovació. Per no tocar l'entorn local, usa l'equivalent amb `-f compose.ci.yaml` de [CI.md](../CI.md).

Seed i E2E. Per defecte, executa'ls a l'entorn aïllat de `compose.e2e.yaml`: BD buida a cada execució, sense ports publicats ni res instal·lat a l'host, i sense tocar `fintech-local`. Agafa el frontend de `FRONTEND_PATH` (per defecte `../frontend`), així que els tests són els de la branca que hi tinguis:

```bash
docker compose -f compose.e2e.yaml run --rm --build playwright
docker compose -f compose.e2e.yaml down
```

L'ordre retorna el codi de sortida de Playwright i deixa l'informe a `e2e-report/playwright-report/index.html`, també si els tests fallen. Fes sempre el `down` en acabar: si l'entorn queda engegat, la següent execució reutilitza la BD amb les dades del seed anterior.

Només si cal provar-los sobre l'entorn de desenvolupament (`compose.yaml` engegat), el seed necessita `httpx` i `psycopg` al Python de l'host, i Playwright, Node i Chromium a l'host:

```bash
python seed_e2e_testing_data.py
# des de ../frontend
npm ci && npx playwright install chromium
PLAYWRIGHT_BASE_URL=http://127.0.0.1:<FRONTEND_PORT> npx playwright test --workers=1
```

Aquesta via escriu les dades del seed a la BD de desenvolupament de forma permanent, i el seed suposa una BD sense les seves dades: si l'usuari `inyector@fintech.com` ja existeix, tornar-lo a executar falla o duplica les oportunitats i trenca els recomptes dels E2E. Demana a l'usuari abans d'utilitzar-la. Les PR de tasca cap a `feat/US…` no disparen el workflow E2E, així que la prova local és l'única abans de la PR de `feat` a `dev`; en aquesta, el comentari `Resultados E2E de Playwright` ha d'estar tot verd.
