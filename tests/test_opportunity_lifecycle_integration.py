"""De l'alta de l'entitat promotora a l'oportunitat visible al catàleg (US01.9, US06.1.1).

Les proves de creació existents se salten l'autenticació; aquestes fan el camí amb la
cookie real: registre, sessió, entitat promotora, creació i publicació.
"""
import unittest
from datetime import UTC, datetime, timedelta

from app.models.opportunity import Opportunity, OpportunityStatus
from integration_support import (
    PNG_IMAGE,
    WEBP_IMAGE,
    IntegrationTestCase,
    new_email,
    opportunity_body,
)

# Forma que copia `frontend/src/store/useOpportunityStore.ts`.
OPPORTUNITY_KEYS = {
    "id",
    "user_id",
    "type",
    "title",
    "description",
    "location",
    "cover_image_url",
    "images",
    "target_amount_cents",
    "committed_cents",
    "deadline",
    "date_published",
    "date_closed",
    "created_at",
    "updated_at",
}
IMAGE_KEYS = {"id", "content_type", "position", "url"}
ENTITY_REQUIRED_TO_CREATE = {"detail": "A promoting entity is required to create opportunities"}
ENTITY_REQUIRED = {"detail": "A promoting entity is required"}
ENTITY_ALREADY_EXISTS = {"detail": "El usuario ya tiene una entidad promotora"}


class PromoterOnboardingTest(IntegrationTestCase):
    database_prefix = "promoter_onboarding_integration_test_"

    def entity_of(self, user_id: int) -> dict:
        entities = self.anonymous.get("/api/promotingentity").json()
        (entity,) = [entity for entity in entities if entity["user_id"] == user_id]
        return entity

    def my_opportunities(self, actor) -> dict:
        response = actor.client.get("/api/me/opportunities")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_user_registered_as_promoter_can_create_an_opportunity_after_login(self):
        promoter = self.new_actor(promoter=True)
        self.assertTrue(promoter.client.get("/api/auth/me").json()["is_promoter"])

        response = self.post_opportunity(promoter.client, opportunity_body())

        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertEqual(set(created), OPPORTUNITY_KEYS)
        self.assertEqual(created["user_id"], promoter.id)
        self.assertEqual((created["committed_cents"], created["date_published"]), (0, None))
        (stored,) = self.opportunities_of(promoter.id)
        self.assertEqual((stored.id, stored.status), (created["id"], OpportunityStatus.DRAFT))
        # Pendent de revisió: l'entitat la veu, el públic encara no.
        mine = self.my_opportunities(promoter)
        self.assertEqual(
            mine["summary"],
            {
                "committed_cents": 0,
                "published_count": 0,
                "in_funding_count": 0,
                "pending_review_count": 1,
            },
        )
        (item,) = mine["opportunities"]
        self.assertEqual((item["id"], item["funding_status"]), (created["id"], "pending_review"))
        self.assertEqual(self.entity_of(promoter.id)["published_projects_count"], 0)
        self.assertNotIn(created["id"], self.catalog_ids())

        self.publish(created["id"])

        self.assertIn(created["id"], self.catalog_ids())
        self.assertEqual(self.entity_of(promoter.id)["published_projects_count"], 1)
        self.assertEqual(
            self.my_opportunities(promoter)["summary"],
            {
                "committed_cents": 0,
                "published_count": 1,
                "in_funding_count": 1,
                "pending_review_count": 0,
            },
        )

    def test_user_without_entity_is_forbidden_until_they_create_one(self):
        user = self.new_actor()
        self.assertFalse(user.client.get("/api/auth/me").json()["is_promoter"])

        # Metadades vàlides: el 403 és per no tenir entitat, no per cap error de validació.
        forbidden = self.post_opportunity(user.client, opportunity_body())
        listing = user.client.get("/api/me/opportunities")

        self.assertEqual(
            (forbidden.status_code, forbidden.json()), (403, ENTITY_REQUIRED_TO_CREATE)
        )
        self.assertEqual((listing.status_code, listing.json()), (403, ENTITY_REQUIRED))
        self.assertEqual(self.opportunities_of(user.id), [])
        self.assertEqual(self.stored_files(), set())

        legal_name = f"Nova {user.id} SL"
        entity = user.client.post("/api/promotingentity", json={"legal_name": legal_name})

        self.assertEqual(entity.status_code, 201, entity.text)
        self.assertEqual(
            entity.json(),
            {
                "user_id": user.id,
                "legal_name": legal_name,
                "image_url": None,
                "published_projects_count": 0,
                "experience_years": None,
                "founding_year": None,
                "location": None,
            },
        )
        # La mateixa sessió passa a ser d'una entitat promotora, sense tornar a entrar.
        self.assertTrue(user.client.get("/api/auth/me").json()["is_promoter"])
        created = self.post_opportunity(user.client, opportunity_body())
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["user_id"], user.id)
        self.assertEqual(
            [item["id"] for item in self.my_opportunities(user)["opportunities"]],
            [created.json()["id"]],
        )
        self.assertEqual(len(self.stored_files()), 1)

    def test_registered_promoter_cannot_create_a_second_entity(self):
        client = self.new_client()
        email = new_email()
        legal_name = f"Primera {email[:8]} SL"
        registered = self.register(client, email, promoting_entity={"legal_name": legal_name})
        self.assertEqual(registered.status_code, 201, registered.text)
        self.log_in(email, client)

        response = client.post("/api/promotingentity", json={"legal_name": "Segona SL"})

        self.assertEqual((response.status_code, response.json()), (409, ENTITY_ALREADY_EXISTS))
        self.assertEqual(self.entity_of(registered.json()["id"])["legal_name"], legal_name)
        # El conflicte no deixa la sessió inservible.
        self.assertTrue(client.get("/api/auth/me").json()["is_promoter"])


