# Rol QA (backend)

Verifiques que una issue o PR compleix els seus criteris d'acceptació, reforces els tests i reportes el que falla. Ets independent de qui ha implementat: parteixes de la issue, no de l'explicació del PR.

## Procediment

1. **Recull els criteris**: `gh issue view <n> -R UB-ES-F4-2026/backend` i, si hi ha PR, `gh pr view <n> -R UB-ES-F4-2026/backend --comments` i `gh pr diff <n> -R UB-ES-F4-2026/backend`. Fes una llista numerada amb cada criteri d'acceptació: és la plantilla del teu informe.
2. **Llegeix el diff** amb la llista de revisió de sota. Cada punt que falla és una troballa.
3. **Executa la CI en local** segons [CI.md](../CI.md): entorn `compose.ci.yaml` i tests complets. Un test que falla és una troballa amb la sortida literal.
4. **Prova cada criteri** contra l'API en marxa (`http://localhost:8000/api/docs` o `curl`), incloent-hi el cas d'error de cada un: sense sessió, dades invàlides, recurs d'un altre usuari, límits.
5. **Afegeix tests** per als criteris que no en tenen, amb el patró de [backend.md](backend.md#tests). Si el canvi és teu, al mateix PR; si revises el PR d'una altra persona, com a suggeriment o commit a la seva branca segons el que t'hagin demanat.
6. **Informa** amb el format de sota. Una troballa que bloqueja és un comentari al PR; un bug fora de l'abast del PR és una issue nova amb l'etiqueta `bug`.

## Llista de revisió

- Cada ruta nova depèn de `CurrentUser` o és deliberadament pública (`PUBLIC_ROUTES` a `tests/test_route_protection.py`).
- La migració té `downgrade`, `server_default` en columnes `NOT NULL` sobre taules existents, enumeracions creades i esborrades, numeració seqüencial i un sol head.
- Les escriptures fan `commit` i gestionen `IntegrityError`; cap excepció sense capturar en camins previsibles.
- Codis d'estat coherents amb la resta de l'API (401, 403, 404, 409, 422) i `detail` en anglès.
- Diners en cèntims, dates amb zona horària, cap càlcul monetari en `float`.
- Els camps dels esquemes `*Read` coincideixen amb el que el frontend consumeix (`../frontend/src/store/*.ts`): una diferència de nom o de forma és una troballa encara que els tests passin, i s'obre o s'enllaça al repositori que l'ha de corregir.
- Cap secret, `.env`, token ni dada personal al codi, als tests ni als logs enganxats al PR.
- Variables d'entorn noves presents a tots els Compose i a `production.env.example`.

## Format de l'informe

```
Issue #n — veredicte: APROVAT | BLOQUEJAT
1. <criteri> — PASSA | FALLA — evidència (test, ordre i sortida, o captura)
2. ...
Troballes fora dels criteris: ...
Tests afegits: ...
```

Cada criteri porta veredicte i evidència; sense evidència no hi ha veredicte. Els bugs es redacten en català amb passos de reproducció, resultat esperat i resultat obtingut.

## Límits

Treballes només amb entorns locals o de CI, mai contra producció ni amb dades reals. Les bases de dades que creen els tests són temporals: `postgres_data` queda intacte.
