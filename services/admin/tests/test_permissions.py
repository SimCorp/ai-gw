"""Unit tests for the pure path-based permission functions in unified_auth.

Covers can_access() prefix-inheritance semantics and the _ROLE_POWER ordering.
No DB / HTTP — these are pure-Python predicate tests.

A session role is a dict {"role": <role>, "node_path": <materialized path>}.
can_access(user, target_path, min_role) returns True iff the user holds a role
with power >= min_role on any node whose path is a prefix of target_path.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.routers.unified_auth import (
    _ROLE_POWER,
    _assert_sa_in_scope,
    can_access,
    max_role_power,
)
from fastapi import HTTPException


def _user(*roles):
    """Build a session-shaped user dict from (role, node_path) tuples."""
    return {"roles": [{"role": r, "node_path": p} for r, p in roles]}


# ---------------------------------------------------------------------------
# _ROLE_POWER ordering
# ---------------------------------------------------------------------------


def test_role_power_strict_descending_hierarchy():
    assert (
        _ROLE_POWER["platform_admin"]
        > _ROLE_POWER["area_owner"]
        > _ROLE_POWER["unit_lead"]
        > _ROLE_POWER["team_admin"]
        > _ROLE_POWER["developer"]
        > _ROLE_POWER["viewer"]
    )


def test_role_power_unknown_role_is_zero_via_can_access():
    # An unknown role name has power 0 → never satisfies even viewer.
    user = _user(("nonsense_role", "/"))
    assert can_access(user, "/anything", "viewer") is False


# ---------------------------------------------------------------------------
# Prefix inheritance — ancestor grants access to descendants
# ---------------------------------------------------------------------------


def test_role_at_ancestor_grants_descendant():
    # area_owner at /root/area → can access /root/area/unit/team
    user = _user(("area_owner", "/root/area"))
    assert can_access(user, "/root/area/unit/team", "team_admin") is True


def test_role_at_root_grants_everything():
    user = _user(("platform_admin", "/"))
    assert can_access(user, "/root/area/unit/team", "platform_admin") is True
    assert can_access(user, "/some/other/path", "viewer") is True


def test_role_at_exact_node_grants_that_node():
    user = _user(("team_admin", "/root/area/team"))
    assert can_access(user, "/root/area/team", "team_admin") is True


# ---------------------------------------------------------------------------
# Non-inheritance — sibling / descendant roles do NOT grant ancestor access
# ---------------------------------------------------------------------------


def test_role_at_sibling_does_not_grant():
    # team_admin at /root/area/team-a must not reach /root/area/team-b
    user = _user(("team_admin", "/root/area/team-a"))
    assert can_access(user, "/root/area/team-b", "viewer") is False


def test_role_at_child_does_not_grant_ancestor():
    # A role scoped to a deep node grants nothing on its ancestor.
    user = _user(("area_owner", "/root/area/unit/team"))
    assert can_access(user, "/root/area", "viewer") is False


def test_unrelated_path_does_not_grant():
    user = _user(("area_owner", "/root/finance"))
    assert can_access(user, "/root/engineering/team", "viewer") is False


# ---------------------------------------------------------------------------
# Role power vs min_role requirement
# ---------------------------------------------------------------------------


def test_higher_power_satisfies_lower_requirement():
    # area_owner (5) satisfies a viewer (1) requirement on the same subtree.
    user = _user(("area_owner", "/root/area"))
    assert can_access(user, "/root/area/team", "viewer") is True


def test_lower_power_does_not_satisfy_higher_requirement():
    # developer (2) cannot satisfy a team_admin (3) requirement.
    user = _user(("developer", "/root/area"))
    assert can_access(user, "/root/area/team", "team_admin") is False


def test_equal_power_satisfies_requirement():
    user = _user(("team_admin", "/root/area"))
    assert can_access(user, "/root/area/team", "team_admin") is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_roles_denies():
    assert can_access({"roles": []}, "/root/area", "viewer") is False


def test_missing_roles_key_denies():
    assert can_access({}, "/root/area", "viewer") is False


def test_empty_node_path_never_matches():
    # A role with an empty node_path must not act as a universal grant.
    user = _user(("platform_admin", ""))
    assert can_access(user, "/root/area", "viewer") is False


def test_multiple_roles_any_match_grants():
    # A user can hold several roles; access is granted if ANY one qualifies.
    user = _user(
        ("viewer", "/root/finance"),
        ("team_admin", "/root/engineering"),
    )
    assert can_access(user, "/root/engineering/team", "team_admin") is True
    assert can_access(user, "/root/finance/team", "team_admin") is False


# ---------------------------------------------------------------------------
# max_role_power — privilege-amplification guard for granting roles
# ---------------------------------------------------------------------------


def test_max_role_power_returns_highest_matching_role():
    user = _user(("area_owner", "/root/eng"), ("viewer", "/root/eng/team"))
    assert max_role_power(user, "/root/eng/team") == _ROLE_POWER["area_owner"]


def test_max_role_power_ignores_non_prefix_nodes():
    user = _user(("platform_admin", "/root/finance"))
    # The platform_admin grant is on a sibling subtree, not a prefix.
    assert max_role_power(user, "/root/eng/team") == 0


def test_area_owner_cannot_amplify_to_platform_admin():
    # The exploit: an area_owner (power 5) must not be able to grant
    # platform_admin (power 6) — max_role_power gates the add_permission check.
    user = _user(("area_owner", "/root/eng"))
    assert _ROLE_POWER["platform_admin"] > max_role_power(user, "/root/eng")
    # ...but they can grant a role at or below their own power.
    assert _ROLE_POWER["team_admin"] <= max_role_power(user, "/root/eng")


# ---------------------------------------------------------------------------
# _assert_sa_in_scope — cross-team service-account access guard
# ---------------------------------------------------------------------------


def _sa_session(team_id):
    """Mock session whose SA lookup returns the given team_id (or None)."""
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = (
        {"team_id": team_id} if team_id is not None else None
    )
    session.execute.return_value = result
    return session


async def test_sa_scope_platform_admin_bypasses_lookup():
    session = AsyncMock()
    caller = {"roles": [{"role": "platform_admin", "node_path": "/"}]}
    await _assert_sa_in_scope(session, "sa-1", caller)  # no raise
    session.execute.assert_not_called()


async def test_sa_scope_team_admin_blocked_cross_team():
    # team_admin of team A may not touch an SA owned by team B.
    session = _sa_session("team-B")
    caller = {"roles": [{"role": "team_admin", "scope_id": "team-A"}]}
    with pytest.raises(HTTPException) as exc:
        await _assert_sa_in_scope(session, "sa-b", caller)
    assert exc.value.status_code == 403


async def test_sa_scope_team_admin_allowed_own_team():
    session = _sa_session("team-A")
    caller = {"roles": [{"role": "team_admin", "scope_id": "team-A"}]}
    await _assert_sa_in_scope(session, "sa-a", caller)  # no raise


async def test_sa_scope_missing_sa_is_404():
    session = _sa_session(None)
    caller = {"roles": [{"role": "team_admin", "scope_id": "team-A"}]}
    with pytest.raises(HTTPException) as exc:
        await _assert_sa_in_scope(session, "ghost", caller)
    assert exc.value.status_code == 404
