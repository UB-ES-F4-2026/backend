#!/usr/bin/env python3
"""Seed de datos de demostración para la plataforma Fintech.

Combina las oportunidades inmobiliarias y de equity, crea el usuario y la
entidad promotora mediante la API e inserta por SQL los campos que no expone
el endpoint de creación de oportunidades.

Además del catálogo heredado (usuario `inyector` y sus 12 oportunidades), crea
el bloque determinista que usan los tests funcionales de Playwright: cuentas de
solo lectura, oportunidades en cada estado y compromisos reales hechos por la
API, de modo que `commitments`, `wallets` y `opportunities` quedan coherentes.

El saldo se ingresa por la ruta de producción `POST /api/webhooks/stripe`, con
un evento `payment_intent.succeeded` firmado con el secreto del entorno E2E.

El script supone una base de datos recién migrada y sin sus datos: una segunda
ejecución sobre la misma base se detiene con un error.
"""

import hashlib
import hmac
import json
import os
import struct
import time
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

try:  # psycopg 3 o psycopg2: la API utilizada es compatible en ambos casos
    import psycopg as pg
except ImportError:
    import psycopg2 as pg


OPPORTUNITIES_URL = "{API_BASE_URL}/api/opportunities"
REGISTER_URL = "{API_BASE_URL}/api/auth/register"
LOGIN_URL = "{API_BASE_URL}/api/auth/login"
SEED_EMAIL = "inyector@fintech.com"
SEED_PASSWORD = "inyector-fintech-2026"
SEED_IMAGE = b"\x89PNG\r\n\x1a\nseed-image"


def deadline_in(days: int) -> str:
    """Devuelve una fecha límite relativa a la ejecución del seed (UTC)."""
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def date_in(days: int) -> str:
    """Devuelve una fecha futura relativa al día de ejecución del seed."""
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


def opportunity_location(location: str) -> dict[str, str]:
    """Converteix la localització històrica del seed al contracte de l'API."""
    municipality, province = (component.strip() for component in location.split(",", 1))
    return {
        "municipality": municipality,
        "province": province,
        "country": "Espanya",
    }


# ---------------------------------------------------------------------------
# Datos de oportunidades
# Se conserva el catálogo ampliado de 12 oportunidades de la primera versión.
# Las fechas se calculan en tiempo de ejecución para evitar que caduquen por
# utilizar fechas fijas en un seed que se ejecute más adelante.
# ---------------------------------------------------------------------------

opportunities = [
    {
        "type": "real_estate",
        "title": "Rehabilitación de Edificio Histórico en L'Eixample",
        "description": "Proyecto de adquisición y reforma integral de una finca regia de 4 plantas. El inmueble se destinará al mercado de alquiler residencial de media estancia, con certificación energética A y alta rentabilidad asegurada.",
        "location": "L'Eixample, Barcelona",
        "cover_image_url": "https://becinadas.es/wp-content/uploads/2021/02/casa-ramos-plaza-lesseps-barcelona.jpg?w=750",
        "target_amount_cents": 150000000,
        "committed_cents": 2000000,
        "deadline": deadline_in(30),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "real_estate",
        "title": "Local Comercial Prime en el Barrio de Salamanca",
        "description": "Oportunidad de inversión en un local a pie de calle en una de las zonas comerciales más exclusivas. Actualmente alquilado a una reconocida marca de moda con contrato obligatorio a 10 años, ofreciendo rentas estables desde el primer mes.",
        "location": "Barrio de Salamanca, Madrid",
        "cover_image_url": "https://orozcoyasociados.es/wp-content/uploads/2026/08/gastos-comunidad-local-comercial-1024x683.jpg",
        "target_amount_cents": 85000000,
        "committed_cents": 1000000,
        "deadline": deadline_in(15),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "real_estate",
        "title": "Promoción de Viviendas Passivhaus",
        "description": "Financiación para la construcción de 10 viviendas unifamiliares con estándar Passivhaus (alta eficiencia energética). Licencia de obras ya concedida y fase de preventas completada al 40%.",
        "location": "Mairena del Aljarafe, Sevilla",
        "cover_image_url": "https://es.habcdn.com/photos/project/medium/conjunto-de-20-viviendas-unifamiliares-en-rosa-de-bara_192999.jpg",
        "target_amount_cents": 120000000,
        "committed_cents": 6000000,
        "deadline": deadline_in(60),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "real_estate",
        "title": "Apartamentos Turísticos en la Costa Blanca",
        "description": "Adquisición de un bloque de 6 apartamentos frente al mar para explotación turística mediante un operador profesional. Rendimiento neto estimado del 7.5% anual tras gastos de gestión e impuestos.",
        "location": "Calpe, Alicante",
        "cover_image_url": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQFwPGBb33NxFliAWiIGgrWyaivq6aKbKaOzPijc7r9teYKkKxk-IAnV9g&s=10",
        "target_amount_cents": 65000000,
        "committed_cents": 650000,
        "deadline": deadline_in(20),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "equity",
        "title": "Ronda Seed - EcoLogistics SL",
        "description": "Empresa de logística urbana de última milla con vehículos 100% eléctricos y software propio de optimización de rutas. Buscamos financiación para abrir operaciones en tres nuevas ciudades. Se ofrece un 10% del capital social.",
        "location": "Valencia, España",
        "cover_image_url": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRFepW0C2QB0nE3bjm3XewQUkyTItkjP7mz2M5pSryj0pRpCZ5_syMOxdo&s=10",
        "target_amount_cents": 40000000,
        "committed_cents": 8000,
        "deadline": deadline_in(45),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "equity",
        "title": "Ampliación de Capital - HealthAI Solutions",
        "description": "Startup del sector HealthTech que desarrolla algoritmos de inteligencia artificial para la detección temprana de anomalías médicas. Cuenta con certificación y pilotos activos en 5 hospitales. Oferta por el 15% del equity.",
        "location": "Sant Cugat del Vallès, Barcelona",
        "cover_image_url": "https://images.ctfassets.net/5z56gn2a2s8n/4zSVT4TZLVImyLvXvLu5HO/1844f0a714cb2606b43f0e99986cd937/AI-for-Healthcare---sized.jpg?fm=webp&q=75&w=1200",
        "target_amount_cents": 60000000,
        "committed_cents": 1000,
        "deadline": deadline_in(90),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "real_estate",
        "title": "Rehabilitación de Espai Mixt en L'Hospitalet",
        "description": "Rehabilitación de un edificio de uso mixto con espacios residenciales y comerciales. La propuesta incluye mejoras de accesibilidad y eficiencia energética.",
        "location": "L'Hospitalet de Llobregat, Barcelona",
        "cover_image_url": None,
        "target_amount_cents": 92000000,
        "committed_cents": 0,
        "deadline": deadline_in(75),
        "minimum_contribution_cents": 5000
    },
    {
        "type": "real_estate",
        "title": "Nave Industrial Sostenible en Zaragoza",
        "description": "Construcción de una nave industrial preparada para alquiler logístico, con instalaciones fotovoltaicas y acceso directo a vías principales.",
        "location": "La Cartuja Baja, Zaragoza",
        "cover_image_url": None,
        "target_amount_cents": 73500000,
        "committed_cents": 12500000,
        "deadline": deadline_in(105),
        "minimum_contribution_cents": 25000
    },
    {
        "type": "real_estate",
        "title": "Urbanización de Parcela Urbana en Girona",
        "description": "Proyecto de urbanización de una parcela para su posterior comercialización. La inversión contempla las obras previstas y los gastos de gestión.",
        "location": "Girona, Catalunya",
        "cover_image_url": None,
        "target_amount_cents": 18000000,
        "committed_cents": 4500000,
        "deadline": deadline_in(35),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "real_estate",
        "title": "Locales Comerciales Rehabilitados en Bilbao",
        "description": "Adquisición y rehabilitación de locales en planta baja para uso comercial. El plan incluye renovación de instalaciones y mejora de fachadas.",
        "location": "Bilbao, Bizkaia",
        "cover_image_url": None,
        "target_amount_cents": 51000000,
        "committed_cents": 50900000,
        "deadline": deadline_in(12),
        "minimum_contribution_cents": 50000
    },
    {
        "type": "real_estate",
        "title": "Residencial de Alquiler en Tarragona",
        "description": "Adquisición de un edificio residencial para alquiler de larga duración. La planificación incluye la actualización de zonas comunes y servicios.",
        "location": "Tarragona, Catalunya",
        "cover_image_url": None,
        "target_amount_cents": 44000000,
        "committed_cents": 21000000,
        "deadline": deadline_in(55),
        "minimum_contribution_cents": 10000
    },
    {
        "type": "real_estate",
        "title": "Vivienda de Obra Nueva para Uso Propio",
        "description": "Construcción de una vivienda unifamiliar con espacios adaptables y soluciones de bajo consumo energético.",
        "location": "Pamplona, Navarra",
        "cover_image_url": None,
        "target_amount_cents": 26500000,
        "committed_cents": 3250000,
        "deadline": deadline_in(80),
        "minimum_contribution_cents": 10000
    }
]

