# Proves unitàries

Les proves unitàries validen una regla o unitat de codi sense PostgreSQL, FastAPI,
Docker ni xarxa. S'executen a la CI amb cobertura de línies i branques.

## On posar-les

- Els fitxers nous es diuen `tests/test_*_unit.py`.
- Les funcions de domini reutilitzables viuen a `app/core/` i no reben una sessió
  SQLAlchemy ni objectes HTTP.
- Els validadors Pydantic es proven construint l'esquema directament.

## Què ha de provar una PR

Per cada regla nova o modificada, afegeix com a mínim:

1. Un cas vàlid representatiu.
2. Cada límit rellevant: mínim, màxim, buit i valor invàlid.
3. El resultat observable en cas d'error.

Els tokens, hashes i rellotges no s'han de comparar amb valors aleatoris o amb
l'hora exacta: comprova'n el format, la propietat de seguretat o un interval.

## Què no és una prova unitària

Una prova que crea una base de dades, aplica Alembic, obre un `TestClient` o
executa una consulta SQL és d'integració. Es manté a `tests/` i s'executa al job
d'integració; no s'ha de substituir per mocks.

## Abans d'obrir la PR

Executa la suite unitària del contenidor de CI i revisa l'informe de cobertura.
No s'accepta baixar la cobertura del mòdul modificat sense una justificació a la
PR. Quan aparegui una dependència nova entre unitats, afegeix una prova
d'integració a més de les unitàries.
