import pytest

from unitelabs.mycobotpro630 import create_app
from unitelabs.mycobotpro630.config import Mycobotpro630Config


@pytest.mark.asyncio
async def test_create_app_simulation_does_not_construct_elephant(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(**_kwargs: object) -> None:
        message = "Elephant constructed"
        raise AssertionError(message)

    monkeypatch.setattr("unitelabs.mycobotpro630.io.protocol.Elephant", factory)
    app_factory = create_app(Mycobotpro630Config())

    await app_factory.__anext__()
    await app_factory.aclose()
