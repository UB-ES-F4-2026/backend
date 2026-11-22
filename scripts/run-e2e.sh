#!/bin/sh
# Executa els E2E de Playwright a l'entorn aïllat de compose.e2e.yaml.
# Atura l'entorn abans i després de cada execució: la BD (tmpfs) comença
# sempre buida, també si una execució anterior es va interrompre.
# Retorna el codi de sortida de Playwright. Informe: e2e-report/playwright-report/index.html
# COMPOSE permet canviar l'eina (per defecte "docker compose").
set -u
cd "$(dirname "$0")/.."

compose() {
    ${COMPOSE:-docker compose} -f compose.e2e.yaml "$@"
}

compose down --remove-orphans || exit 1
trap 'compose down --remove-orphans' EXIT
trap 'exit 130' INT TERM

# El build va a part: "run --build" no sempre reconstrueix les dependències
# (frontend, backend), i es provarien imatges antigues amb tests nous.
status=0
compose build && compose run --rm playwright || status=$?
echo "Informe: e2e-report/playwright-report/index.html"
exit "$status"
