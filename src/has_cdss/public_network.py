from __future__ import annotations

import ipaddress
import socket
from typing import Any

from httpcore._backends.sync import SyncBackend


def public_addresses(host: str, port: int) -> list[str]:
    if not host or port != 443:
        raise ValueError("Endpoint público inválido.")
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError
    except Exception:
        raise ValueError("Endpoint público inválido.") from None
    return addresses


class PublicNetworkBackend(SyncBackend):
    """Fixa IP público na conexão; httpcore preserva SNI/TLS do hostname original."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        addresses = public_addresses(host, port)
        # DNS é resolvido e validado imediatamente antes da conexão. Conectar ao
        # IP aprovado evita uma segunda resolução controlável durante o socket.
        return super().connect_tcp(
            addresses[0], port, timeout, local_address, socket_options
        )
