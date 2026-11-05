"""The restore planner: which files of an upload make up the world, and where they go."""
import io
import os
import tarfile
import zipfile

import pytest

from gamefleet_backend.db.models.game_server import GameServer
from gamefleet_backend.models.game_server_type import GameServerType as G
from gamefleet_backend.services.backup_service import (
    LAYOUTS, BackupError, World, _ChunkReader, plan_upload, tar_stream,
)


def zip_of(tmp_path, name, files):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)
    return str(path)


def tar_of(tmp_path, name, files):
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as t:
        for n, data in files.items():
            info = tarfile.TarInfo(n)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return str(path)


def raw(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def world(game, name):
    server = GameServer(game=game, name="x", address="h", port=1, data_path="/data", world_path="/data/world",
                        container_name="c")
    return World(server, LAYOUTS[game], name, f"/data/{name}", "/data/gamefleet-backups", [], False)


def dests(plan):
    try:
        return [dest for _, dest in plan.files]
    finally:
        plan.cleanup()


def test_java_world_at_archive_root(tmp_path):
    archive = zip_of(tmp_path, "a.zip", {"level.dat": b"x", "region/r.0.0.mca": b"y", "session.lock": b"z"})
    assert dests(plan_upload(world(G.minecraft, "World"), archive, "a.zip")) == ["World/level.dat", "World/region/r.0.0.mca"]


def test_java_world_in_wrapper_folder_is_renamed(tmp_path):
    archive = zip_of(tmp_path, "b.zip", {"backup/world/level.dat": b"x", "__MACOSX/._x": b""})
    assert dests(plan_upload(world(G.minecraft, "World"), archive, "b.zip")) == ["World/level.dat"]


def test_paper_dimensions_follow_the_world(tmp_path):
    archive = tar_of(tmp_path, "c.tar.gz", {"world/level.dat": b"x", "world_nether/level.dat": b"n",
                                            "world_the_end/level.dat": b"e"})
    assert dests(plan_upload(world(G.minecraft, "World"), archive, "c.tar.gz")) == [
        "World/level.dat", "World_nether/level.dat", "World_the_end/level.dat"]


def test_two_worlds_are_refused(tmp_path):
    archive = zip_of(tmp_path, "d.zip", {"alpha/level.dat": b"x", "beta/level.dat": b"y"})
    with pytest.raises(BackupError, match="several worlds"):
        plan_upload(world(G.minecraft, "World"), archive, "d.zip")


def test_bedrock_world_is_refused_on_java(tmp_path):
    archive = zip_of(tmp_path, "e.mcworld", {"level.dat": b"x", "db/CURRENT": b"y"})
    with pytest.raises(BackupError, match="other Minecraft edition"):
        plan_upload(world(G.minecraft, "World"), archive, "e.mcworld")
    assert dests(plan_upload(world(G.minecraft_bedrock, "Bedrock level"), archive, "e.mcworld")) == [
        "Bedrock level/level.dat", "Bedrock level/db/CURRENT"]


def test_factorio_save_takes_the_configured_name(tmp_path):
    save = zip_of(tmp_path, "mysave.zip", {"mysave/level-init.dat": b"x", "mysave/info.json": b"{}"})
    assert dests(plan_upload(world(G.factorio, "prod"), save, "mysave.zip")) == ["prod.zip"]
    assert dests(plan_upload(world(G.factorio, ""), save, "mysave.zip")) == ["mysave.zip"]


def test_valheim_pair_prefers_the_live_world_over_its_copies(tmp_path):
    archive = zip_of(tmp_path, "worlds.zip", {
        "config/worlds_local/Dedicated.db": b"1", "config/worlds_local/Dedicated.fwl": b"2",
        "config/worlds_local/Dedicated.fwl.old": b"3",
        "config/worlds_local/Dedicated_backup_auto-2025.db": b"4", "config/worlds_local/Dedicated_backup_auto-2025.fwl": b"5",
    })
    assert sorted(dests(plan_upload(world(G.valheim, "Dedicated"), archive, "worlds.zip"))) == ["Dedicated.db", "Dedicated.fwl"]


def test_valheim_needs_both_files(tmp_path):
    with pytest.raises(BackupError, match="incomplete"):
        plan_upload(world(G.valheim, "Dedicated"), zip_of(tmp_path, "v.zip", {"MyWorld.db": b"1"}), "v.zip")


def test_ark_copy_name_is_stripped_and_nested_for_asa(tmp_path):
    ark = raw(tmp_path, "TheIsland_WP_27.09.2026_00.30.00.ark", b"1")
    assert dests(plan_upload(world(G.ark_asa, ""), ark, os.path.basename(ark))) == ["TheIsland_WP/TheIsland_WP.ark"]
    assert dests(plan_upload(world(G.ark_ase, ""), ark, "TheIsland_27.09.2026_00.30.00.ark")) == ["TheIsland.ark"]


def test_wrong_file_type_is_refused(tmp_path):
    with pytest.raises(BackupError, match="Expected"):
        plan_upload(world(G.factorio, ""), raw(tmp_path, "x.sav", b"nope"), "x.sav")


def test_tar_stream_round_trips_the_plan(tmp_path):
    data = os.urandom(3000)
    archive = zip_of(tmp_path, "r.zip", {"world/level.dat": data, "world/region/r.mca": b"y" * 600})
    plan = plan_upload(world(G.minecraft, "World"), archive, "r.zip")
    try:
        out = b"".join(tar_stream(plan.files))
    finally:
        plan.cleanup()
    with tarfile.open(fileobj=io.BytesIO(out)) as t:
        members = {m.name: t.extractfile(m).read() for m in t.getmembers()}
    assert members == {"World/level.dat": data, "World/region/r.mca": b"y" * 600}


def test_chunk_reader_serves_tarfile_in_stream_mode():
    payload = os.urandom(5 * 1024 * 1024 + 7)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        info = tarfile.TarInfo("big.zip")
        info.size = len(payload)
        t.addfile(info, io.BytesIO(payload))
    raw_bytes = buf.getvalue()
    chunks = [raw_bytes[i:i + 2 * 1024 * 1024] for i in range(0, len(raw_bytes), 2 * 1024 * 1024)]
    with tarfile.open(fileobj=_ChunkReader(iter(chunks)), mode="r|") as t:
        member = t.next()
        assert t.extractfile(member).read() == payload
