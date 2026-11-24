"""Imatges de les oportunitats: qui les pot veure i què queda al disc (US06.1.1).

La ruta de la imatge decideix amb la cookie real si qui la demana n'és el propietari;
les proves existents substitueixen aquesta dependència. Cada prova té el seu directori
d'imatges, de manera que pot comprovar-ne tot el contingut.
"""
import unittest

from integration_support import (
    INSUFFICIENT_BALANCE,
    PNG,
    PNG_IMAGE,
    WEBP,
    WEBP_IMAGE,
    IntegrationTestCase,
    opportunity_body,
)

IMAGE_NOT_FOUND = {"detail": "Image not found"}
IMAGE_KEYS = {"id", "content_type", "position", "url"}


class OpportunityMediaTest(IntegrationTestCase):
    database_prefix = "opportunity_media_integration_test_"

    def setUp(self):
        super().setUp()
        self.promoter = self.new_actor(promoter=True)

    def test_draft_images_are_served_only_to_the_owners_session(self):
        created = self.create_opportunity(self.promoter)
        url = created["cover_image_url"]
        expired_owner, expired_token = self.log_in(self.promoter.email)
        self.expire_session(expired_token)
        unknown_cookie = self.new_client()
        unknown_cookie.cookies.set("session", "unknown-token")
        strangers = {
            "another user": self.new_actor().client,
            "no session": self.anonymous,
            "expired owner session": expired_owner,
            "unknown cookie": unknown_cookie,
        }

        owner = self.promoter.client.get(url)

        self.assertEqual(owner.status_code, 200)
        self.assertEqual(owner.headers["content-type"], "image/png")
        self.assertEqual(owner.content, PNG)
        for name, client in strangers.items():
            with self.subTest(name):
                response = client.get(url)

                # 404 i no 403: no es revela que l'oportunitat pendent existeix.
                self.assertEqual((response.status_code, response.json()), (404, IMAGE_NOT_FOUND))

        self.publish(created["id"])

        for name, client in strangers.items():
            with self.subTest(name, published=True):
                response = client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, PNG)

    def test_image_must_belong_to_the_opportunity_in_the_path(self):
        published = self.create_opportunity(self.promoter, publish=True)
        draft = self.create_opportunity(self.promoter, images=[WEBP_IMAGE])
        published_image = published["images"][0]["id"]
        draft_image = draft["images"][0]["id"]

        own = self.anonymous.get(published["cover_image_url"])
        # La imatge d'un esborrany no es pot llegir pel camí d'una oportunitat pública.
        crossed = self.anonymous.get(
            f"/api/opportunities/{published['id']}/images/{draft_image}"
        )
        reversed_path = self.anonymous.get(
            f"/api/opportunities/{draft['id']}/images/{published_image}"
        )
        unknown = self.anonymous.get(
            f"/api/opportunities/{published['id']}/images/{2**31 - 1}"
        )

        self.assertEqual(own.status_code, 200)
        for response in (crossed, reversed_path, unknown):
            self.assertEqual((response.status_code, response.json()), (404, IMAGE_NOT_FOUND))

    def test_published_detail_exposes_the_uploaded_gallery_in_order(self):
        created = self.create_opportunity(self.promoter, images=[PNG_IMAGE, WEBP_IMAGE])
        self.publish(created["id"])

        response = self.anonymous.get(f"/api/opportunities/{created['id']}")

        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["images"], created["images"])
        self.assertEqual([set(image) for image in detail["images"]], [IMAGE_KEYS, IMAGE_KEYS])
        self.assertEqual([image["position"] for image in detail["images"]], [0, 1])
        self.assertEqual(
            [image["content_type"] for image in detail["images"]], ["image/png", "image/webp"]
        )
        # La portada és sempre la primera imatge pujada.
        self.assertEqual(detail["cover_image_url"], detail["images"][0]["url"])
        for image, content in zip(detail["images"], (PNG, WEBP)):
            served = self.anonymous.get(image["url"])
            self.assertEqual(served.status_code, 200)
            self.assertEqual(served.headers["content-type"], image["content_type"])
            self.assertEqual(served.content, content)
        self.assertEqual(len(self.stored_files()), 2)

    def test_rejected_creation_leaves_no_files_behind(self):
        self.deposit(self.promoter.id, 5_000)
        rejected = {
            "initial contribution above the balance": (
                opportunity_body(initial_contribution_cents=7_500),
                [PNG_IMAGE, WEBP_IMAGE],
                (409, INSUFFICIENT_BALANCE),
            ),
            # La primera imatge ja és al directori temporal quan la segona falla.
            "second file is not an image": (
                opportunity_body(),
                [PNG_IMAGE, ("notes.txt", b"plain text", "text/plain")],
                (422, {"detail": "Unsupported image format"}),
            ),
            "declared type does not match the content": (
                opportunity_body(),
                [PNG_IMAGE, ("photo.jpg", PNG, "image/jpeg")],
                (422, {"detail": "Image content type does not match its content"}),
            ),
        }

        for name, (body, images, expected) in rejected.items():
            with self.subTest(name):
                response = self.post_opportunity(self.promoter.client, body, images)

                self.assertEqual((response.status_code, response.json()), expected)
                self.assertEqual(self.stored_files(), set())
                self.assertEqual(self.opportunities_of(self.promoter.id), [])
                self.assertEqual(self.commitments(user_id=self.promoter.id), [])
                self.assertEqual(self.balances(self.promoter.id), (5_000, 0))

        # Una creació vàlida just després desa les seves imatges i reserva l'aportació.
        created = self.create_opportunity(
            self.promoter, images=[PNG_IMAGE, WEBP_IMAGE], initial_contribution_cents=5_000
        )

        files = self.stored_files()
        self.assertEqual(len(files), 2)
        self.assertEqual(
            {path.parent.as_posix() for path in files}, {f"opportunities/{created['id']}"}
        )
        self.assertEqual(self.balances(self.promoter.id), (0, 5_000))

    def test_image_removed_from_disk_returns_not_found(self):
        created = self.create_opportunity(self.promoter, publish=True)
        for path in self.stored_files():
            (self.media_root / path).unlink()

        response = self.anonymous.get(created["cover_image_url"])

        self.assertEqual((response.status_code, response.json()), (404, IMAGE_NOT_FOUND))


if __name__ == "__main__":
    unittest.main()
