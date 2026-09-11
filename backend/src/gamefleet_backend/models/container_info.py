from pydantic import BaseModel


class PortBinding(BaseModel):
    host_port: int
    protocol: str  # tcp / udp


class ContainerInfo(BaseModel):
    name: str
    image: str
    state: str  # running, exited, paused, restarting, dead, created
    ports: list[PortBinding]
