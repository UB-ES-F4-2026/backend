import os
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
        "deadline": "2026-12-15T23:59:59.000Z",
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
        "deadline": "2026-11-30T18:00:00.000Z",
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
        "deadline": "2027-01-20T12:00:00.000Z",
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
        "deadline": "2026-11-15T23:59:59.000Z",
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
        "deadline": "2026-12-10T14:00:00.000Z",
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
        "deadline": "2027-02-28T23:59:59.000Z",
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
        "estimated_works_end": "2027-06-30",
        "estimated_rental_start": "2027-09-01",
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
        "estimated_works_end": "2027-12-15",
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
        "estimated_rental_start": "2027-03-01",
        "public_latitude": "38.643000",
        "public_longitude": "0.060000",
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


def inject_real_estate_details():
    """Inserta por SQL los datos de real_estate_opportunities de las oportunidades ya creadas."""
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
            for title, details in real_estate_details.items():
                cursor.execute(INSERT_REAL_ESTATE_SQL, {"title": title, **details})
                if cursor.rowcount:
                    print(f"✅ Datos inmobiliarios insertados: {title}")
                else:
                    print(f"ℹ️ Sin cambios (ya existían o no se encontró la oportunidad): {title}")
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
            print(f"ℹ️ El usuario ya existe: {SEED_EMAIL}")
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
            print(f"ℹ️ La entidad promotora ya existe: {promoting_entity['legal_name']}")
        else:
            print(
                "❌ No se pudo crear la entidad promotora: "
                f"{promoting_entity_response.status_code} - {promoting_entity_response.text}"
            )
            promoting_entity_response.raise_for_status()
        
        for index, opp in enumerate(opportunities, start=1):
            try:
                response = client.post(OPPORTUNITIES_URL.format(API_BASE_URL=backend_url), json=opp, headers=headers)

                if response.status_code in (200, 201):
                    print(f"✅ [{index}/6] Inyectada con éxito: {opp['title']}")
                else:
                    print(f"❌ [{index}/6] Error al inyectar: {opp['title']}")
                    print(f"   Detalle: {response.status_code} - {response.text}")

            except httpx.RequestError as exc:
                print(f"⚠️ Error de conexión en la petición {index}: {exc}")

    inject_real_estate_details()
        
        

if __name__ == "__main__":
    print("Asegúrate de que el backend esté corriendo antes de ejecutar este script.")

    port = get_backend_port()
    print(f"Usando el puerto del backend: {port}")

    print("Iniciando inyección de datos (Seed)...")
    seed_database(backend_url=f"http://localhost:{port}")
    print("Proceso finalizado.")