promoting_entity = {
    "legal_name": "Inmobiliaria Completamente Benevolente S.A.",
    "image_url": "https://media.licdn.com/dms/image/v2/D4E12AQGEkrAsxY1QhQ/article-cover_image-shrink_600_2000/article-cover_image-shrink_600_2000/0/1672160148298?e=2147483647&v=beta&t=2tButp2hDwHJwlq_BnGQ2FaEga6yJsHbCqRm8OW6ZSQ",
    "experience_years": 10,
    "founding_year": 2012,
    "location": "Madrid, España"
}

# ---------------------------------------------------------------------------
# Metadatos específicos que no admite OpportunityCreate.
# Los datos inmobiliarios proceden de la primera versión y los empresariales
# de la segunda. Se insertan/actualizan por SQL después de crear las
# oportunidades mediante la API.
# ---------------------------------------------------------------------------

real_estate_details = {
    "Rehabilitación de Edificio Histórico en L'Eixample": {
        "purpose": "acquisition_and_renovation",
        "intended_use": "rental",
        "asset_type": "residential",
        "surface_m2": "780.00",
        "planned_housing_units": 8,
        "estimated_works_end": date_in(225),
        "estimated_rental_start": date_in(285),
        "public_latitude": "41.391000",
        "public_longitude": "2.165000",
    },
    "Local Comercial Prime en el Barrio de Salamanca": {
        "purpose": "acquisition",
        "intended_use": "rental",
        "asset_type": "commercial",
        "surface_m2": "210.00",
        "planned_housing_units": None,
        "estimated_works_end": None,
        "estimated_rental_start": None,
        "public_latitude": "40.429000",
        "public_longitude": "-3.684000",
    },
    "Promoción de Viviendas Passivhaus": {
        "purpose": "construction",
        "intended_use": "sale",
        "asset_type": "residential",
        "surface_m2": "1450.00",
        "planned_housing_units": 10,
        "estimated_works_end": date_in(390),
        "estimated_rental_start": None,
        "public_latitude": "37.344000",
        "public_longitude": "-6.062000",
    },
    "Apartamentos Turísticos en la Costa Blanca": {
        "purpose": "acquisition",
        "intended_use": "rental",
        "asset_type": "residential",
        "surface_m2": "410.00",
        "planned_housing_units": 6,
        "estimated_works_end": None,
        "estimated_rental_start": date_in(100),
        "public_latitude": "38.643000",
        "public_longitude": "0.060000",
    },
    "Rehabilitación de Espai Mixt en L'Hospitalet": {
        "purpose": "renovation",
        "intended_use": "own_use",
        "asset_type": "mixed",
        "surface_m2": "620.00",
        "planned_housing_units": 3,
        "estimated_works_end": date_in(310),
        "estimated_rental_start": None,
        "public_latitude": None,
        "public_longitude": None,
    },
    "Nave Industrial Sostenible en Zaragoza": {
        "purpose": "construction",
        "intended_use": "rental",
        "asset_type": "industrial",
        "surface_m2": "2850.00",
        "planned_housing_units": None,
        "estimated_works_end": date_in(420),
        "estimated_rental_start": date_in(480),
        "public_latitude": "41.635000",
        "public_longitude": "-0.850000",
    },
    "Urbanización de Parcela Urbana en Girona": {
        "purpose": "construction",
        "intended_use": "sale",
        "asset_type": "land",
        "surface_m2": "345.75",
        "planned_housing_units": None,
        "estimated_works_end": date_in(190),
        "estimated_rental_start": None,
        "public_latitude": None,
        "public_longitude": None,
    },
    "Locales Comerciales Rehabilitados en Bilbao": {
        "purpose": "acquisition_and_renovation",
        "intended_use": "own_use",
        "asset_type": "commercial",
        "surface_m2": "128.40",
        "planned_housing_units": None,
        "estimated_works_end": date_in(160),
        "estimated_rental_start": None,
        "public_latitude": "43.263000",
        "public_longitude": "-2.935000",
    },
    "Residencial de Alquiler en Tarragona": {
        "purpose": "acquisition",
        "intended_use": "rental",
        "asset_type": "mixed",
        "surface_m2": "980.00",
        "planned_housing_units": 14,
        "estimated_works_end": None,
        "estimated_rental_start": date_in(75),
        "public_latitude": "41.118000",
        "public_longitude": "1.245000",
    },
    "Vivienda de Obra Nueva para Uso Propio": {
        "purpose": "construction",
        "intended_use": "own_use",
        "asset_type": "residential",
        "surface_m2": "156.25",
        "planned_housing_units": 1,
        "estimated_works_end": date_in(350),
        "estimated_rental_start": None,
        "public_latitude": None,
        "public_longitude": None,
    },
}

