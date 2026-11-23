# Proves d'integració

Les proves d'integració comproven que diverses peces reals col·laboren. No
substitueixen les proves unitàries ni els E2E: validen els límits entre HTTP,
persistència, autenticació, navegació i servei API sense recórrer tot el
sistema en un navegador real.

## Backend

Una prova d'integració de backend usa FastAPI, Alembic i una base PostgreSQL
temporal. No se simula la base de dades. Els fitxers nous es diuen
`tests/test_*_integration.py`; durant la transició, els fitxers històrics que
creen una BD temporal també s'executen al job d'integració.

Per cada ruta nova o modificada, prova com a mínim:

1. El camí correcte i la forma exacta de la resposta.
2. Sense sessió (`401`) i, si hi ha propietat o rol, el recurs d'una altra
   persona (`403` o `404` segons el contracte).
3. Dades invàlides i els límits rellevants (`422`).
4. La persistència després de `commit` i l'absència d'efectes parcials quan
   falla una operació prevista (`409`, restricció o rollback).

Les migracions, la protecció global de rutes i les relacions/cascades de base
de dades són proves d'integració encara que no facin una petició HTTP.

Actualment, la suite històrica de rutes, sessions, oportunitats, promotors,
cartera i migracions s'executa com a integració. `test_name_search.py` i els
fitxers acabats en `_unit.py` es reserven explícitament per al job unitari fins
que els fitxers antics es vagin reanomenant de forma oportunista.

## Frontend

Una prova d'integració de frontend uneix pàgina o component, store, router i
`src/service/api.ts`. L'únic límit simulat és `fetch`: no s'arrenca el backend
ni es duplica Playwright. Els fitxers nous es diuen
`tests/*.integration.test.tsx` i s'executen amb `npm run test:integration`.

Per cada flux que consumeix API, prova el payload o consulta, càrrega, èxit,
error recuperable i la navegació o actualització d'estat observable. El test
ha d'usar el store i el servei reals; simular el store sencer converteix la
prova en unitària.

## Relació amb E2E i mètriques

- Les unitàries mesuren cobertura de línies i branques dels mòduls modificats.
- Les integracions es mesuren amb una matriu `ruta o flux -> autenticació ->
  error -> persistència o estat visible`, no amb un percentatge global de
  cobertura.
- Un E2E només es crea per un recorregut crític que travessa frontend,
  backend i PostgreSQL; no se'n crea un per endpoint.

En cada PR, unitàries i integració s'executen com a checks obligatoris. Els
E2E s'executen sobre els canvis integrats a `dev` o quan el flux transversal
canvia. Un test inestable s'ha de corregir o desactivar justificadament: no
s'allarga el timeout global per ocultar-lo.

## Abans d'obrir una PR

1. Relaciona cada criteri d'acceptació amb una prova unitària, d'integració o
   E2E.
2. Executa la suite d'integració del repositori afectat.
3. Si canvia un contracte entre repositoris, inclou la resposta real esperada
   i una prova del payload consumidor.
