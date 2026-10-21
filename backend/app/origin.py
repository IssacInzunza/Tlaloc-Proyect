"""Mutations must originate from this same local or private-network server."""
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request

PRIVATE_NETWORKS = tuple(map(ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")))


def require_local_origin(request: Request, detail="local_same_origin_required"):
    host = request.url.hostname
    local = host == "localhost"
    try:
        address = ip_address(host or "")
        local = address.is_loopback or any(address in network for network in PRIVATE_NETWORKS)
    except ValueError:
        pass
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if not local or request.headers.get("origin") != expected:
        raise HTTPException(403, detail)