class CatalogContractTest(IntegrationTestCase):
    database_prefix = "catalog_contract_integration_test_"

    def catalog(self, **params) -> list[dict]:
        response = self.anonymous.get("/api/opportunities", params=params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_catalog_item_has_the_exact_public_shape(self):
        promoter = self.new_actor(promoter=True)
        body = opportunity_body()
        response = self.post_opportunity(promoter.client, body, [PNG_IMAGE, WEBP_IMAGE])
        self.assertEqual(response.status_code, 201, response.text)
        opportunity_id = response.json()["id"]
        self.publish(opportunity_id)

        (item,) = [item for item in self.catalog() if item["id"] == opportunity_id]

        # Ni l'estat editorial ni cap camp intern: exactament el que el frontend copia.
        self.assertEqual(set(item), OPPORTUNITY_KEYS)
        self.assertEqual(
            {key: item[key] for key in (
                "user_id", "type", "title", "description", "location",
                "target_amount_cents", "committed_cents", "date_closed",
            )},
            {
                "user_id": promoter.id,
                "type": "real_estate",
                "title": body["title"],
                "description": body["description"],
                "location": "Girona, Girona, Espanya",
                "target_amount_cents": 100_000,
                "committed_cents": 0,
                "date_closed": None,
            },
        )
        self.assertEqual(
            datetime.fromisoformat(item["deadline"]), datetime.fromisoformat(body["deadline"])
        )
        self.assertIsNotNone(item["date_published"])
        self.assertEqual([set(image) for image in item["images"]], [IMAGE_KEYS, IMAGE_KEYS])
        self.assertEqual([image["position"] for image in item["images"]], [0, 1])
        self.assertEqual(item["cover_image_url"], item["images"][0]["url"])
        # El filtre per tipus retorna la mateixa forma i no barreja categories.
        self.assertIn(item, self.catalog(type="real_estate"))
        self.assertNotIn(opportunity_id, [other["id"] for other in self.catalog(type="equity")])

    def test_catalog_lists_the_newest_opportunities_first(self):
        promoter = self.new_actor(promoter=True)
        now = datetime.now(UTC)
        # Dates de creació explícites i diferents: l'ordre no té cap altre criteri de desempat.
        ages = {
            "middle": timedelta(days=2),
            "newest": timedelta(days=1),
            "oldest": timedelta(days=3),
        }
        ids = {}
        for name, age in ages.items():
            ids[name] = self.create_opportunity(promoter, publish=True)["id"]
            with self.Session() as db:
                db.get(Opportunity, ids[name]).created_at = now - age
                db.commit()

        listed = [item["id"] for item in self.catalog() if item["id"] in ids.values()]

        self.assertEqual(listed, [ids["newest"], ids["middle"], ids["oldest"]])


if __name__ == "__main__":
    unittest.main()
