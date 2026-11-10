"""Test-only fakes for hardware interfaces.

Living under ``tests/`` keeps them out of the installed package, so the
operating profile cannot import or activate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kiosk.domain.errors import DispenserEmptyError, HardwareTimeoutError
from kiosk.hardware.interfaces import DispenserState


@dataclass
class FakeState:
    """Read-only sensor view of the fake dispenser."""

    user_exit_occupied: bool = False
    read_position_occupied: bool = False
    stack_occupied: bool = False


@dataclass
class FakeDispenser:
    """In-memory card dispenser for tests.

    Attributes:
        uid: UID returned by ``read_uid``.
        stock: Cards left; issuing with zero raises ``DispenserEmptyError``.
        failures: Queue of exceptions raised by the next operations, in order.
        calls: Recorded method names for assertions.
    """

    uid: str = "8388B21A"
    stock: int = 10
    failures: list[Exception] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    _state: FakeState = field(default_factory=FakeState)

    @property
    def exit_occupied(self) -> bool:
        """Whether a card currently sits at the user exit (test helper)."""
        return self._state.user_exit_occupied

    @exit_occupied.setter
    def exit_occupied(self, value: bool) -> None:
        self._state.user_exit_occupied = value

    def _check(self, name: str) -> None:
        self.calls.append(name)
        if self.failures:
            raise self.failures.pop(0)

    def issue_card(self) -> None:
        self._check("issue_card")
        if self.stock <= 0:
            raise DispenserEmptyError("stock empty")
        self.stock -= 1
        self._state.user_exit_occupied = True

    def move_card_to_read_position(self) -> None:
        """FC7: from the stack (new card) or from the user exit, to read position."""
        self._check("move_card_to_read_position")
        if self._state.user_exit_occupied:
            self._state.user_exit_occupied = False
        elif self.stock > 0:
            self.stock -= 1
        else:
            raise DispenserEmptyError("stock empty")
        self._state.read_position_occupied = True

    def move_card_to_user_exit(self) -> None:
        self._check("move_card_to_user_exit")
        if not (self._state.read_position_occupied or self._state.stack_occupied):
            raise HardwareTimeoutError("no card to move to user exit")
        self._state.read_position_occupied = False
        self._state.user_exit_occupied = True

    def read_uid(self) -> str:
        self._check("read_uid")
        if not self._state.read_position_occupied:
            raise HardwareTimeoutError("no card at read position")
        return self.uid

    def dispose_card(self) -> None:
        self._check("dispose_card")
        self._state.read_position_occupied = False

    def poll_state(self) -> DispenserState:
        self._check("poll_state")
        return self._state


@dataclass
class FakeIdReader:
    """Scripted ID reader for tests.

    Attributes:
        responses: Identifiers returned in order. Exceptions are raised as-is.
    """

    responses: list[str | Exception] = field(default_factory=list)

    def read_id(self) -> str:
        if not self.responses:
            raise HardwareTimeoutError("no id scripted")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