business_details = {
    "Ronda Seed - EcoLogistics SL": {
        "sector": "other_services",
        "phase": "launch",
        "pre_investment_valuation_cents": 360000000,
    },
    "Ampliación de Capital - HealthAI Solutions": {
        "sector": "health",
        "phase": "growth",
        "pre_investment_valuation_cents": 340000000,
    },
}

UPDATE_OPPORTUNITY_FOR_CATALOG_SQL = """
    UPDATE public.opportunities
    SET minimum_contribution_cents = %(minimum_contribution_cents)s,
        committed_cents = %(committed_cents)s,
        status = 'published',
        date_published = COALESCE(date_published, CURRENT_TIMESTAMP)
    WHERE title = %(title)s AND type = %(type)s
"""

INSERT_REAL_ESTATE_SQL = """
    INSERT INTO public.real_estate_opportunities (
        opportunity_id, purpose, intended_use, asset_type, surface_m2,
        planned_housing_units, estimated_works_end, estimated_rental_start,
        public_latitude, public_longitude
    )
    SELECT
        o.id,
        %(purpose)s::real_estate_purpose,
        %(intended_use)s::real_estate_intended_use,
        %(asset_type)s::real_estate_asset_type,
        %(surface_m2)s::numeric,
        %(planned_housing_units)s::integer,
        %(estimated_works_end)s::date,
        %(estimated_rental_start)s::date,
        %(public_latitude)s::numeric,
        %(public_longitude)s::numeric
    FROM public.opportunities o
    WHERE o.title = %(title)s AND o.type = 'real_estate'
    ON CONFLICT (opportunity_id) DO UPDATE SET
        purpose = EXCLUDED.purpose,
        intended_use = EXCLUDED.intended_use,
        asset_type = EXCLUDED.asset_type,
        surface_m2 = EXCLUDED.surface_m2,
        planned_housing_units = EXCLUDED.planned_housing_units,
        estimated_works_end = EXCLUDED.estimated_works_end,
        estimated_rental_start = EXCLUDED.estimated_rental_start,
        public_latitude = EXCLUDED.public_latitude,
        public_longitude = EXCLUDED.public_longitude
    RETURNING opportunity_id
"""

# ---------------------------------------------------------------------------
# Bloque determinista para los tests funcionales (Playwright)
#
# Reglas de uso, compartidas con frontend/e2e/support/seed.ts:
# - Las cuentas de este bloque son de SOLO LECTURA: ningún flujo escribe con
#   ellas. Un flujo que modifica datos registra su propio usuario y le ingresa
#   el saldo que necesita.
# - La cartera de `promotora.e2e` (P1-P8) no recibe compromisos de ningún flujo:
#   sus importes y recuentos son fijos.
# - Las oportunidades de `promotora.flujos.e2e` (F1-F8) son las únicas en las
#   que los flujos comprometen saldo, y cada una pertenece a un solo flujo.
# - Las gemelas «casi financiadas» se eligen en tiempo de ejecución: hay tres
#   de cada tipo, una por intento (1 ejecución + 2 reintentos de la CI).
# ---------------------------------------------------------------------------

E2E_PASSWORD = "Password123!"
E2E_PHONE = "+34612345678"
# Secreto de usar y tirar del entorno E2E; nunca el de staging o producción.
E2E_WEBHOOK_SECRET = "whsec_e2e_only_not_a_real_secret"

CAPITAL_EMAIL = "capital.e2e@fintech.com"
INVESTOR_EMAIL = "inversora.e2e@fintech.com"
PORTFOLIO_PROMOTER_EMAIL = "promotora.e2e@fintech.com"
FLOWS_PROMOTER_EMAIL = "promotora.flujos.e2e@fintech.com"

# `promoting_entity` va en el registro; `entity` se crea después por
# POST /api/promotingentity, que admite además los años de experiencia.
e2e_accounts = [
    {
        "email": CAPITAL_EMAIL,
        "first_name": "Capital",
        "last_name": "Semilla",
        "deposit_cents": 93_630_000,
    },
    {
        "email": INVESTOR_EMAIL,
        "first_name": "Inés",
        "last_name": "Cartera-Núñez",
        "deposit_cents": 318_456,
    },
    {
        "email": PORTFOLIO_PROMOTER_EMAIL,
        "first_name": "Pau",
        "last_name": "Promotor d'Àger",
        "deposit_cents": 800_000,
        "entity": {
            "legal_name": "Promotora Determinista E2E S.L.",
            "image_url": None,
            "experience_years": 7,
            "founding_year": 2015,
            "location": "Girona, España",
        },
    },
    {
        "email": FLOWS_PROMOTER_EMAIL,
        "first_name": "Flor",
        "last_name": None,
        "deposit_cents": 0,
        "promoting_entity": {"legal_name": "Promotora de Flujos E2E S.L."},
    },
]


def e2e_location(municipality: str, province: str) -> dict[str, str]:
    return {"municipality": municipality, "province": province, "country": "España"}


