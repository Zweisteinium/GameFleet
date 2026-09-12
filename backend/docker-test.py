#!/usr/bin/env python3
"""
Docker container listing test using the official docker SDK (docker-py).

Security notes:
- Uses the Unix socket API (/var/run/docker.sock) via docker-py — no shell, no subprocess,
  no string interpolation into commands. There is no user-controlled input here at all.
- The Docker socket gives root-equivalent access to the host. In production, restrict
  socket access to a dedicated group (e.g. `docker`) and never expose it to web clients.
- docker-py returns typed Python objects; no parsing of raw strings from the daemon.
"""

import docker
import docker.errors
from datetime import datetime, timezone


def fmt_ports(ports: dict) -> str:
    """Format container port bindings into a readable string."""
    if not ports:
        return "none"
    parts = []
    for container_port, bindings in ports.items():
        if bindings:
            for b in bindings:
                parts.append(f"{b['HostIp'] or '0.0.0.0'}:{b['HostPort']} → {container_port}")
        else:
            parts.append(container_port)
    return ", ".join(parts)


def fmt_age(created: str) -> str:
    """Format ISO8601 creation timestamp as a human-readable age."""
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes = rem // 60
        if days:
            return f"{days}d {hours}h ago"
        if hours:
            return f"{hours}h {minutes}m ago"
        return f"{minutes}m ago"
    except Exception:
        return created


def main():
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as e:
        print(f"[ERROR] Cannot connect to Docker daemon: {e}")
        print("        Is Docker running? Do you have access to /var/run/docker.sock?")
        return 1

    containers = client.containers.list(all=True)

    if not containers:
        print("No containers found.")
        return 0

    print(f"{'NAME':<30} {'STATUS':<12} {'IMAGE':<40} {'CREATED':<18} {'PORTS'}")
    print("─" * 130)

    for c in sorted(containers, key=lambda x: x.name):
        image_tags = c.image.tags
        image = image_tags[0] if image_tags else c.image.short_id
        ports = fmt_ports(c.ports)
        created = fmt_age(c.attrs.get("Created", ""))

        print(f"{c.name:<30} {c.status:<12} {image:<40} {created:<18} {ports}")

    print(f"\n{len(containers)} container(s) total.")
    return 0


if __name__ == "__main__":
    exit(main())
