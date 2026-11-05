"""Edge detection on K720 sensor bits. Pure logic, no device."""

from __future__ import annotations

from kiosk.hardware.sensor_events import SensorEdgeDetector, SensorEvent, SensorReading

IDLE = SensorReading(user_exit=False, read_position=False, stack=False)
USER = SensorReading(user_exit=True, read_position=False, stack=False)
USER_AND_STACK = SensorReading(user_exit=True, read_position=False, stack=True)


def test_first_reading_is_only_a_baseline() -> None:
    detector = SensorEdgeDetector()

    assert detector.update(USER) == ()


def test_card_entering_user_exit_emits_one_event() -> None:
    detector = SensorEdgeDetector()
    detector.update(IDLE)

    assert detector.update(USER) == (SensorEvent.USER_EXIT_OCCUPIED,)


def test_steady_occupied_state_emits_nothing_more() -> None:
    detector = SensorEdgeDetector()
    detector.update(IDLE)
    detector.update(USER)

    assert detector.update(USER) == ()
    assert detector.update(USER) == ()


def test_card_taken_emits_freed_event() -> None:
    detector = SensorEdgeDetector()
    detector.update(IDLE)
    detector.update(USER)

    assert detector.update(IDLE) == (SensorEvent.USER_EXIT_FREED,)


def test_already_occupied_at_start_does_not_fire() -> None:
    detector = SensorEdgeDetector()
    detector.update(USER)

    assert detector.update(USER) == ()


def test_stack_refill_is_reported_separately() -> None:
    detector = SensorEdgeDetector()
    detector.update(USER)

    assert detector.update(USER_AND_STACK) == (SensorEvent.STACK_OCCUPIED,)


def test_read_position_edges_are_reported() -> None:
    detector = SensorEdgeDetector()
    detector.update(IDLE)

    at_read = SensorReading(user_exit=False, read_position=True, stack=False)
    assert detector.update(at_read) == (SensorEvent.READ_POSITION_OCCUPIED,)
    assert detector.update(IDLE) == (SensorEvent.READ_POSITION_FREED,)


def test_simultaneous_changes_are_all_reported() -> None:
    detector = SensorEdgeDetector()
    detector.update(IDLE)

    events = detector.update(USER_AND_STACK)

    assert set(events) == {SensorEvent.USER_EXIT_OCCUPIED, SensorEvent.STACK_OCCUPIED}
