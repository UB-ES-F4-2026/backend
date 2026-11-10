# Rol Backend

Implementes canvis a l'API: rutes, esquemes, models, migracions i tests. Treballes dins de `app/` seguint els patrons existents; la lògica nova s'assembla a la que ja hi ha.

## Procediment

1. **Llegeix la issue** (`gh issue view <n> -R UB-ES-F4-2026/backend`). Extreu els criteris d'acceptació: cada un acabarà cobert per un test o per una comprovació descrita al PR. Si un criteri és ambigu, tria la interpretació més conservadora i deixa-la escrita al PR.
2. **Localitza el codi afectat** amb el mapa de sota i llegeix els mòduls que tocaràs i els tests que els cobreixen.
3. **Implementa** seguint les convencions. Un canvi d'esquema de dades porta model i migració al mateix commit.
4. **Escriu o amplia tests** a `tests/` per a cada criteri i per a cada codi d'error nou.
5. **Valida** amb les ordres de la secció final. Fins que no passa tot, la tasca no està feta.
6. **Entrega**: PR cap a `main` amb `Closes #n`, resum del contracte de l'API (rutes, camps, codis d'estat) perquè el frontend el pugui consumir, i les decisions preses sobre criteris ambigus.

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
| Migracions `000N_descripcio.py` | `alembic/versions/` |
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

- Genera-la amb la BD en marxa: `docker compose run --rm --build backend alembic revision --autogenerate -m "Descripcio"`. Reanomena el fitxer a `000N_descripcio.py` i posa `revision = "000N"`, `down_revision = "000(N-1)"`, seguint la numeració existent.
- Revisa el resultat: l'autogeneració pot convertir un canvi de nom en drop + create. Columnes `NOT NULL` sobre taules existents porten `server_default`. Les enumeracions de PostgreSQL es creen i s'esborren explícitament (model: `0006_add_opportunity_status.py`). `downgrade()` desfà exactament `upgrade()`.
- Un sol `head`. Una migració ja fusionada a `main` és immutable: els canvis van en una de nova. L'esquema el creen només les migracions, mai `Base.metadata.create_all()`.
- Una variable d'entorn nova s'afegeix alhora a `compose.yaml`, `compose.ci.yaml`, `compose.production.yaml` i `production.env.example`; avisa DevOps al PR.

### Tests

- `unittest`, un fitxer per recurs. Patró de `tests/test_auth.py`: cada classe crea la seva base de dades (`CREATE DATABASE` + `alembic upgrade head`), sobreescriu `get_db` amb `app.dependency_overrides` i l'esborra a `tearDownClass`. Per saltar l'autenticació, sobreescriu `get_current_user` com a `tests/test_opportunities.py`.
- `TestClient(app, base_url="https://testserver")` quan la prova depèn de la cookie de sessió, que és `Secure`.
- Cobreix el camí correcte, cada codi d'error i les regles de negoci (límits, estats, propietat). `test_route_protection.py` falla sol si una ruta nova queda sense protegir.

## Validació

Des de `backend`, amb Docker en marxa:

```bash
docker compose config --quiet
docker compose up --build --wait
docker compose exec backend alembic check
docker compose exec backend python -m unittest discover -s tests -v
```

Fet vol dir: tot verd, `alembic check` sense diferències i cada criteri de la issue amb el seu test o comprovació. Per no tocar l'entorn local, usa l'equivalent amb `-f compose.ci.yaml` de [CI.md](../CI.md).
