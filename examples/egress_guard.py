"""Validating the address of a configurable endpoint before connecting.

The endpoint URL is a configuration value, which makes it a place where
credentials and clinical text can be sent by mistake. Four rules are checked
before a socket is opened, and the resolved address is pinned for the request so
that a second DNS answer cannot redirect the connection.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class EgressRefused(Exception):
    pass


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    address: str


def resolve_public_endpoint(url: str) -> Endpoint:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise EgressRefused("only https is allowed")
    port = parts.port or 443
    if port != 443:
        raise EgressRefused("only port 443 is allowed")
    host = parts.hostname
    if not host:
        raise EgressRefused("missing host")

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise EgressRefused(f"host did not resolve: {exc}") from exc
    if not infos:
        raise EgressRefused("host did not resolve")

    address = infos[0][4][0]
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        raise EgressRefused(f"address {ip} is not public and global")
    return Endpoint(host=host, port=port, address=str(ip))


def describe(endpoint: Endpoint) -> str:
    """The connection is opened to the pinned address, with SNI set to the host."""
    return f"connect to {endpoint.address}:{endpoint.port} with server_hostname={endpoint.host}"


if __name__ == "__main__":
    for candidate in (
        "https://example.com/v1/chat/completions",
        "http://example.com/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest/meta-data",
    ):
        try:
            print(candidate, "->", describe(resolve_public_endpoint(candidate)))
        except EgressRefused as exc:
            print(candidate, "-> refused:", exc)
