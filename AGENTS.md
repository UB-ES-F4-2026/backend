# Instruccions per a agents — Backend Fintech

API FastAPI amb PostgreSQL 17 i Alembic. El frontend (React/Vite) viu al repositori germà `UB-ES-F4-2026/frontend`, clonat a `../frontend`. El `compose.yaml` d'aquest repositori arrenca tots dos: executa Docker Compose sempre des d'aquesta carpeta.

Llegeix [README.md](README.md) per a l'entorn local, migracions i tests, i [CI.md](CI.md) per reproduir la CI.

## Rols

Cada petició s'atén amb un rol. Tria'l per la feina que demana la tasca i llegeix el seu fitxer sencer abans de tocar res:

| Rol | Quan | Fitxer |
|---|---|---|
| Backend | Rutes, esquemes, models, migracions, lògica de negoci | [agents/backend.md](agents/backend.md) |
| QA | Verificar una issue o PR, escriure o revisar tests, reportar bugs | [agents/qa.md](agents/qa.md) |
| DevOps | CI, imatges, Compose de producció, desplegament, incidències al servidor | [agents/devops.md](agents/devops.md) |

El rol Frontend, i la part de QA i DevOps pròpia del frontend, són al `AGENTS.md` del repositori frontend.

Per invocar-ne un: «Actua com a QA. Verifica la PR #40 contra la issue #32». Si la petició no diu rol, dedueix-lo i digues quin apliques. Són perfils de comportament, no processos: no cal llançar subagents perquè existeixin.

## Regles comunes

- Documentació, issues, PRs i comentaris de codi en català. Respon en l'idioma en què t'escriuen.
- Les issues són a GitHub: `gh issue view <n> -R UB-ES-F4-2026/backend`. Una tasca comença llegint la seva issue i els criteris d'acceptació; el PR l'enllaça amb `Closes #n`. Una issue que afecta també el frontend es referencia amb el nom complet (`UB-ES-F4-2026/frontend#13`).
- Una branca per issue, `task/<n>-<descripció>`, amb PR cap a `main`. La CI de `.github/workflows/ci.yml` ha de passar abans de fusionar.
- `.env` conté credencials locals: conserva'l, no el mostris, no el pugis. Secrets, `.env*`, tokens i volcats de dades queden fora de qualsevol sortida.
- Els volums `postgres_data` i `pgadmin_data` guarden dades locals: `docker compose down` sense `-v`. Un error es resol llegint logs, mai esborrant volums, fent `prune` ni SQL destructiu.
- Abans d'`amend` o `rebase`, comprova branca i `HEAD` (`git branch --show-current`, `git log -1`): poden haver canviat des de l'última ordre.
- Commits i PRs sense atribució d'IA: cap `Co-Authored-By` d'assistent ni línia «Generated with …». Han de semblar escrits només per l'autor humà.
- Tanca cada tasca amb: què has canviat, com ho has comprovat (ordres i resultat) i què queda pendent.
