import docker
import docker.errors

from gamefleet_backend.models.container_info import ContainerInfo, PortBinding


def _map_container(c) -> ContainerInfo:
    seen: set[tuple[int, str]] = set()
    ports: list[PortBinding] = []
    for container_port_proto, bindings in (c.ports or {}).items():
        if not bindings:
            continue
        _, _, protocol = container_port_proto.partition("/")
        protocol = protocol or "tcp"
        for b in bindings:
            try:
                key = (int(b["HostPort"]), protocol)
                if key not in seen:
                    seen.add(key)
                    ports.append(PortBinding(host_port=key[0], protocol=protocol))
            except (KeyError, ValueError):
                continue

    image_tags = c.image.tags
    image = image_tags[0] if image_tags else c.image.short_id

    return ContainerInfo(
        name=c.name,
        image=image,
        state=c.status,
        ports=ports,
    )


class DockerService:
    MANAGED_LABEL = "gamefleet.managed"

    def __init__(self):
        self._client = docker.from_env()

    def get_all_containers(self) -> list[ContainerInfo]:
        """Return all containers on the host (any state)."""
        containers = self._client.containers.list(all=True)
        return [_map_container(c) for c in containers]

    def get_managed_containers(self) -> list[ContainerInfo]:
        """Return only containers labelled gamefleet.managed=true."""
        containers = self._client.containers.list(
            all=True,
            filters={"label": f"{self.MANAGED_LABEL}=true"},
        )
        return [_map_container(c) for c in containers]
