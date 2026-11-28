"""Finding the running application: the port is not a property of the machine.

RFEM gives its first instance 9000, the next 9001 and so on, so a port
pinned in a .env goes stale the moment the user opens RFEM alone (seen
2026-09-18 on 9001, 2026-10-13 on 9000 - with "connection refused" as the
only hint, which reads like "RFEM is not running").
"""

import pytest

from tekton_dlubal.dlubal.client import CANDIDATE_PORTS
from tekton_dlubal.dlubal.client import DlubalClient
from tekton_dlubal.dlubal.client import configured_port


class FakeApplication:
    """Answers on one port; every other one fails the way gRPC does."""

    opened = []

    def __init__(self, listening_on=None, api_key_value=None, port=None):
        FakeApplication.opened.append(port)
        if port != listening_on:
            raise RuntimeError(
                "gRPC Connection error: UNAVAILABLE - failed to connect to all addresses; "
                "last error: UNAVAILABLE: ipv4:127.0.0.1:{}: ConnectEx: Connection refused".format(port))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def client_against(listening_on, port=None):
    client = DlubalClient(api_key="k", port=port)
    client.api = type("api", (), {
        "Application": lambda **kwargs: FakeApplication(listening_on=listening_on, **kwargs)})
    FakeApplication.opened = []
    return client


def test_the_default_port_is_found_without_trying_others():
    with client_against(9000) as client:
        assert client.port == 9000
    assert FakeApplication.opened == [9000]


def test_a_second_instance_is_found_by_probing():
    with client_against(9002) as client:
        assert client.port == 9002
    assert FakeApplication.opened == [9000, 9001, 9002]


def test_a_pinned_port_is_not_second_guessed():
    """An explicit port that is wrong must say so, not silently use another instance."""
    with pytest.raises(RuntimeError, match="No RFEM answered"):
        client_against(9000, port=9001).__enter__()
    assert FakeApplication.opened == [9001]


def test_nothing_listening_names_the_ports_and_the_cause():
    with pytest.raises(RuntimeError) as error:
        client_against(9999).__enter__()
    message = str(error.value)
    assert "9000, 9001, 9002, 9003" in message
    assert "running" in message and "port" in message
    assert FakeApplication.opened == list(CANDIDATE_PORTS)


def test_an_authentication_failure_is_not_a_port_problem():
    """Probing on past a real answer would hide the actual error."""
    class Unauthenticated(FakeApplication):
        def __init__(self, **kwargs):
            FakeApplication.opened.append(kwargs.get("port"))
            raise RuntimeError("gRPC Connection error: UNAUTHENTICATED - API key is in incorrect format.")

    client = DlubalClient(api_key="nonsense")
    client.api = type("api", (), {"Application": lambda **kwargs: Unauthenticated(**kwargs)})
    FakeApplication.opened = []
    with pytest.raises(RuntimeError, match="UNAUTHENTICATED"):
        client.__enter__()
    assert FakeApplication.opened == [9000]


def test_the_environment_can_pin_a_port(monkeypatch):
    monkeypatch.setenv("DLUBAL_API_PORT", "9005")
    assert configured_port() == 9005
    monkeypatch.delenv("DLUBAL_API_PORT")
    assert configured_port() is None
