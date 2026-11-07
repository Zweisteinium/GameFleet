"""Settings files are edited in place: only the changed lines move, everything else survives untouched."""
import pytest

from gamefleet_backend.services.config_service import (
    ConfigError, SettingSpec, _coerce, _escape, _from_text, _get_path, _set_path, _unescape,
    read_properties, write_properties,
)

PROPERTIES = """#Minecraft server properties
#Sat Sep 27 00:00:00 UTC 2026
motd=A Minecraft Server
max-players=20
pvp=true
level-name=World
key.with.dots : spaced value
"""


def test_read_properties_handles_comments_separators_and_escapes():
    values = read_properties(PROPERTIES + "unicode=caf\\u00e9 \\: ok\n")
    assert values["motd"] == "A Minecraft Server"
    assert values["key.with.dots"] == "spaced value"
    assert values["unicode"] == "café : ok"
    assert "#Minecraft" not in values


def test_write_properties_changes_only_the_named_lines():
    out = write_properties(PROPERTIES, {"motd": "Hello §a Welt ä", "pvp": "false", "new-key": "1"})
    lines = out.splitlines()
    assert lines[0] == "#Minecraft server properties"
    assert lines[2] == "motd=Hello \\u00a7a Welt \\u00e4"
    assert lines[3] == "max-players=20"
    assert lines[4] == "pvp=false"
    assert lines[-1] == "new-key=1"
    assert read_properties(out)["motd"] == "Hello §a Welt ä"


def test_escape_round_trips():
    for value in ("plain", "a=b:c#d!e\\f", "tab\there", "ünïcödé", ""):
        assert _unescape(_escape(value)) == value


def test_nested_json_paths():
    data = {"visibility": {"public": True}}
    assert _get_path(data, "visibility.public") is True
    assert _get_path(data, "visibility.lan") is None
    _set_path(data, "visibility.lan", False)
    _set_path(data, "new.nested.key", 3)
    assert data == {"visibility": {"public": True, "lan": False}, "new": {"nested": {"key": 3}}}


def spec(type, options=()):
    return SettingSpec(key="k", label="K", type=type, description="", options=list(options), group="")


def test_coerce_validates_types():
    assert _coerce(spec("bool"), "true") is True
    assert _coerce(spec("int"), "12") == 12
    assert _coerce(spec("enum", ("easy", "hard")), "hard") == "hard"
    with pytest.raises(ConfigError):
        _coerce(spec("int"), "twelve")
    with pytest.raises(ConfigError):
        _coerce(spec("enum", ("easy", "hard")), "peaceful")
    with pytest.raises(ConfigError):
        _coerce(spec("bool"), "maybe")


def test_from_text_reads_missing_and_broken_values_as_unknown():
    assert _from_text(spec("int"), None) is None
    assert _from_text(spec("int"), "abc") is None
    assert _from_text(spec("bool"), "TRUE") is True
    assert _from_text(spec("str"), "x") == "x"


def test_properties_round_trip_outside_the_bmp():
    from gamefleet_backend.services.config_service import read_properties, write_properties
    text = write_properties("motd=x\n", {"motd": "Hi \U0001F600 ä"})
    assert "\\ud83d\\ude00" in text
    assert read_properties(text)["motd"] == "Hi \U0001F600 ä"


ARK_INI = """[SessionSettings]
SessionName=Hammer, Sichel, Raptor

[ServerSettings]
ServerPVE=False
XPMultiplier=2.0
; a comment
RCONPort=27020

[/Script/Engine.GameSession]
MaxPlayers=42
"""


def test_read_ini_keys_by_section():
    from gamefleet_backend.services.config_service import read_ini
    values = read_ini(ARK_INI)
    assert values["SessionSettings/SessionName"] == "Hammer, Sichel, Raptor"
    assert values["/Script/Engine.GameSession/MaxPlayers"] == "42"
    assert values["ServerSettings/XPMultiplier"] == "2.0"


def test_write_ini_in_place_appends_to_section_and_adds_sections():
    from gamefleet_backend.services.config_service import read_ini, write_ini
    out = write_ini(ARK_INI, {
        "ServerSettings/XPMultiplier": "3.5", "ServerSettings/TamingSpeedMultiplier": "2.0",
        "/Script/Engine.GameSession/MaxPlayers": "10", "MessageOfTheDay/Message": "Hi",
    })
    assert "; a comment" in out
    lines = out.splitlines()
    # The new key lands after the last key of its section, before the blank line.
    assert lines[lines.index("RCONPort=27020") + 1] == "TamingSpeedMultiplier=2.0"
    values = read_ini(out)
    assert values["ServerSettings/XPMultiplier"] == "3.5"
    assert values["/Script/Engine.GameSession/MaxPlayers"] == "10"
    assert values["MessageOfTheDay/Message"] == "Hi"
    assert values["SessionSettings/SessionName"] == "Hammer, Sichel, Raptor"


def test_float_settings():
    from gamefleet_backend.services.config_service import _float_text
    spec = SettingSpec(key="x", label="X", type="float")
    assert _from_text(spec, "2.70") == 2.7
    assert _coerce(spec, "1.5") == 1.5
    assert _float_text(2.0) == "2.0" and _float_text(0.35) == "0.35"
    with pytest.raises(ConfigError):
        _coerce(spec, "fast")
