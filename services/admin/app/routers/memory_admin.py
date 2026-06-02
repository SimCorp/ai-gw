from fastapi import APIRouter, Depends
from sqlalchemy import String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_role
from app.db import get_session

router = APIRouter(prefix="/memory-admin", tags=["memory-admin"])

_auth = [Depends(require_admin_role)]


@router.get("/stats", dependencies=_auth)
async def aggregate_stats(session: AsyncSession = Depends(get_session)):
    row = (
        (
            await session.execute(
                text("""
        SELECT
            (SELECT COUNT(DISTINCT developer_id) FROM memory_drawers)         AS developers_with_drawers,
            (SELECT COUNT(*)                      FROM memory_drawers)         AS total_drawers,
            (SELECT COUNT(DISTINCT developer_id) FROM memory_kg_nodes)        AS developers_with_kg,
            (SELECT COUNT(*)                      FROM memory_kg_nodes)        AS total_kg_nodes,
            (SELECT COUNT(*)                      FROM memory_kg_edges)        AS total_kg_edges,
            (SELECT COUNT(DISTINCT developer_id) FROM memory_diary)           AS developers_with_diary,
            (SELECT COUNT(*)                      FROM memory_diary)           AS total_diary_entries,
            (SELECT COUNT(DISTINCT developer_id) FROM memory_tunnels)         AS developers_with_tunnels,
            (SELECT COUNT(*)                      FROM memory_tunnels)         AS total_tunnels,
            (
                SELECT COUNT(DISTINCT dev_id) FROM (
                    SELECT developer_id AS dev_id FROM memory_drawers
                    UNION
                    SELECT developer_id FROM memory_kg_nodes
                    UNION
                    SELECT developer_id FROM memory_diary
                    UNION
                    SELECT developer_id FROM memory_tunnels
                ) AS all_devs
            )                                                                  AS total_developers
    """)
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else {}


@router.get("/developers", dependencies=_auth)
async def list_developers(session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                text("""
        SELECT
            dev.id              AS developer_id,
            dev.email,
            dev.display_name,
            COALESCE(d.drawers,     0) AS drawers,
            COALESCE(kn.kg_nodes,   0) AS kg_nodes,
            COALESCE(ke.kg_edges,   0) AS kg_edges,
            COALESCE(di.diary,      0) AS diary_entries,
            COALESCE(tu.tunnels,    0) AS tunnels,
            GREATEST(d.last_drawer, kn.last_node, di.last_diary) AS last_activity
        FROM developers dev
        INNER JOIN (
            SELECT developer_id, COUNT(*) AS drawers, MAX(created_at) AS last_drawer
            FROM memory_drawers GROUP BY developer_id
        ) d ON d.developer_id = dev.id
        LEFT JOIN (
            SELECT developer_id, COUNT(*) AS kg_nodes, MAX(created_at) AS last_node
            FROM memory_kg_nodes GROUP BY developer_id
        ) kn ON kn.developer_id = dev.id
        LEFT JOIN (
            SELECT developer_id, COUNT(*) AS kg_edges
            FROM memory_kg_edges GROUP BY developer_id
        ) ke ON ke.developer_id = dev.id
        LEFT JOIN (
            SELECT developer_id, COUNT(*) AS diary, MAX(updated_at) AS last_diary
            FROM memory_diary GROUP BY developer_id
        ) di ON di.developer_id = dev.id
        LEFT JOIN (
            SELECT developer_id, COUNT(*) AS tunnels
            FROM memory_tunnels GROUP BY developer_id
        ) tu ON tu.developer_id = dev.id
        ORDER BY GREATEST(d.last_drawer, kn.last_node, di.last_diary) DESC NULLS LAST
    """)
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


@router.get("/developers/{developer_id}/taxonomy", dependencies=_auth)
async def developer_taxonomy(developer_id: str, session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                text("""
        SELECT wing, room, COUNT(*) AS count
        FROM memory_drawers
        WHERE developer_id = (:dev_id)::uuid
        GROUP BY wing, room
        ORDER BY wing, room
    """).bindparams(bindparam("dev_id", type_=String)),
                {"dev_id": developer_id},
            )
        )
        .mappings()
        .all()
    )
    taxonomy: dict = {}
    for r in rows:
        taxonomy.setdefault(r["wing"], {})[r["room"]] = r["count"]
    return {"developer_id": developer_id, "taxonomy": taxonomy}


@router.delete("/developers/{developer_id}", dependencies=_auth, status_code=204)
async def purge_developer_memory(developer_id: str, session: AsyncSession = Depends(get_session)):
    for table in (
        "memory_drawers",
        "memory_kg_edges",
        "memory_kg_nodes",
        "memory_diary",
        "memory_tunnels",
    ):
        await session.execute(
            text(f"DELETE FROM {table} WHERE developer_id = (:dev_id)::uuid").bindparams(
                bindparam("dev_id", type_=String)
            ),
            {"dev_id": developer_id},
        )
    await session.commit()
