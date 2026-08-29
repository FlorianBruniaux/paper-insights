from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest
from _pytest.monkeypatch import MonkeyPatch


class _NetworkBlockedSocket(socket.socket):
    def connect(self, address: object) -> None:
        raise AssertionError(f"provider test attempted a real network connection: {address!r}")

    def connect_ex(self, address: object) -> int:
        raise AssertionError(f"provider test attempted a real network connection: {address!r}")


def _blocked_connection(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("provider test attempted a real network connection")


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch: MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(socket, "socket", _NetworkBlockedSocket)
    monkeypatch.setattr(socket, "create_connection", _blocked_connection)
    yield
