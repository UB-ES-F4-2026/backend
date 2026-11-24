"""Proves de validació i persistència de les imatges d'oportunitats."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core import media


class MediaTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.previous_media_root = media.MEDIA_ROOT
        media.MEDIA_ROOT = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        media.MEDIA_ROOT = self.previous_media_root
        self.temporary_directory.cleanup()

    @staticmethod
    def upload(content: bytes, content_type: str) -> UploadFile:
        return UploadFile(
            file=BytesIO(content),
            filename="image",
            headers=Headers({"content-type": content_type}),
        )

    async def test_stage_images_accepts_supported_formats(self) -> None:
        images = (
            self.upload(b"\xff\xd8\xff\xe0image", "image/jpeg"),
            self.upload(b"\x89PNG\r\n\x1a\nimage", "image/png"),
            self.upload(b"RIFF\x00\x00\x00\x00WEBPimage", "image/webp"),
        )

        staged_images = await media.stage_images(images)

        self.assertEqual(
            [(image.content_type, image.extension) for image in staged_images],
            [("image/jpeg", "jpg"), ("image/png", "png"), ("image/webp", "webp")],
        )
        self.assertEqual(
            [image.size_bytes for image in staged_images],
            [9, 13, 17],
        )
        self.assertTrue(all(image.temporary_path.is_file() for image in staged_images))

    async def test_stage_images_rejects_empty_or_invalid_files(self) -> None:
        with self.assertRaises(media.InvalidImage):
            await media.stage_images(())
        with self.assertRaises(media.InvalidImage):
            await media.stage_images((self.upload(b"not-an-image", "image/png"),))
        with self.assertRaises(media.InvalidImage):
            await media.stage_images(
                (self.upload(b"\x89PNG\r\n\x1a\nimage", "image/jpeg"),)
            )
        self.assertEqual(list((media.MEDIA_ROOT / ".tmp").glob("*")), [])

    async def test_stage_images_rejects_files_larger_than_five_megabytes(self) -> None:
        image = self.upload(
            b"\x89PNG\r\n\x1a\n" + b"x" * media.MAX_IMAGE_BYTES,
            "image/png",
        )

        with self.assertRaises(media.InvalidImage):
            await media.stage_images((image,))

        self.assertEqual(list((media.MEDIA_ROOT / ".tmp").glob("*")), [])

    async def test_persist_staged_images_uses_relative_unique_keys(self) -> None:
        staged_images = await media.stage_images(
            (self.upload(b"\x89PNG\r\n\x1a\nimage", "image/png"),)
        )

        stored_images = media.persist_staged_images(staged_images, opportunity_id=15)

        self.assertEqual(stored_images[0].content_type, "image/png")
        self.assertEqual(stored_images[0].size_bytes, 13)
        self.assertTrue(stored_images[0].storage_key.startswith("opportunities/15/"))
        self.assertTrue((media.MEDIA_ROOT / stored_images[0].storage_key).is_file())
        self.assertFalse(staged_images[0].temporary_path.exists())