def near_funded_twins(
    title: str, description: str, location: dict[str, str], target_cents: int, specific: dict
) -> list[dict]:
    """Tres oportunidades idénticas a 500,00 € del objetivo, una por intento."""
    return [
        {
            "owner": FLOWS_PROMOTER_EMAIL,
            "title": f"{title} {number}",
            "description": description,
            "location": location,
            "target_amount_cents": target_cents,
            # Mayor que lo pendiente: solo se puede aportar el resto (500,00 €).
            "minimum_contribution_cents": 100_000,
            "deadline": deadline_in(25),
            "published_days_ago": 1,
            **specific,
        }
        for number in (1, 2, 3)
    ]


# `published_days_ago`: None deja la oportunidad pendiente de revisión.
# `final_state`: cambio por SQL posterior a los compromisos (sin endpoint).
e2e_opportunities = [
    # --- Cartera de solo lectura (promotora.e2e) ---------------------------
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "real_estate",
        "title": "Piso en Girona",
        "description": "Compra de un piso de dos habitaciones en el Barri Vell para alquiler de larga duración.\nIncluye la puesta a punto de la cocina y de las instalaciones.",
        "location": e2e_location("Girona", "Girona"),
        "target_amount_cents": 12_000_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(50),
        "published_days_ago": 3,
        "real_estate": {
            "purpose": "acquisition",
            "intended_use": "rental",
            "asset_type": "residential",
            "surface_m2": "85.50",
            "planned_housing_units": 1,
            "estimated_works_end": None,
            "estimated_rental_start": date_in(120),
            "public_latitude": "41.983000",
            "public_longitude": "2.824000",
        },
    },
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "real_estate",
        "title": "Parcela Rústica Cadí",
        "description": "Urbanización de una parcela al pie de la sierra del Cadí para su venta posterior.",
        "location": e2e_location("Bellver de Cerdanya", "Lleida"),
        "target_amount_cents": 8_000_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(70),
        "published_days_ago": 5,
        "real_estate": {
            "purpose": "construction",
            "intended_use": "sale",
            "asset_type": "land",
            "surface_m2": "2400.00",
            "planned_housing_units": None,
            "estimated_works_end": date_in(200),
            "estimated_rental_start": None,
            "public_latitude": None,
            "public_longitude": None,
        },
    },
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "equity",
        "title": "Cervecera artesana en Girona",
        "description": "Microcervecera con obrador propio y distribución en Cataluña. La ronda financia una segunda línea de envasado.",
        "location": e2e_location("Salt", "Girona"),
        "target_amount_cents": 30_000_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(65),
        "published_days_ago": 10,
        "business": {
            "sector": "food_and_beverage",
            "phase": "growth",
            "pre_investment_valuation_cents": 270_000_000,
        },
    },
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "real_estate",
        "title": "Nave Logística Objetivo Cumplido",
        "description": "Nave logística de última milla junto a la AP-7. Financiación completada.",
        "location": e2e_location("Vilamalla", "Girona"),
        "target_amount_cents": 2_000_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(45),
        "published_days_ago": 20,
        "real_estate": {
            "purpose": "construction",
            "intended_use": "rental",
            "asset_type": "industrial",
            "surface_m2": "1200.00",
            "planned_housing_units": None,
            "estimated_works_end": date_in(260),
            "estimated_rental_start": date_in(300),
            "public_latitude": "42.217000",
            "public_longitude": "2.970000",
        },
    },
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "real_estate",
        "title": "Hostal Rural Plazo Vencido",
        "description": "Rehabilitación de un hostal rural de ocho habitaciones. El plazo terminó sin alcanzar el objetivo.",
        "location": e2e_location("Àger", "Lleida"),
        "target_amount_cents": 4_000_000,
        "minimum_contribution_cents": 10_000,
        # La API rechaza fechas pasadas: se crea vigente y se vence por SQL.
        "deadline": deadline_in(1),
        "published_days_ago": 30,
        "final_state": "expired",
        "real_estate": {
            "purpose": "acquisition_and_renovation",
            "intended_use": "own_use",
            "asset_type": "commercial",
            "surface_m2": "640.25",
            "planned_housing_units": None,
            "estimated_works_end": date_in(150),
            "estimated_rental_start": None,
            "public_latitude": "42.000000",
            "public_longitude": "0.763000",
        },
    },
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "equity",
        "title": "Coworking Pendiente de Revisión",
        "description": "Espacio de trabajo compartido en un antiguo taller. Todavía es una idea: busca capital para la reforma.",
        "location": e2e_location("Figueres", "Girona"),
        "target_amount_cents": 6_000_000,
        "minimum_contribution_cents": 100_000,
        "deadline": deadline_in(90),
        "initial_contribution_cents": 500_000,
        "published_days_ago": None,
        "business": {
            "sector": "other_services",
            "phase": "idea",
            "pre_investment_valuation_cents": 54_000_000,
        },
    },
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "equity",
        "title": "Obrador Cierre Anticipado",
        "description": "Obrador de pan con tres tiendas propias. La entidad cerró la ronda antes de tiempo.",
        "location": e2e_location("Olot", "Girona"),
        "target_amount_cents": 10_000_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(40),
        "published_days_ago": 40,
        "final_state": "closed",
        "business": {
            "sector": "commerce",
            "phase": "consolidated",
            "pre_investment_valuation_cents": 90_000_000,
        },
    },
    {
        "owner": PORTFOLIO_PROMOTER_EMAIL,
        "type": "real_estate",
        "title": "Proyecto Rechazado No Visible",
        "description": "Proyecto rechazado en la revisión: no debe aparecer en ninguna lista.",
        "location": e2e_location("Ripoll", "Girona"),
        "target_amount_cents": 3_000_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(30),
        "published_days_ago": None,
        "final_state": "rejected",
        "real_estate": {
            "purpose": "construction",
            "intended_use": "sale",
            "asset_type": "land",
            "surface_m2": "900.00",
            "planned_housing_units": None,
            "estimated_works_end": None,
            "estimated_rental_start": None,
            "public_latitude": None,
            "public_longitude": None,
        },
    },
    # --- Oportunidades en las que escriben los flujos (promotora.flujos.e2e) -
    {
        "owner": FLOWS_PROMOTER_EMAIL,
        "type": "real_estate",
        "title": "Residencial Riera Alta",
        "description": "Rehabilitación de un edificio de doce viviendas para alquiler asequible.",
        "location": e2e_location("Mataró", "Barcelona"),
        "target_amount_cents": 7_200_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(40),
        "published_days_ago": 2,
        "real_estate": {
            "purpose": "acquisition_and_renovation",
            "intended_use": "rental",
            "asset_type": "residential",
            "surface_m2": "940.00",
            "planned_housing_units": 12,
            "estimated_works_end": date_in(240),
            "estimated_rental_start": date_in(270),
            "public_latitude": "41.540000",
            "public_longitude": "2.444000",
        },
    },
    {
        "owner": FLOWS_PROMOTER_EMAIL,
        "type": "equity",
        "title": "Movilidad Eléctrica Garraf",
        "description": "Red de recarga para flotas de reparto. Ronda de lanzamiento para desplegar los primeros 40 puntos.",
        "location": e2e_location("Vilanova i la Geltrú", "Barcelona"),
        "target_amount_cents": 30_000_000,
        "minimum_contribution_cents": 10_000,
        "deadline": deadline_in(60),
        "published_days_ago": 2,
        "business": {
            "sector": "technology",
            "phase": "launch",
            "pre_investment_valuation_cents": 270_000_000,
        },
    },
    *near_funded_twins(
        "Ático Último Tramo",
        "Reforma de un ático para alquiler. Solo faltan 500,00 € para completar la financiación.",
        e2e_location("Sitges", "Barcelona"),
        5_000_000,
        {
            "type": "real_estate",
            "real_estate": {
                "purpose": "renovation",
                "intended_use": "rental",
                "asset_type": "residential",
                "surface_m2": "110.00",
                "planned_housing_units": 1,
                "estimated_works_end": date_in(90),
                "estimated_rental_start": date_in(120),
                "public_latitude": "41.237000",
                "public_longitude": "1.805000",
            },
        },
    ),
    *near_funded_twins(
        "Biotech Ronda Final",
        "Spin-off de diagnóstico rápido. Solo faltan 500,00 € para cerrar la ronda.",
        e2e_location("Cerdanyola del Vallès", "Barcelona"),
        10_000_000,
        {
            "type": "equity",
            "business": {
                "sector": "health",
                "phase": "growth",
                "pre_investment_valuation_cents": 90_000_000,
            },
        },
    ),
]

