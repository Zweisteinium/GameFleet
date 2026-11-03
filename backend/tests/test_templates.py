import pytest
import yaml

from gamefleet_backend.db.models.host_settings import HostSettingsBase
from gamefleet_backend.models.template import CreateRequest
from gamefleet_backend.services.template_service import (
    TemplateError, active_variables, get_template, render, templates,
)

SETTINGS = HostSettingsBase(servers_dir="/opt", owner_uid=1000, owner_gid=1000, default_memory_gb=4,
                            timezone="Europe/Berlin", stop_grace_seconds=60)


def request(**changes) -> CreateRequest:
    values = dict(template="minecraft", name="Skyblock", slug="skyblock", eula=True)
    values.update(changes)
    return CreateRequest(**values)


def service(rendered) -> dict:
    document = yaml.safe_load(rendered.compose)
    return document["services"]["minecraft"]


def test_all_templates_load():
    assert "minecraft" in templates()
    for template in templates().values():
        assert template.ports[0].publish, f"{template.id}: the first port is the game port and must be published"


def test_vanilla_defaults():
    rendered = render(get_template("minecraft"), request(), SETTINGS)
    assert rendered.folder == "/opt/minecraft/skyblock"
    assert rendered.project == rendered.container_name == "minecraft-skyblock"
    assert rendered.compose.startswith("# Created by GameFleet")
    svc = service(rendered)
    assert svc["image"] == "itzg/minecraft-server:java25"
    assert svc["restart"] == "unless-stopped" and svc["stop_grace_period"] == "60s"
    assert svc["ports"] == ["25565:25565"]  # RCON stays inside Docker
    assert svc["volumes"] == ["./data:/data"]
    env = svc["environment"]
    assert env["EULA"] == "TRUE" and env["TYPE"] == "VANILLA" and env["VERSION"] == "LATEST"
    assert env["UID"] == "1000" and env["TZ"] == "Europe/Berlin"
    assert env["MEMORY"] == "4G"
    assert svc["deploy"]["resources"]["limits"]["memory"] == "5120M"  # heap + 25 %
    # Advanced variables at their default are left to the image.
    assert "DIFFICULTY" not in env and "MAX_PLAYERS" not in env and "ONLINE_MODE" not in env


def test_secret_goes_to_env_file_only():
    rendered = render(get_template("minecraft"), request(), SETTINGS)
    password = rendered.env_file.split("RCON_PASSWORD=")[1].strip()
    assert len(password) >= 16
    assert password not in rendered.compose
    assert service(rendered)["environment"]["RCON_PASSWORD"] == "${RCON_PASSWORD}"
    assert rendered.secrets == ["RCON_PASSWORD"]


def test_generated_secrets_are_reused():
    template = get_template("minecraft")
    first = render(template, request(), SETTINGS)
    second = render(template, request(), SETTINGS, generated={"RCON_PASSWORD": "fixed-password-123"})
    assert "RCON_PASSWORD=fixed-password-123" in second.env_file
    assert first.compose == second.compose  # the compose file only references the secret


def test_modrinth_pack_hides_version_and_needs_pack():
    template = get_template("minecraft")
    with pytest.raises(TemplateError, match="Modpack is required"):
        render(template, request(values={"TYPE": "MODRINTH"}), SETTINGS)
    rendered = render(template, request(values={"TYPE": "MODRINTH", "MODRINTH_MODPACK": "cobblemon-fabric",
                                               "VERSION": "1.20.1", "MEMORY": "8g"}), SETTINGS)
    env = service(rendered)["environment"]
    assert env["MODRINTH_MODPACK"] == "cobblemon-fabric"
    assert "VERSION" not in env  # only for plain server types
    assert env["MEMORY"] == "8G"
    assert service(rendered)["deploy"]["resources"]["limits"]["memory"] == "10240M"


def test_show_if_follows_defaults():
    template = get_template("minecraft")
    active = {v.env for v in active_variables(template, {}, SETTINGS)}
    assert "VERSION" in active and "MODRINTH_MODPACK" not in active and "WHITELIST" not in active
    active = {v.env for v in active_variables(template, {"ENABLE_WHITELIST": "true"}, SETTINGS)}
    assert "WHITELIST" in active


@pytest.mark.parametrize("values, message", [
    ({"TYPE": "BUKKIT"}, "not one of the choices"),
    ({"MAX_PLAYERS": "lots"}, "whole number"),
    ({"MEMORY": "6 GB"}, "6G or 512M"),
    ({"ONLINE_MODE": "maybe"}, "true or false"),
    ({"VERSION": "1.21; rm -rf /"}, "not valid"),
    ({"MOTD": "two\nlines"}, "single line"),
    ({"TYPE": "AUTO_CURSEFORGE", "CF_PAGE_URL": "https://example.com/pack"}, "not valid"),
])
def test_invalid_values(values, message):
    with pytest.raises(TemplateError, match=message):
        render(get_template("minecraft"), request(values=values), SETTINGS)


def test_unknown_values_are_ignored():
    rendered = render(get_template("minecraft"), request(values={"JVM_OPTS": "-Xmx99G", "privileged": "true"}), SETTINGS)
    assert "JVM_OPTS" not in rendered.compose and "privileged" not in rendered.compose


@pytest.mark.parametrize("slug", ["", "-x", "x-", "Sky", "sky_block", "../etc", "a" * 33])
def test_invalid_slug(slug):
    with pytest.raises(TemplateError, match="folder name"):
        render(get_template("minecraft"), request(slug=slug), SETTINGS)


def test_eula_required():
    with pytest.raises(TemplateError, match="EULA"):
        render(get_template("minecraft"), request(eula=False), SETTINGS)


def test_port_tag_cpu_and_advanced_values():
    settings = SETTINGS.model_copy(update={"cpu_limit": 4.0})
    rendered = render(get_template("minecraft"), request(port=25570, tag="java17",
                                                         values={"DIFFICULTY": "hard", "MOTD": "Hi"}), settings)
    svc = service(rendered)
    assert svc["ports"] == ["25570:25565"]
    assert rendered.ports == [(25570, 25565, "tcp")]
    assert svc["image"] == "itzg/minecraft-server:java17"
    assert svc["deploy"]["resources"]["limits"]["cpus"] == "4"
    assert svc["environment"]["DIFFICULTY"] == "hard" and svc["environment"]["MOTD"] == "Hi"
    with pytest.raises(TemplateError, match="image tag"):
        render(get_template("minecraft"), request(tag="java17 --privileged"), SETTINGS)
