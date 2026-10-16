from __future__ import annotations

import ipaddress
import socket


_VIRTUAL_INTERFACE_MARKERS = (
    "docker",
    "hyper-v",
    "loopback",
    "npcap",
    "tailscale",
    "virtual",
    "virtualbox",
    "vmware",
    "vethernet",
    "wsl",
    "zerotier",
)

_PREFERRED_INTERFACE_MARKERS = (
    "ethernet",
    "wi-fi",
    "wifi",
    "wireless",
    "wlan",
    "以太",
    "无线",
)


def _parse_ipv4(value: object) -> ipaddress.IPv4Address | None:
    try:
        ip = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return None
    return ip if isinstance(ip, ipaddress.IPv4Address) else None


def _is_reachable_client_ipv4(ip: ipaddress.IPv4Address) -> bool:
    return not (
        ip.is_loopback
        or ip.is_unspecified
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
    )


def _interface_penalty(name: str) -> int:
    lower = str(name or "").lower()
    if any(marker in lower for marker in _VIRTUAL_INTERFACE_MARKERS):
        return 30
    if any(marker in lower for marker in _PREFERRED_INTERFACE_MARKERS):
        return 0
    return 10


def _add_candidate(
    candidates: list[tuple[int, int, int, str]],
    seen: set[str],
    value: object,
    *,
    interface_name: str = "",
    source_order: int = 0,
) -> None:
    ip = _parse_ipv4(value)
    if not ip or not _is_reachable_client_ipv4(ip):
        return

    text = str(ip)
    if text in seen:
        return
    seen.add(text)

    private_rank = 0 if ip.is_private else 1
    candidates.append((private_rank, _interface_penalty(interface_name), source_order, text))


def _add_psutil_candidates(candidates: list[tuple[int, int, int, str]], seen: set[str]) -> None:
    try:
        import psutil  # type: ignore
    except Exception:
        return

    try:
        stats_by_name = psutil.net_if_stats()
        interfaces = psutil.net_if_addrs()
    except Exception:
        return

    for interface_name, addresses in interfaces.items():
        try:
            stats = stats_by_name.get(interface_name)
            if stats is not None and not bool(getattr(stats, "isup", False)):
                continue
        except Exception:
            pass

        for addr in addresses:
            try:
                if getattr(addr, "family", None) != socket.AF_INET:
                    continue
                _add_candidate(
                    candidates,
                    seen,
                    getattr(addr, "address", ""),
                    interface_name=interface_name,
                    source_order=0,
                )
            except Exception:
                continue


def _add_route_candidates(candidates: list[tuple[int, int, int, str]], seen: set[str]) -> None:
    # UDP connect 不会实际发包，只用于询问系统默认出站路由会使用哪个本机地址。
    for target in ("223.5.5.5", "8.8.8.8", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.2)
                sock.connect((target, 80))
                local_ip = sock.getsockname()[0]
        except Exception:
            continue
        _add_candidate(candidates, seen, local_ip, interface_name="", source_order=1)


def _add_hostname_candidates(candidates: list[tuple[int, int, int, str]], seen: set[str]) -> None:
    try:
        hostname = socket.gethostname()
        _, _, addresses = socket.gethostbyname_ex(hostname)
    except Exception:
        return

    for address in addresses:
        _add_candidate(candidates, seen, address, interface_name="", source_order=2)


def get_lan_access_host(default: str = "127.0.0.1") -> str:
    """返回同网段设备可访问的本机 IPv4 地址。"""

    candidates: list[tuple[int, int, int, str]] = []
    seen: set[str] = set()

    _add_psutil_candidates(candidates, seen)
    _add_route_candidates(candidates, seen)
    _add_hostname_candidates(candidates, seen)

    if not candidates:
        return default

    candidates.sort()
    return candidates[0][3]
