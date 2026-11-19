import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

try:  # psycopg 3 o psycopg2: la API que usamos es la misma en ambos
    import psycopg as pg
except ImportError:
    import psycopg2 as pg


OPPORTUNITIES_URL = "{API_BASE_URL}/api/opportunities"
REGISTER_URL = "{API_BASE_URL}/api/auth/register"
LOGIN_URL = "{API_BASE_URL}/api/auth/login"
SEED_EMAIL = "inyector@fintech.com"
SEED_PASSWORD = "inyector-fintech-2026"


def deadline_in(days: int) -> str:
    """Fecha límite relativa a la ejecución: una fecha fija caduca y la oportunidad sale del catálogo."""
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def date_in(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


# Datos con las modificaciones aplicadas (imágenes y localización)
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
    "location": "Madrid, España"
}

# Datos de real_estate_opportunities. No hay endpoint para crearlos, así que se
# insertan por SQL, enlazando con la oportunidad por título (los ids los asigna el backend).
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
    ON CONFLICT (opportunity_id) DO NOTHING
"""

# OpportunityCreate no acepta minimum_contribution_cents (Pydantic lo descartaría
# sin avisar), así que se informa por SQL una vez creada la oportunidad.
SET_MINIMUM_CONTRIBUTION_SQL = """
    UPDATE public.opportunities
    SET minimum_contribution_cents = %(minimum_contribution_cents)s
    WHERE title = %(title)s
"""


def load_env() -> dict[str, str]:
    """Lee el .env del backend (sin dependencias); las variables de entorno tienen prioridad."""
    here = Path(__file__).resolve().parent
    values: dict[str, str] = {}
    for candidate in (here / "backend" / ".env", here / ".env", here.parent / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    values[key.strip()] = value.strip().strip("\"'")
            break
    return {**values, **{k: v for k, v in os.environ.items() if k.startswith("POSTGRES_") or k == "BACKEND_PORT"}}


def get_backend_port() -> int:
    """Puerto del backend publicado por compose (BACKEND_PORT en el .env)."""
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


def inject_sql_only_data():
    """Inserta por SQL los datos sin endpoint (aportación mínima y real_estate_opportunities) de las oportunidades ya creadas."""
    env = load_env()
    missing = [k for k in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT") if k not in env]
    if missing:
        raise RuntimeError(f"Faltan variables en el .env: {', '.join(missing)}")

    connection = pg.connect(
        host="127.0.0.1",  # compose publica Postgres solo en localhost
        port=int(env["POSTGRES_PORT"]),
        dbname=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        with connection.cursor() as cursor:
            for opp in opportunities:
                cursor.execute(
                    SET_MINIMUM_CONTRIBUTION_SQL,
                    {"title": opp["title"], "minimum_contribution_cents": opp["minimum_contribution_cents"]},
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"No se pudo informar la aportación mínima de {opp['title']}: "
                        f"se encontraron {cursor.rowcount} oportunidades"
                    )
                print(f"✅ Aportación mínima informada: {opp['title']}")
            for title, details in real_estate_details.items():
                cursor.execute(INSERT_REAL_ESTATE_SQL, {"title": title, **details})
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"No se pudieron insertar los datos inmobiliarios de {title}: "
                        "la oportunidad no existe o ya tiene datos"
                    )
                print(f"✅ Datos inmobiliarios insertados: {title}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def seed_database(backend_url: str = "http://localhost:8000"):
    with httpx.Client() as client:
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
            raise RuntimeError(
                f"El usuario {SEED_EMAIL} ya existe; ejecuta el seed solo sobre una base de datos vacía"
            )
        else:
            print(
                "❌ No se pudo registrar el usuario: "
                f"{register_response.status_code} - {register_response.text}"
            )
            register_response.raise_for_status()

        login_response = client.post(
            LOGIN_URL.format(API_BASE_URL=backend_url),
            json={
                "email": SEED_EMAIL,
                "password": SEED_PASSWORD,
            },
        )
        login_response.raise_for_status()

        session_token = login_response.cookies.get("session")
        if not session_token:
            raise RuntimeError("El login no devolvió la cookie de sesión")

        headers = {
            "Content-Type": "application/json",
            "Cookie": f"session={session_token}",
        }

        promoting_entity_response = client.post(
            f"{backend_url}/api/promotingentity",
            json=promoting_entity,
            headers=headers
        )
        if promoting_entity_response.status_code in (200, 201):
            print(f"✅ Entidad promotora creada: {promoting_entity['legal_name']}")
        elif promoting_entity_response.status_code == 409:
            raise RuntimeError(
                "La entidad promotora del usuario seed ya existe; "
                "ejecuta el seed solo sobre una base de datos vacía"
            )
        else:
            print(
                "❌ No se pudo crear la entidad promotora: "
                f"{promoting_entity_response.status_code} - {promoting_entity_response.text}"
            )
            promoting_entity_response.raise_for_status()
        
        total = len(opportunities)
        for index, opp in enumerate(opportunities, start=1):
            # Solo los campos que acepta OpportunityCreate; el resto va por SQL.
            payload = {k: v for k, v in opp.items() if k != "minimum_contribution_cents"}
            response = client.post(OPPORTUNITIES_URL.format(API_BASE_URL=backend_url), json=payload, headers=headers)

            if response.status_code in (200, 201):
                print(f"✅ [{index}/{total}] Inyectada con éxito: {opp['title']}")
            else:
                # Un dato que falta hace fallar los E2E más tarde: mejor parar aquí.
                print(f"❌ [{index}/{total}] Error al inyectar: {opp['title']}")
                print(f"   Detalle: {response.status_code} - {response.text}")
                response.raise_for_status()

    inject_sql_only_data()
        
        

if __name__ == "__main__":
    print("Asegúrate de que el backend esté corriendo antes de ejecutar este script.")

    port = get_backend_port()
    print(f"Usando el puerto del backend: {port}")

    print("Iniciando inyección de datos (Seed)...")
    seed_database(backend_url=f"http://localhost:{port}")
    print("Proceso finalizado.")