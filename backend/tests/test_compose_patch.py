import pytest
import yaml

from gamefleet_backend.services.compose_service import (
    ComposeError, INTERPOLATION, check_patch, patch, raw_environment, service_environment, _load,
)

GTNH = '''services:
  gtnh:
    image: itzg/minecraft-server:java25   # pinned
    container_name: gtnh-server
    environment:
      EULA: "TRUE"
      # --- Memory ---
      MEMORY: "16G"
      ENABLE_WHITELIST: "false"
      DIFFICULTY: hard            # GTNH default
      MOTD: "\\u00A74\\u00A7l--\\u00A7r Hi\\n\\u00A77Version: 2.9"
      RCON_PASSWORD: ${RCON_PASSWORD}
    ports:
      - "25565:25565"
'''


def env(text, service="gtnh"):
    return yaml.safe_load(text)["services"][service].get("environment")


def apply(text, changes, service="gtnh"):
    new = patch(text, service, changes)
    check_patch(text, new, service, changes)
    return new


def test_change_keeps_comments_and_other_lines():
    new = apply(GTNH, {"ENABLE_WHITELIST": "true", "DIFFICULTY": "normal"})
    assert '      ENABLE_WHITELIST: "true"\n' in new
    assert '      DIFFICULTY: "normal"            # GTNH default\n' in new
    assert "# --- Memory ---" in new and "# pinned" in new
    assert len(new.splitlines()) == len(GTNH.splitlines())
    assert env(new)["MOTD"] == env(GTNH)["MOTD"]


def test_motd_with_section_signs_and_newline():
    new = apply(GTNH, {"MOTD": "§4Hello\n§7second line"})
    assert env(new)["MOTD"] == "§4Hello\n§7second line"
    assert '      MOTD: "§4Hello\\n§7second line"\n' in new


def test_add_and_remove():
    new = apply(GTNH, {"VIEW_DISTANCE": "8", "MEMORY": None})
    e = env(new)
    assert e["VIEW_DISTANCE"] == "8" and "MEMORY" not in e
    assert new.index("VIEW_DISTANCE") < new.index("    ports:")
    assert '      VIEW_DISTANCE: "8"\n' in new


def test_dollar_is_escaped():
    new = apply(GTNH, {"MOTD": "Only $5"})
    assert env(new)["MOTD"] == "Only $$5"


def test_list_form():
    text = "services:\n  mc:\n    image: x\n    environment:\n      - EULA=TRUE\n      - MOTD=hi  # note\n    ports: []\n"
    new = apply(text, {"MOTD": "new one", "PVP": "false"}, "mc")
    assert env(new, "mc") == ["EULA=TRUE", "MOTD=new one", "PVP=false"]
    assert "# note" in new


def test_no_environment_block_yet():
    text = "services:\n  mc:\n    image: itzg/minecraft-server\n    ports:\n      - 25565:25565\n"
    new = apply(text, {"MOTD": "hi"}, "mc")
    assert env(new, "mc") == {"MOTD": "hi"}
    assert new.startswith("services:\n  mc:\n    image: itzg/minecraft-server\n    environment:\n      MOTD: \"hi\"\n")


def test_multiline_value_is_refused():
    text = "services:\n  mc:\n    image: x\n    environment:\n      MOTD: >\n        folded\n      PVP: 'true'\n"
    with pytest.raises(ComposeError, match="several lines"):
        patch(text, "mc", {"MOTD": "x"})
    assert env(apply(text, {"PVP": "false"}, "mc"), "mc")["PVP"] == "false"


def test_quoted_values_with_hash_and_escaped_quotes():
    text = 'services:\n  mc:\n    image: x\n    environment:\n      A: "x # not a comment \\" still"  # real\n      B: \'it\'\'s\'\n'
    new = apply(text, {"A": "1", "B": "2"}, "mc")
    assert '      A: "1"  # real\n' in new and '      B: "2"\n' in new


def test_newline_injection_cannot_add_keys():
    new = apply(GTNH, {"MOTD": "a\n    privileged: true"})
    assert "privileged" not in yaml.safe_load(new)["services"]["gtnh"]


def test_bad_names_and_unknown_service():
    with pytest.raises(ComposeError):
        patch(GTNH, "gtnh", {"BAD NAME": "x"})
    with pytest.raises(ComposeError, match="no service"):
        patch(GTNH, "other", {"A": "x"})


def test_interpolated_values_are_detected():
    raw = raw_environment(service_environment(_load(GTNH), "gtnh")[1])
    assert INTERPOLATION.search(raw["RCON_PASSWORD"])
    assert not INTERPOLATION.search("Only $$5")


def test_check_patch_catches_collateral_changes():
    with pytest.raises(ComposeError):
        check_patch(GTNH, GTNH.replace("gtnh-server", "other"), "gtnh", {})


def test_specs_for_a_server_loaded_from_the_database():
    # The database hands the game over as a plain string, not the enum.
    from gamefleet_backend.db.models.game_server import GameServer
    from gamefleet_backend.services.compose_service import specs_for
    server = GameServer(name="x", game="minecraft", address="x", port=1)
    envs = [o.env for o in specs_for(server, "itzg/minecraft-server:java25")]
    assert envs[0] == "MOTD" and "MEMORY" in envs and "TYPE" not in envs
    assert [o.env for o in specs_for(GameServer(name="v", game="valheim", address="x", port=1),
                                     "ghcr.io/lloesche/valheim-server:latest")] == [
        "SERVER_NAME", "SERVER_PUBLIC", "BACKUPS", "UPDATE_CRON"]
