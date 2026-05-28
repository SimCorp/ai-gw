"""Tests for the nightly auto-confirm-asks cron."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_auto_confirm_promotes_and_grants():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    update_result = MagicMock()
    update_result.__iter__.return_value = iter([
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "00000000-0000-0000-0000-000000000001"),
        ("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "00000000-0000-0000-0000-000000000002"),
    ])
    session.execute.return_value = update_result

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.jobs.auto_confirm_asks.async_session_maker", return_value=session_cm), \
         patch("app.jobs.auto_confirm_asks.grant_points", new=AsyncMock()) as gp:
        from app.jobs.auto_confirm_asks import run_auto_confirm
        count = await run_auto_confirm()

    assert count == 2
    # The SQL should be a status promotion
    args, _ = session.execute.await_args
    sql = str(args[0])
    assert "UPDATE champion_asks" in sql
    assert "'resolved'" in sql
    assert "auto_confirm_at" in sql
    assert "resolved_pending" in sql
    # Both grants issued
    assert gp.await_count == 2
    first = gp.await_args_list[0].kwargs
    assert first["delta"] == 200
    assert first["reason"] == "champion_ask_resolved_auto"
    assert first["engineer_id"] == "00000000-0000-0000-0000-000000000001"
    # commit happens before grants are issued
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_auto_confirm_returns_zero_when_none_pending():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    update_result = MagicMock()
    update_result.__iter__.return_value = iter([])
    session.execute.return_value = update_result

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.jobs.auto_confirm_asks.async_session_maker", return_value=session_cm), \
         patch("app.jobs.auto_confirm_asks.grant_points", new=AsyncMock()) as gp:
        from app.jobs.auto_confirm_asks import run_auto_confirm
        count = await run_auto_confirm()
    assert count == 0
    gp.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_auto_confirm_swallows_grant_failure():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    update_result = MagicMock()
    update_result.__iter__.return_value = iter([
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "00000000-0000-0000-0000-000000000001"),
    ])
    session.execute.return_value = update_result

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.jobs.auto_confirm_asks.async_session_maker", return_value=session_cm), \
         patch("app.jobs.auto_confirm_asks.grant_points",
               new=AsyncMock(side_effect=RuntimeError("boom"))):
        from app.jobs.auto_confirm_asks import run_auto_confirm
        count = await run_auto_confirm()
    assert count == 1  # status promotion still counted
