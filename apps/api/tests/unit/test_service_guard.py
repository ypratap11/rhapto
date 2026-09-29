import pytest
from service_guard import REQUIRE_SERVICES_ENV, service_unreachable, services_required


def test_by_default_an_unreachable_service_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(REQUIRE_SERVICES_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception, match="Postgres not reachable"):
        service_unreachable("Postgres not reachable")


def test_when_services_are_required_an_unreachable_service_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REQUIRE_SERVICES_ENV, "1")
    with pytest.raises(pytest.fail.Exception, match="Redis not reachable"):
        service_unreachable("Redis not reachable")


@pytest.mark.parametrize(
    ("value", "required"), [("1", True), (" 1 ", True), ("0", False), ("true", False), ("", False)]
)
def test_only_exactly_one_turns_the_switch_on(
    monkeypatch: pytest.MonkeyPatch, value: str, required: bool
) -> None:
    monkeypatch.setenv(REQUIRE_SERVICES_ENV, value)
    assert services_required() is required
