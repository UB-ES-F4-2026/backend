# Proves funcionals

Les proves funcionals comproven els criteris d'acceptació de les històries
d'usuari al navegador, contra el frontend, el backend i PostgreSQL reals. Els
fluxos són al repositori `UB-ES-F4-2026/frontend` (`e2e/flows`), que també té
la guia per escriure'ls (`docs/qa/FUNCTIONAL_TESTING.md`) i la matriu
criteri → prova (`docs/qa/TRACEABILITY.md`).

Aquest repositori hi aporta l'entorn i les dades.

## Entorn

`compose.e2e.yaml` arrenca una base de dades buida, el backend, el frontend, el
seed i Playwright, sense ports publicats ni volums compartits amb
desenvolupament:

```bash
sh scripts/run-e2e.sh
```

L'informe queda a `e2e-report/playwright-report/index.html`. Els detalls són a
[CI.md](../../CI.md#tests-e2e).

## Dades

`seed_e2e_testing_data.py` deixa la base de dades en un estat conegut. Les
regles per mantenir-lo són a
[agents/backend.md](../../agents/backend.md#seed-e2e). Per a les proves
funcionals importen tres coses:

- Els comptes `capital.e2e`, `inversora.e2e`, `promotora.e2e` i
  `promotora.flujos.e2e` són de només lectura: els fluxos que escriuen
  registren el seu propi usuari.
- Cada oportunitat de `promotora.flujos.e2e` pertany a un sol flux.
- El seed acaba amb una autocomprovació (`verify_e2e_data`): si les dades no
  són les que esperen els fluxos, falla el seed i no Playwright.

## Saldo sense Stripe

L'entorn E2E no té claus de Stripe. El backend d'aquest entorn arrenca amb
`STRIPE_WEBHOOK_SECRET=whsec_e2e_only_not_a_real_secret`, un valor d'un sol ús
que no és cap secret real, i el seed i els fluxos ingressen saldo enviant a
`POST /api/webhooks/stripe` un pagament signat amb aquest valor. És la ruta de
producció: no hi ha cap endpoint ni canvi d'esquema només per a proves.

Aquest valor no s'ha d'afegir mai a `compose.production.yaml`,
`compose.staging.yaml`, `production.env.example` ni `.env.example`.

## Quan canvia el backend

Una PR que canvia un esquema `*Create`, un model, una migració o una regla de
visibilitat ha d'actualitzar el seed al mateix canvi i executar
`sh scripts/run-e2e.sh`. Un flux funcional que falla per dades absents és una
troballa de la PR del backend, encara que la prova sigui al frontend.
