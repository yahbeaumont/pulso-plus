from __future__ import annotations

import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from httpcore._backends.sync import SyncBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from has_cdss.config import LLMSettings, get_llm_settings
from has_cdss.llm_client import LLMHttpClient, MotorError
from has_cdss.public_network import PublicNetworkBackend, public_addresses


def answer(address: str) -> list[tuple]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (address, 443))]


class PublicDeploymentTests(unittest.TestCase):
    def test_global_key_ignored_for_open_session(self) -> None:
        with patch.dict(os.environ, {"PULSO_PUBLIC_DEPLOY": "1", "LLM_API_KEY": "synthetic-key", "LLM_BASE_URL": "https://example.test/v1", "LLM_MODEL_NAME": "test"}):
            self.assertFalse(get_llm_settings().ready)
            self.assertTrue(get_llm_settings({"api_key": "local-key", "base_url": "https://example.test/v1", "model_name": "test"}).ready)

    def test_private_addresses_and_metadata_denied(self) -> None:
        for address in ["127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "::1", "fc00::1"]:
            with self.subTest(address=address), patch("socket.getaddrinfo", return_value=answer(address)):
                with self.assertRaises(ValueError):
                    public_addresses("endpoint.test", 443)

    def test_plain_http_and_custom_port_denied(self) -> None:
        with patch.dict(os.environ, {"PULSO_PUBLIC_DEPLOY": "1"}), patch("socket.getaddrinfo", return_value=answer("8.8.8.8")):
            for base in ["http://localhost/v1", "http://endpoint.test/v1", "https://endpoint.test:8443/v1"]:
                with self.subTest(base=base), self.assertRaises(MotorError):
                    LLMHttpClient(LLMSettings("test", base, "model"))

    def test_connect_pins_validated_ip_not_hostname(self) -> None:
        sentinel = object()
        with patch("socket.getaddrinfo", return_value=answer("8.8.8.8")), patch.object(SyncBackend, "connect_tcp", return_value=sentinel) as connect:
            result = PublicNetworkBackend().connect_tcp("endpoint.test", 443, timeout=2)
            self.assertIs(result, sentinel)
            self.assertEqual(connect.call_args.args[:2], ("8.8.8.8", 443))

    def test_rebinding_private_resolution_fails_before_socket(self) -> None:
        with patch("socket.getaddrinfo", side_effect=[answer("8.8.8.8"), answer("127.0.0.1")]), patch.object(SyncBackend, "connect_tcp") as connect:
            self.assertEqual(public_addresses("endpoint.test", 443), ["8.8.8.8"])
            with self.assertRaises(ValueError):
                PublicNetworkBackend().connect_tcp("endpoint.test", 443)
            connect.assert_not_called()

    def test_errors_neutral_and_transport_compatible_with_lock(self) -> None:
        with patch.dict(os.environ, {"PULSO_PUBLIC_DEPLOY": "1"}), patch("socket.getaddrinfo", return_value=answer("8.8.8.8")):
            client = LLMHttpClient(LLMSettings("synthetic-secret", "https://endpoint.test/v1", "internal-model"))
            self.assertIsInstance(client._http._transport._pool._network_backend, PublicNetworkBackend)
            client.close()
            mocked = LLMHttpClient(LLMSettings("synthetic-secret", "https://endpoint.test/v1", "internal-model"), transport=httpx.MockTransport(lambda _r: httpx.Response(401, text="do not expose")))
            with self.assertRaises(MotorError) as caught:
                mocked.create(messages=[])
            self.assertNotIn("endpoint.test", str(caught.exception))
            self.assertNotIn("synthetic-secret", str(caught.exception))
            mocked.close()


if __name__ == "__main__":
    unittest.main()
