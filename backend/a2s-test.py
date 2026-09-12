#!/usr/bin/env python3
# A2S query port note: this is NOT always the same as the game/connection port.
#   Source games (TF2, CS:GO, GMod, L4D2, Rust): query == game port
#   Valheim: query = game_port + 1  (2456 game → 2457 query)
#   ARK ASE: query port configured separately (often 27015, not 7777)

import argparse
import asyncio
import socket
import a2s

TIMEOUT = 5.0

# (game, label, host, query_port)
SERVERS = [
    # ("TF2",                  "Uncletopia Chicago",         "chi-1.us.uncletopia.com", 27015),
    ("TF2",                  "Skial 2Fort US",             "91.216.250.10",           27015),
    ("Garry's Mod",          "Sunrust Zombie Survival",    "193.243.190.32",          27015),
    ("HL2DM",                "Fusionhead Jazz Club",       "74.91.118.209",           27015),
    ("Insurgency (2014)",    "Bot Massacre COOP",          "109.230.215.32",          27016),
    # ("Insurgency Sandstorm", "ProRussianServer COOP",      "109.195.19.160",          27102),
    # ("CS:Zero",              "UGC.GS Dust2",               "94.23.156.177",           27018),
    # ("Rust",                 "Rustafied US Main",          "us.rustafied.com",        28015),
    # ("Factorio",             "Nexela Public",              "play.code-support.de",    34197),  # Factorio query port == game port (34197), not 27015
]


async def fetch(host: str, port: int):
    addr = (host, port)
    try:
        info, players = await asyncio.gather(
            a2s.ainfo(addr, timeout=TIMEOUT),
            a2s.aplayers(addr, timeout=TIMEOUT),
        )
        return info, players
    except (socket.timeout, asyncio.TimeoutError):
        return "TIMEOUT", None
    except ConnectionRefusedError:
        return "REFUSED", None
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}", None


def fmt(val) -> str:
    if val is None:
        return "n/a"
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)

def print_result(game: str, label: str, host: str, port: int, info, players, show_players: bool):
    print(f"── {game}  {label}  ({host}:{port})")

    if isinstance(info, str):
        print(f"   [{info}]")
        print()
        return

    # Print every field from the info dataclass
    for field, val in vars(info).items():
        print(f"   {field:<22} {fmt(val)}")

    if show_players:
        named = [p for p in (players or []) if p.name and p.name.strip()]
        if named:
            print(f"   ── Players ({len(named)}) ──")
            for p in sorted(named, key=lambda x: -(x.duration or 0)):
                h, m = divmod(int(p.duration or 0) // 60, 60)
                print(f"   {p.name:<30}  score={fmt(p.score):<5}  {h}h{m:02d}m  (index={p.index})")

    print()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--players", action="store_true", help="Print player list with scores and durations")
    args = parser.parse_args()

    print(f"Querying {len(SERVERS)} servers in parallel…\n")
    results = await asyncio.gather(*[fetch(host, port) for _, _, host, port in SERVERS])
    for (game, label, host, port), (info, players) in zip(SERVERS, results):
        print_result(game, label, host, port, info, players, show_players=args.players)


def _exception_handler(loop, ctx):
    msg = ctx.get("message", "")
    exc = ctx.get("exception")
    # Suppress known python-a2s noise:
    #   - "Event loop is closed" from __del__ cleanup
    #   - OSError/Invalid data stream from bz2 fragment decompression on malformed server responses
    if "Event loop is closed" in msg:
        return
    if isinstance(exc, OSError) and "Invalid data stream" in str(exc):
        return
    loop.default_exception_handler(ctx)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(_exception_handler)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()