# Compromisos reales, en orden: primero el inversor de fondos y después la
# inversora de solo lectura, cuyo orden define su lista de «Mis inversiones».
e2e_commitments = [
    (CAPITAL_EMAIL, "Piso en Girona", 2_980_000),
    (CAPITAL_EMAIL, "Cervecera artesana en Girona", 18_350_000),
    (CAPITAL_EMAIL, "Nave Logística Objetivo Cumplido", 1_950_000),
    (CAPITAL_EMAIL, "Hostal Rural Plazo Vencido", 1_500_000),
    (CAPITAL_EMAIL, "Obrador Cierre Anticipado", 1_200_000),
    (CAPITAL_EMAIL, "Residencial Riera Alta", 4_500_000),
    (CAPITAL_EMAIL, "Movilidad Eléctrica Garraf", 18_450_000),
    *((CAPITAL_EMAIL, f"Ático Último Tramo {number}", 4_950_000) for number in (1, 2, 3)),
    *((CAPITAL_EMAIL, f"Biotech Ronda Final {number}", 9_950_000) for number in (1, 2, 3)),
    (INVESTOR_EMAIL, "Piso en Girona", 10_000),
    (INVESTOR_EMAIL, "Cervecera artesana en Girona", 100_000),
    (INVESTOR_EMAIL, "Nave Logística Objetivo Cumplido", 50_000),
    (INVESTOR_EMAIL, "Hostal Rural Plazo Vencido", 25_000),
    (INVESTOR_EMAIL, "Piso en Girona", 10_000),
]

# Estado que debe quedar tras el seed; `verify_e2e_data` lo comprueba por la API.
E2E_EXPECTED_WALLETS = {
    CAPITAL_EMAIL: (0, 93_630_000),
    INVESTOR_EMAIL: (123_456, 195_000),
    PORTFOLIO_PROMOTER_EMAIL: (300_000, 500_000),
    FLOWS_PROMOTER_EMAIL: (0, 0),
}
E2E_EXPECTED_PORTFOLIO_SUMMARY = {
    "committed_cents": 26_175_000,
    "published_count": 6,
    "in_funding_count": 3,
    "pending_review_count": 1,
}
E2E_EXPECTED_INVESTMENTS_SUMMARY = {
    "total_committed_cents": 195_000,
    "commitments_count": 5,
    "in_funding_count": 3,
}
E2E_EXPECTED_COMMITTED = {
    "Piso en Girona": 3_000_000,
    "Parcela Rústica Cadí": 0,
    "Cervecera artesana en Girona": 18_450_000,
    "Residencial Riera Alta": 4_500_000,
    "Movilidad Eléctrica Garraf": 18_450_000,
    **{f"Ático Último Tramo {number}": 4_950_000 for number in (1, 2, 3)},
    **{f"Biotech Ronda Final {number}": 9_950_000 for number in (1, 2, 3)},
}
E2E_HIDDEN_FROM_CATALOG = (
    "Nave Logística Objetivo Cumplido",
    "Hostal Rural Plazo Vencido",
    "Coworking Pendiente de Revisión",
    "Obrador Cierre Anticipado",
    "Proyecto Rechazado No Visible",
)

# La publicación, el vencimiento, el cierre y el rechazo no tienen endpoint.
# Clave natural: título, tipo y correo de la entidad propietaria. La condición
# sobre `status` evita reescribir una oportunidad que ya haya cambiado de estado.
E2E_PUBLISH_SQL = """
    UPDATE public.opportunities AS o
    SET status = 'published', date_published = %(published_at)s
    FROM public.users AS u
    WHERE o.user_id = u.id AND u.email = %(owner)s
      AND o.title = %(title)s AND o.type = %(type)s AND o.status = 'draft'
"""

E2E_FINAL_STATE_SQL = {
    "expired": """
        UPDATE public.opportunities AS o
        SET deadline = %(moment)s
        FROM public.users AS u
        WHERE o.user_id = u.id AND u.email = %(owner)s
          AND o.title = %(title)s AND o.type = %(type)s AND o.status = 'published'
    """,
    "closed": """
        UPDATE public.opportunities AS o
        SET status = 'closed', date_closed = %(moment)s
        FROM public.users AS u
        WHERE o.user_id = u.id AND u.email = %(owner)s
          AND o.title = %(title)s AND o.type = %(type)s AND o.status = 'published'
    """,
    "rejected": """
        UPDATE public.opportunities AS o
        SET status = 'rejected'
        FROM public.users AS u
        WHERE o.user_id = u.id AND u.email = %(owner)s
          AND o.title = %(title)s AND o.type = %(type)s AND o.status = 'draft'
    """,
}


