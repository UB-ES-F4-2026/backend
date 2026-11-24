"""Proves unitàries de les primitives de contrasenya i token de sessió."""
import hashlib
import re
import unittest

from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


class PasswordSecurityTest(unittest.TestCase):
    def test_hashed_password_verifies_only_the_original_password(self):
        hashed_password = hash_password("Correct horse battery staple")

        self.assertNotEqual(hashed_password, "Correct horse battery staple")
        self.assertTrue(verify_password("Correct horse battery staple", hashed_password))
        self.assertFalse(verify_password("incorrect password", hashed_password))


class SessionTokenSecurityTest(unittest.TestCase):
    def test_generated_tokens_are_url_safe_and_unique(self):
        first_token = generate_session_token()
        second_token = generate_session_token()

        self.assertRegex(first_token, re.compile(r"^[A-Za-z0-9_-]+$"))
        self.assertGreaterEqual(len(first_token), 32)
        self.assertNotEqual(first_token, second_token)

    def test_session_token_hash_is_the_sha256_hex_digest(self):
        token = "test-session-token"

        hashed_token = hash_session_token(token)

        self.assertEqual(hashed_token, hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(len(hashed_token), 64)
        self.assertNotEqual(hashed_token, token)


if __name__ == "__main__":
    unittest.main()
