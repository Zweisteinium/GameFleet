"""Minimal asyncio implementation of the Source RCON protocol (used by Factorio, ARK, Rust, Source games...)."""
import asyncio
import struct

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


class RconError(Exception):
    pass


class RconAuthError(RconError):
    pass


def _packet(packet_id: int, packet_type: int, body: str) -> bytes:
    payload = struct.pack("<ii", packet_id, packet_type) + body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


async def _read_packet(reader: asyncio.StreamReader) -> tuple[int, int, str]:
    (length,) = struct.unpack("<i", await reader.readexactly(4))
    data = await reader.readexactly(length)
    packet_id, packet_type = struct.unpack("<ii", data[:8])
    return packet_id, packet_type, data[8:-2].decode("utf-8", errors="replace")


async def rcon_execute(host: str, port: int, password: str, commands: list[str], timeout: float = 5.0) -> list[str]:
    """Authenticate once and run each command in order, returning the response body of each."""
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    try:
        writer.write(_packet(0, SERVERDATA_AUTH, password))
        await writer.drain()
        # Source servers send an empty RESPONSE_VALUE before the AUTH_RESPONSE; Factorio only sends the latter.
        while True:
            packet_id, packet_type, _ = await asyncio.wait_for(_read_packet(reader), timeout)
            if packet_type == SERVERDATA_AUTH_RESPONSE:
                break
        if packet_id == -1:
            raise RconAuthError("RCON authentication failed (wrong password?)")

        responses: list[str] = []
        for index, command in enumerate(commands, start=1):
            writer.write(_packet(index, SERVERDATA_EXECCOMMAND, command))
            await writer.drain()
            while True:
                packet_id, packet_type, body = await asyncio.wait_for(_read_packet(reader), timeout)
                if packet_id == index:
                    responses.append(body)
                    break
        return responses
    finally:
        writer.close()
