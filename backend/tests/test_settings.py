from gamefleet_backend.services.settings_service import mount_problem

SOCKET = {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True}


def bind(source: str, destination: str, rw: bool = True) -> dict:
    return {"Type": "bind", "Source": source, "Destination": destination, "RW": rw}


def test_unset_and_relative():
    assert "Choose the servers folder" in mount_problem(None, None, False)
    assert "absolute" in mount_problem("opt", None, True)


def test_native_run_only_needs_the_folder():
    assert mount_problem("/opt", None, True) is None
    assert "does not exist" in mount_problem("/opt", None, False)


def test_container_needs_same_path_mount():
    assert mount_problem("/opt", [SOCKET, bind("/opt", "/opt")], True) is None
    assert mount_problem("/opt/games", [bind("/opt", "/opt")], True) is None  # below a mount is fine
    assert "same path" in mount_problem("/opt", [SOCKET], True)
    assert "same path" in mount_problem("/opt", [bind("/srv", "/opt")], True)  # compose would hand out /opt
    assert "same path" in mount_problem("/optional", [bind("/opt", "/opt")], True)
    assert "same path" in mount_problem("/opt", [{"Type": "volume", "Source": "/opt", "Destination": "/opt"}], True)


def test_read_only_mount():
    assert "read-only" in mount_problem("/opt", [bind("/opt", "/opt", rw=False)], True)
