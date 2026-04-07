from __future__ import annotations

from ptest.models import (
    ManagedObjectRecord,
    OBJECT_CLEARABLE_STATUSES,
    OBJECT_FAILURE_PRESERVED_STATUSES,
    OBJECT_NORMAL_STATUSES,
    OBJECT_RESETTABLE_STATUSES,
    OBJECT_STATUS_CREATED,
    OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
    OBJECT_STATUS_INSTALLED,
    OBJECT_STATUS_RUNNING,
    OBJECT_STATUS_START_FAILED_PRESERVED,
    OBJECT_STATUS_STOPPED,
    is_clearable_object_status,
    is_failure_preserved_object_status,
    is_normal_object_status,
    is_resettable_object_status,
)


def test_managed_object_record_defaults_to_created_status() -> None:
    record = ManagedObjectRecord(name="demo", type_name="mysql")
    assert record.status == OBJECT_STATUS_CREATED
    assert record.installed is False


def test_normal_object_statuses_are_classified_consistently() -> None:
    assert OBJECT_NORMAL_STATUSES == {
        OBJECT_STATUS_INSTALLED,
        OBJECT_STATUS_RUNNING,
        OBJECT_STATUS_STOPPED,
    }
    assert is_normal_object_status(OBJECT_STATUS_INSTALLED) is True
    assert is_normal_object_status(OBJECT_STATUS_RUNNING) is True
    assert is_normal_object_status(OBJECT_STATUS_STOPPED) is True
    assert is_normal_object_status(OBJECT_STATUS_INSTALL_FAILED_PRESERVED) is False


def test_failure_preserved_statuses_are_classified_consistently() -> None:
    assert OBJECT_FAILURE_PRESERVED_STATUSES == {
        OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
        OBJECT_STATUS_START_FAILED_PRESERVED,
    }
    assert (
        is_failure_preserved_object_status(OBJECT_STATUS_INSTALL_FAILED_PRESERVED)
        is True
    )
    assert (
        is_failure_preserved_object_status(OBJECT_STATUS_START_FAILED_PRESERVED) is True
    )
    assert is_failure_preserved_object_status(OBJECT_STATUS_RUNNING) is False


def test_clearable_and_resettable_status_sets_match_phase_one_scope() -> None:
    assert OBJECT_CLEARABLE_STATUSES == OBJECT_FAILURE_PRESERVED_STATUSES
    assert is_clearable_object_status(OBJECT_STATUS_INSTALL_FAILED_PRESERVED) is True
    assert is_clearable_object_status(OBJECT_STATUS_START_FAILED_PRESERVED) is True
    assert is_clearable_object_status(OBJECT_STATUS_INSTALLED) is False

    assert OBJECT_RESETTABLE_STATUSES == {
        OBJECT_STATUS_INSTALLED,
        OBJECT_STATUS_RUNNING,
        OBJECT_STATUS_STOPPED,
        OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
        OBJECT_STATUS_START_FAILED_PRESERVED,
    }
    assert is_resettable_object_status(OBJECT_STATUS_INSTALLED) is True
    assert is_resettable_object_status(OBJECT_STATUS_RUNNING) is True
    assert is_resettable_object_status(OBJECT_STATUS_STOPPED) is True
    assert is_resettable_object_status(OBJECT_STATUS_INSTALL_FAILED_PRESERVED) is True
    assert is_resettable_object_status(OBJECT_STATUS_START_FAILED_PRESERVED) is True
    assert is_resettable_object_status(OBJECT_STATUS_CREATED) is False