def tiny_png() -> bytes:
    """PNG válido de 1x1 píxel: la galería del detalle puede decodificarlo."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixel = zlib.compress(b"\x00\xf5\xa5\x24")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixel) + chunk(b"IEND", b"")


E2E_IMAGE = tiny_png()


def load_env() -> dict[str, str]:
    """Lee el .env del backend; las variables de entorno tienen prioridad."""
    here = Path(__file__).resolve().parent
    values: dict[str, str] = {}
    candidates = (
        here / "backend" / ".env",
        here / ".env",
        here.parent / ".env",
        Path.cwd() / ".env",
    )

    for candidate in candidates:
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip("\"'")
        break

    environment_values = {
        key: value
        for key, value in os.environ.items()
        if key.startswith("POSTGRES_")
        or key in {"BACKEND_PORT", "STRIPE_WEBHOOK_SECRET"}
    }
    return {**values, **environment_values}


def get_backend_port() -> int:
    """Obtiene y valida el puerto del backend publicado por Docker Compose."""
    raw = load_env().get("BACKEND_PORT")
    if raw is None:
        raise RuntimeError("Falta BACKEND_PORT en el .env")
    try:
        port = int(raw)
    except ValueError:
        raise RuntimeError(f"BACKEND_PORT no es un número válido: {raw!r}") from None
    if not 0 < port <= 65535:
        raise RuntimeError(f"BACKEND_PORT fuera de rango (1-65535): {port}")
    return port


def get_database_connection():
    """Abre una conexión a PostgreSQL usando la configuración del .env."""
    env = load_env()
    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise RuntimeError(f"Faltan variables en el .env: {', '.join(missing)}")

    try:
        db_port = int(env["POSTGRES_PORT"])
    except ValueError:
        raise RuntimeError("POSTGRES_PORT no es un número válido") from None
    if not 0 < db_port <= 65535:
        raise RuntimeError(f"POSTGRES_PORT fuera de rango (1-65535): {db_port}")

    return pg.connect(
        host=env.get("POSTGRES_HOST", "127.0.0.1"),  # Compose publica PostgreSQL únicamente en localhost
        port=db_port,
        dbname=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )



def inject_sql_only_data() -> None:
    """Completa per SQL les dades del catàleg que l'API encara no exposa.

    Todas las operaciones SQL se ejecutan en una única transacción. Los
    metadatos especializados utilizan UPSERT, por lo que repetir el seed
    actualiza los valores existentes en lugar de dejarlos desfasados.
    """
    connection = get_database_connection()
    try:
        with connection.cursor() as cursor:
            # El seed necessita oportunitats públiques perquè el catàleg E2E
            # les pugui consultar. La publicació encara no té endpoint.
            for opportunity in opportunities:
                cursor.execute(
                    UPDATE_OPPORTUNITY_FOR_CATALOG_SQL,
                    {
                        "title": opportunity["title"],
                        "type": opportunity["type"],
                        "minimum_contribution_cents": opportunity[
                            "minimum_contribution_cents"
                        ],
                        "committed_cents": opportunity["committed_cents"],
                    },
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "No se pudo actualizar la aportación mínima de "
                        f"{opportunity['title']}: se encontraron "
                        f"{cursor.rowcount} filas (se esperaba exactamente 1)"
                    )
                print(f"✅ Oportunidad publicada: {opportunity['title']}")

            for title, details in real_estate_details.items():
                cursor.execute(INSERT_REAL_ESTATE_SQL, {"title": title, **details})
                if cursor.fetchone() is None:
                    raise RuntimeError(
                        "No se encontraron los datos de la oportunidad inmobiliaria "
                        f"'{title}'. Comprueba que se haya creado mediante la API."
                    )
                print(f"✅ Datos inmobiliarios insertados/actualizados: {title}")

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_webhook_secret() -> str:
    """Secreto con el que el backend verifica el webhook de Stripe en este entorno."""
    return load_env().get("STRIPE_WEBHOOK_SECRET") or E2E_WEBHOOK_SECRET


def fail_unless(response: httpx.Response, expected_status: int, action: str) -> None:
    """Detiene el seed con la respuesta del backend si la petición no ha ido bien."""
    if response.status_code != expected_status:
        raise RuntimeError(
            f"❌ {action}: se esperaba {expected_status} y el backend respondió "
            f"{response.status_code} - {response.text}"
        )


def register_e2e_account(client: httpx.Client, backend_url: str, account: dict) -> int:
    """Registra una cuenta del bloque E2E y devuelve su id."""
    payload = {
        "email": account["email"],
        "password": E2E_PASSWORD,
        "first_name": account["first_name"],
        "last_name": account["last_name"],
        "phone": E2E_PHONE,
    }
    if "promoting_entity" in account:
        payload["promoting_entity"] = account["promoting_entity"]
    response = client.post(REGISTER_URL.format(API_BASE_URL=backend_url), json=payload)
    if response.status_code == 409:
        raise RuntimeError(
            f"❌ La cuenta {account['email']} ya existe: el seed ya se ejecutó sobre esta "
            "base de datos. Ejecútalo sobre una base recién migrada."
        )
    fail_unless(response, 201, f"Registrar {account['email']}")
    print(f"✅ Usuario creado: {account['email']}")
    return response.json()["id"]


def login_headers(client: httpx.Client, backend_url: str, email: str, password: str) -> dict[str, str]:
    """Inicia sesión y devuelve la cabecera con la cookie de esa cuenta."""
    response = client.post(
        LOGIN_URL.format(API_BASE_URL=backend_url),
        json={"email": email, "password": password},
    )
    fail_unless(response, 200, f"Iniciar sesión como {email}")
    session_token = response.cookies.get("session")
    if not session_token:
        raise RuntimeError(f"El login de {email} no devolvió la cookie de sesión")
    # La cookie es `Secure` y el seed usa HTTP: se envía a mano en cada petición
    # y se vacía el almacén para no mezclar sesiones de cuentas distintas.
    client.cookies.clear()
    return {"Cookie": f"session={session_token}"}


def credit_wallet(
    client: httpx.Client, backend_url: str, *, user_id: int, amount_cents: int, reference: str
) -> None:
    """Ingresa saldo como lo hace Stripe: con un pago confirmado y firmado.

    Es la ruta de producción, sin atajos: el evento se firma con el esquema de
    Stripe (HMAC-SHA256 de «<timestamp>.<cuerpo>»). La referencia es fija para
    que un mismo ingreso no se pueda acreditar dos veces.
    """
    body = json.dumps(
        {
            "id": f"evt_seed_{reference}",
            "object": "event",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": f"pi_seed_{reference}",
                    "object": "payment_intent",
                    "amount_received": amount_cents,
                    "currency": "eur",
                    "metadata": {"user_id": str(user_id)},
                }
            },
        }
    ).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        get_webhook_secret().encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    response = client.post(
        f"{backend_url}/api/webhooks/stripe",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": f"t={timestamp},v1={signature}",
        },
    )
    if response.status_code == 503:
        raise RuntimeError(
            "❌ El backend no tiene configurado STRIPE_WEBHOOK_SECRET y el seed no puede "
            "ingresar saldo. El entorno E2E (compose.e2e.yaml y los workflows) lo define "
            "con un valor desechable; en el entorno de desarrollo, define el de pruebas "
            "en backend/.env y reinicia el backend."
        )
    if response.status_code == 400:
        raise RuntimeError(
            "❌ El backend ha rechazado el evento firmado por el seed "
            f"({response.text}): su STRIPE_WEBHOOK_SECRET no coincide con el del seed."
        )
    fail_unless(response, 200, f"Ingresar saldo ({reference})")
    if response.json() != {"status": "success"}:
        raise RuntimeError(
            f"❌ El ingreso {reference} no se ha acreditado: {response.text}. "
            "El seed ya se ejecutó sobre esta base de datos."
        )


def create_e2e_opportunity(
    client: httpx.Client, backend_url: str, headers: dict[str, str], opportunity: dict
) -> int:
    """Crea una oportunidad del bloque E2E por la API y devuelve su id."""
    # Solo viajan los campos de OpportunityCreate: Pydantic descarta el resto en silencio.
    payload = {
        key: value
        for key, value in opportunity.items()
        if key not in {"owner", "published_days_ago", "final_state"}
    }
    response = client.post(
        OPPORTUNITIES_URL.format(API_BASE_URL=backend_url),
        data={"metadata": json.dumps(payload)},
        files={"images": ("portada.png", E2E_IMAGE, "image/png")},
        headers=headers,
    )
    fail_unless(response, 201, f"Crear la oportunidad «{opportunity['title']}»")
    print(f"✅ Oportunidad E2E creada: {opportunity['title']}")
    return response.json()["id"]


def run_e2e_sql(statements: list[tuple[str, dict]]) -> None:
    """Ejecuta en una transacción cambios de estado que deben afectar a una sola fila."""
    connection = get_database_connection()
    try:
        with connection.cursor() as cursor:
            for sql, params in statements:
                cursor.execute(sql, params)
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"❌ El cambio de estado de «{params['title']}» afectó a "
                        f"{cursor.rowcount} filas (se esperaba exactamente 1)"
                    )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_e2e_block(client: httpx.Client, backend_url: str) -> dict:
    """Crea cuentas, saldo y oportunidades del bloque E2E y publica las que toca.

    Se ejecuta antes que el catálogo heredado: el catálogo ordena por fecha de
    creación descendente y así las oportunidades heredadas siguen saliendo primero.
    """
    sessions: dict[str, dict[str, str]] = {}
    for account in e2e_accounts:
        user_id = register_e2e_account(client, backend_url, account)
        sessions[account["email"]] = login_headers(
            client, backend_url, account["email"], E2E_PASSWORD
        )
        if "entity" in account:
            response = client.post(
                f"{backend_url}/api/promotingentity",
                json=account["entity"],
                headers=sessions[account["email"]],
            )
            fail_unless(response, 201, f"Crear la entidad de {account['email']}")
            print(f"✅ Entidad promotora creada: {account['entity']['legal_name']}")
        if account["deposit_cents"]:
            credit_wallet(
                client,
                backend_url,
                user_id=user_id,
                amount_cents=account["deposit_cents"],
                reference=account["email"].split("@")[0].replace(".", "_"),
            )
            print(f"✅ Saldo ingresado por el webhook firmado: {account['email']}")

    opportunity_ids: dict[str, int] = {}
    for opportunity in e2e_opportunities:
        opportunity_ids[opportunity["title"]] = create_e2e_opportunity(
            client, backend_url, sessions[opportunity["owner"]], opportunity
        )

    now = datetime.now(UTC)
    run_e2e_sql(
        [
            (
                E2E_PUBLISH_SQL,
                {
                    "owner": opportunity["owner"],
                    "title": opportunity["title"],
                    "type": opportunity["type"],
                    "published_at": now - timedelta(days=opportunity["published_days_ago"]),
                },
            )
            for opportunity in e2e_opportunities
            if opportunity["published_days_ago"] is not None
        ]
    )
    print("✅ Oportunidades E2E publicadas")
    return {"sessions": sessions, "opportunity_ids": opportunity_ids}


def commit_e2e_funds(client: httpx.Client, backend_url: str, block: dict) -> None:
    """Compromete el capital por la API y deja cada oportunidad en su estado final."""
    for email, title, amount_cents in e2e_commitments:
        response = client.post(
            f"{backend_url}/api/opportunities/{block['opportunity_ids'][title]}/commitments",
            json={"amount_cents": amount_cents},
            headers=block["sessions"][email],
        )
        fail_unless(response, 201, f"Comprometer {amount_cents} céntimos en «{title}»")
    print(f"✅ Compromisos E2E creados: {len(e2e_commitments)}")

    now = datetime.now(UTC)
    # Vencida hace dos días; cerrada ahora mismo.
    moments = {"expired": now - timedelta(days=2), "closed": now, "rejected": None}
    run_e2e_sql(
        [
            (
                E2E_FINAL_STATE_SQL[opportunity["final_state"]],
                {
                    "owner": opportunity["owner"],
                    "title": opportunity["title"],
                    "type": opportunity["type"],
                    "moment": moments[opportunity["final_state"]],
                },
            )
            for opportunity in e2e_opportunities
            if "final_state" in opportunity
        ]
    )
    print("✅ Estados finales E2E aplicados (vencida, cerrada y rechazada)")


def verify_e2e_data(client: httpx.Client, backend_url: str, block: dict) -> None:
    """Comprueba por la API que el bloque E2E ha quedado como esperan los tests.

    Si algo no coincide, el seed falla aquí y no más tarde en Playwright.
    """
    problems: list[str] = []

    def expect(description: str, actual: object, expected: object) -> None:
        if actual != expected:
            problems.append(f"{description}: se esperaba {expected!r} y hay {actual!r}")

    def get(path: str, email: str | None = None, **params: str) -> object:
        response = client.get(
            f"{backend_url}{path}",
            params=params,
            headers=block["sessions"][email] if email else None,
        )
        fail_unless(response, 200, f"Consultar {path}")
        return response.json()

    for email, (available, committed) in E2E_EXPECTED_WALLETS.items():
        wallet = get("/api/me/wallet", email)
        expect(
            f"Saldo de {email}",
            (wallet["available_cents"], wallet["committed_cents"]),
            (available, committed),
        )

    portfolio = get("/api/me/opportunities", PORTFOLIO_PROMOTER_EMAIL)
    expect("Resumen de «Mis oportunidades»", portfolio["summary"], E2E_EXPECTED_PORTFOLIO_SUMMARY)
    investments = get("/api/me/commitments", INVESTOR_EMAIL)
    expect("Resumen de «Mis inversiones»", investments["summary"], E2E_EXPECTED_INVESTMENTS_SUMMARY)

    catalog = {item["title"]: item for item in get("/api/opportunities")}
    for title, committed in E2E_EXPECTED_COMMITTED.items():
        expect(
            f"Capital comprometido de «{title}» en el catálogo",
            catalog.get(title, {}).get("committed_cents"),
            committed,
        )
    for title in E2E_HIDDEN_FROM_CATALOG:
        expect(f"«{title}» en el catálogo", title in catalog, False)
    for opportunity in opportunities:
        expect(f"«{opportunity['title']}» en el catálogo", opportunity["title"] in catalog, True)

    for name, kind in (("Ático Último Tramo", "real_estate"), ("Biotech Ronda Final", "equity")):
        twins = get("/api/opportunities", name=name, type=kind)
        expect(f"Gemelas «{name}» disponibles", len(twins), 3)

    if problems:
        raise RuntimeError(
            "❌ El seed no ha dejado los datos E2E esperados:\n- " + "\n- ".join(problems)
        )
    print("✅ Autocomprobación del bloque E2E superada")


def seed_database(backend_url: str) -> None:
    """Crea el bloque E2E y el catálogo heredado, y comprueba el resultado."""
    with httpx.Client(timeout=30.0) as client:
        e2e_block = create_e2e_block(client, backend_url)

        register_response = client.post(
            REGISTER_URL.format(API_BASE_URL=backend_url),
            json={
                "email": SEED_EMAIL,
                "password": SEED_PASSWORD,
                "first_name": "Inyector",
                "phone": "+34612345678",
            },
        )
        if register_response.status_code == 201:
            print(f"✅ Usuario creado: {SEED_EMAIL}")
        elif register_response.status_code == 409:
            print(f"ℹ️ El usuario ya existe: {SEED_EMAIL}")
        else:
            print(
                "❌ No se pudo registrar el usuario: "
                f"{register_response.status_code} - {register_response.text}"
            )
            register_response.raise_for_status()

        login_response = client.post(
            LOGIN_URL.format(API_BASE_URL=backend_url),
            json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
        )
        login_response.raise_for_status()

        session_token = login_response.cookies.get("session")
        if not session_token:
            raise RuntimeError("El login no devolvió la cookie de sesión")

        headers = {
            "Cookie": f"session={session_token}",
        }

        promoting_entity_response = client.post(
            f"{backend_url}/api/promotingentity",
            json=promoting_entity,
            headers=headers,
        )
        if promoting_entity_response.status_code in (200, 201):
            print(f"✅ Entidad promotora creada: {promoting_entity['legal_name']}")
        elif promoting_entity_response.status_code == 409:
            print(
                "ℹ️ La entidad promotora ya existe: "
                f"{promoting_entity['legal_name']}"
            )
        else:
            print(
                "❌ No se pudo crear la entidad promotora: "
                f"{promoting_entity_response.status_code} - "
                f"{promoting_entity_response.text}"
            )
            promoting_entity_response.raise_for_status()

        total = len(opportunities)
        for index, opportunity in enumerate(opportunities, start=1):
            # La API/Pydantic no conserva este campo; se aplica después por SQL.
            payload = {
                key: value
                for key, value in opportunity.items()
                if key not in {"committed_cents", "cover_image_url"}
            }
            payload["location"] = opportunity_location(opportunity["location"])
            if opportunity["type"] == "real_estate":
                payload["real_estate"] = real_estate_details[opportunity["title"]]
            if opportunity["type"] == "equity":
                payload["business"] = business_details[opportunity["title"]]
            response = client.post(
                OPPORTUNITIES_URL.format(API_BASE_URL=backend_url),
                data={"metadata": json.dumps(payload)},
                files={"images": ("seed.png", SEED_IMAGE, "image/png")},
                headers=headers,
            )

            if response.status_code in (200, 201):
                print(
                    f"✅ [{index}/{total}] Inyectada con éxito: "
                    f"{opportunity['title']}"
                )
            elif response.status_code == 409:
                print(
                    f"ℹ️ [{index}/{total}] Ya existía: {opportunity['title']}"
                )
            else:
                print(f"❌ [{index}/{total}] Error al inyectar: {opportunity['title']}")
                print(f"   Detalle: {response.status_code} - {response.text}")
                response.raise_for_status()

        # Se ejecuta después de que la API haya creado (o confirmado) todas las
        # oportunidades para completar los datos que aún no forman parte del contrato.
        inject_sql_only_data()

        # Con todo publicado, el capital se compromete por la API.
        commit_e2e_funds(client, backend_url, e2e_block)
        verify_e2e_data(client, backend_url, e2e_block)


if __name__ == "__main__":
    print("Asegúrate de que el backend esté corriendo antes de ejecutar este script.")

    port = get_backend_port()
    print(f"Usando el puerto del backend: {port}")
    print("Iniciando inyección de datos (Seed)...")
    seed_database(backend_url=f"http://localhost:{port}")
    print("Proceso finalizado.")
