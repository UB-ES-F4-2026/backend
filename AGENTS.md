
# AGENTS.md

## Projecte i abast

Aquestes instruccions s'apliquen a tot el repositori `backend/`.

Grupo F4 és una plataforma d'inversió col·lectiva que permet descobrir, finançar i seguir oportunitats d'inversió, com ara immobles, negocis i startups.

- Mantén una arquitectura independent del tipus d'inversió. Prioritza conceptes genèrics com `opportunity`, `investment` i `funding`.
- Prioritza la seguretat, la integritat de les dades i les transaccions atòmiques en les operacions financeres.
- El backend utilitza FastAPI, SQLAlchemy 2.x, PostgreSQL 17 i Alembic.
- El frontend (React/Vite) es troba al repositori germà `../frontend`.
- `compose.yaml` coordina `backend`, `db`, `frontend` i `pgadmin`. Executa Docker Compose des de `backend/`.

Consulta [README.md](README.md) per a la configuració local i [CI.md](CI.md) per reproduir la CI.

## Rols

Selecciona el rol segons la tasca i llegeix el fitxer corresponent abans de modificar res.

| Rol | Responsabilitat | Instruccions |
|---|---|---|
| Backend | Rutes, esquemes, models, migracions i lògica de negoci | [agents/backend.md](agents/backend.md) |
| QA | Verificació d'issues i PRs, tests i detecció d'errors | [agents/qa.md](agents/qa.md) |
| DevOps | CI, imatges, desplegament i incidències del servidor | [agents/devops.md](agents/devops.md) |

Les instruccions de frontend es troben al seu propi `AGENTS.md`.

Si la petició no especifica un rol, dedueix-lo i comunica quin apliques. Els rols són perfils de comportament, no requereixen subagents.

## Convencions

- Identificadors de codi, variables, funcions, classes, taules i columnes en anglès.
- Documentació, issues, PRs, comentaris i docstrings en català.
- Respon a l'usuari en l'idioma en què escriu.
- No modifiquis textos existents que no estiguin relacionats amb la tasca.
- Utilitza Python 3.13 i sintaxi moderna de tipatge.
- Segueix les convencions existents del projecte i evita refactoritzacions innecessàries.

## Flux de treball

1. Comprova l'estat del repositori i preserva els canvis dels altres col·laboradors.
2. Llegeix la issue i els criteris d'acceptació abans de començar.
3. Examina primer els mòduls i tests directament relacionats amb la tasca.
4. Treballa en una branca `task/<n>-<descripció>` per issue.
5. Mantén els canvis petits i coherents amb l'arquitectura existent.
6. Afegeix o actualitza tests quan canviï el comportament observable.
7. Obre una PR cap a `main`, enllaçant la issue amb `Closes #n`.
8. Comprova que la CI passa abans de fusionar.

Les issues es consulten amb:

```bash
gh issue view <n> -R UB-ES-F4-2026/backend
```

Per referenciar issues del frontend, utilitza el nom complet del repositori, per exemple `UB-ES-F4-2026/frontend#13`.

Abans d'executar `amend` o `rebase`, comprova la branca i el commit actual:

```bash
git branch --show-current
git log -1
```

No afegeixis atribucions automàtiques d'assistents d'IA als commits o PRs.

## Arquitectura i convencions tècniques

- `app/api/routes/`: endpoints HTTP i dependències.
- `app/schemas/`: esquemes Pydantic d'entrada i sortida.
- `app/models/`: models SQLAlchemy.
- `app/database.py`: motor, `Base` i sessions.
- `app/start.py`: migracions i inicialització.
- `alembic/versions/`: historial de migracions.
- `tests/`: tests amb `unittest`.

Utilitza SQLAlchemy 2.x amb `select(Model)`, `db.scalars()`, `db.scalar()` i `db.get()`. Evita `db.query()`.

- Reutilitza `DbSession` i `CurrentUser`.
- Conserva `ConfigDict(from_attributes=True)` als esquemes de lectura.
- Valida les dades amb Pydantic.
- Confirma les escriptures amb `db.commit()` i gestiona errors esperats com `IntegrityError`.
- No afegeixis dependències noves sense aprovació de l'equip.
- No pressuposis que `pytest`, `black` o `ruff` estan disponibles.

L'autenticació utilitza tokens aleatoris, emmagatzemats com a hashes SHA-256 a `sessions`, i cookies `httpOnly`.

## Base de dades i migracions

- Gestiona els canvis d'esquema exclusivament amb Alembic.
- Inclou el model i la migració corresponent en el mateix canvi.
- No utilitzis `Base.metadata.create_all()` ni `alembic init`.
- No modifiquis migracions que altres desenvolupadors puguin haver aplicat.
- Revisa manualment les migracions autogenerades, especialment eliminacions i canvis de nom.
- Si apareixen diversos Alembic `heads`, coordina'n la integració.
- No modifiquis l'esquema manualment amb pgAdmin.

Després de modificar models:

```bash
docker compose run --rm --build backend alembic revision --autogenerate -m "Describe the change"
docker compose up --build --wait
docker compose exec backend alembic check
```

## Validació

Executa des de `backend/`:

```bash
docker compose config --quiet
docker compose up --build --wait
docker compose exec backend python -m unittest discover -s tests -v
docker compose exec backend alembic check
```

Per diagnosticar errors:

```bash
docker compose ps -a
docker compose logs --tail 60 backend db
```

## Seguretat i preservació de dades

- No mostris, modifiquis ni versionis `.env`, secrets, tokens o credencials.
- Preserva els volums `postgres_data` i `pgadmin_data`.
- Utilitza `docker compose down` sense `-v`.
- No executis `prune`, SQL destructiu ni eliminacions de volums per resoldre errors.
- Investiga primer els logs i coordina qualsevol operació destructiva amb l'equip.
- No incloguis secrets ni dades sensibles en informes d'errors.

## Definició de completat

Una tasca es considera completada quan:

- El comportament modificat està cobert per tests.
- La configuració de Compose és vàlida.
- Els tests passen, si l'entorn està disponible.
- `alembic check` no detecta canvis pendents, si s'han modificat models.
- Les migracions han estat revisades manualment.
- El diff no conté secrets, fitxers generats ni canvis aliens a la tasca.

Tanca cada tasca indicant què has modificat, com ho has verificat (ordres i resultats) i què queda pendent.

En informar d'errors, inclou l'ordre executada, el directori de treball i l'error rellevant, sense exposar credencials.
