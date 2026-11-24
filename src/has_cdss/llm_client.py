from __future__ import annotations

import os
from urllib.parse import urlparse
from typing import Any

import httpx

from .config import LLMSettings


class MotorError(RuntimeError):
    """Falha neutra e segura do motor; nunca contém URL, chave ou corpo da resposta."""


class LLMHttpClient:
    def __init__(
        self,
        settings: LLMSettings,
        *,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.ready:
            raise MotorError("Configuração do motor incompleta.")
        parsed = urlparse(settings.base_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
        ):
            raise MotorError("Endpoint de configuração inválido.")
        public_deploy = os.getenv("PULSO_PUBLIC_DEPLOY") == "1"
        if public_deploy:
            from .public_network import PublicNetworkBackend, public_addresses

            try:
                if parsed.scheme != "https":
                    raise ValueError
                public_addresses(parsed.hostname or "", parsed.port or 443)
                if transport is None:
                    public_transport = httpx.HTTPTransport(trust_env=False)
                    # Integração deliberada com httpx/httpcore fixados no lockfile.
                    public_transport._pool._network_backend = PublicNetworkBackend()
                    transport = public_transport
            except Exception:
                raise MotorError("Endpoint de configuração inválido.") from None
        self._api_key = settings.api_key
        self._model_name = settings.model_name
        base = settings.base_url.rstrip("/")
        self._endpoint = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        self._http = httpx.Client(timeout=timeout_seconds, follow_redirects=False, transport=transport, trust_env=not public_deploy)

    def create(self, **payload: Any) -> dict[str, Any]:
        request_body = dict(payload)
        request_body["model"] = self._model_name
        try:
            response = self._http.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=request_body,
            )
            if response.status_code < 200 or response.status_code >= 300:
                raise MotorError("Falha ao comunicar com o motor de análise.")
            data = response.json()
        except MotorError:
            raise
        except Exception:
            # Não propagar exceção da biblioteca: sua representação pode conter endpoint ou detalhes de transporte.
            raise MotorError("Falha ao comunicar com o motor de análise.") from None
        if not isinstance(data, dict) or not isinstance(data.get("choices"), list) or not data["choices"]:
            raise MotorError("Resposta inválida do motor de análise.")
        return data

    def close(self) -> None:
        self._http.close()

    def __repr__(self) -> str:
        return "LLMHttpClient(configured=True)"
