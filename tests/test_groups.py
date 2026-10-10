from types import SimpleNamespace

from sqlalchemy import select

from statora.db.models import Monitor, MonitorStatus, MonitorType
from statora.scheduler import check_monitor_once
from statora.services.groups import evaluate_group

from .conftest import needs_services

UP, DOWN, DEG, PEND, MAINT = (
    MonitorStatus.UP,
    MonitorStatus.DOWN,
    MonitorStatus.DEGRADED,
    MonitorStatus.PENDING,
    MonitorStatus.MAINTENANCE,
)
STACK = {"mode": "stack"}


def members(*statuses, active=True):
    return [
        SimpleNamespace(id=i, name=f"m{i}", status=s, active=active) for i, s in enumerate(statuses, start=1)
    ]


def redundancy(min_up=1, degraded=True):
    return {"mode": "redundancy", "min_up": min_up, "degraded_on_member_failure": degraded}


# ---------------------------------------------------------------- pure evaluation


def test_stack_needs_every_member():
    assert evaluate_group(STACK, members(UP, UP), set()).status == UP
    assert evaluate_group(STACK, members(UP, DEG), set()).status == DEG
    result = evaluate_group(STACK, members(UP, DOWN, UP), set())
    assert result.status == DOWN and "m2" in result.message
    assert evaluate_group(STACK, members(UP, UP), {2}).status == MAINT  # member in maintenance
    assert evaluate_group(STACK, members(UP, PEND), set()).status == UP  # retrying isn't down yet


def test_redundancy_one_of_two():
    assert evaluate_group(redundancy(), members(UP, UP), set()).status == UP
    reduced = evaluate_group(redundancy(), members(UP, DOWN), set())
    assert reduced.status == DEG and "1/2" in reduced.message
    assert evaluate_group(redundancy(degraded=False), members(UP, DOWN), set()).status == UP
    assert evaluate_group(redundancy(), members(DOWN, DOWN), set()).status == DOWN


def test_redundancy_quorum_and_maintenance():
    two_of_three = redundancy(min_up=2)
    assert evaluate_group(two_of_three, members(UP, UP, DOWN), set()).status == DEG
    assert evaluate_group(two_of_three, members(UP, DOWN, DOWN), set()).status == DOWN
    # Short of capacity only because of planned maintenance → maintenance, not an outage.
    assert evaluate_group(two_of_three, members(UP, DOWN, UP), {3}).status == MAINT
    # Even counting the node in maintenance there isn't enough capacity → down.
    assert evaluate_group(redundancy(min_up=3), members(UP, DOWN, UP), {3}).status == DOWN
    assert evaluate_group(two_of_three, members(UP, UP, UP), {2, 3}).status == MAINT


def test_paused_members_are_ignored():
    mixed = members(UP, DOWN) + [SimpleNamespace(id=9, name="paused", status=DOWN, active=False)]
    assert evaluate_group(redundancy(), mixed, set()).status == DEG
    assert evaluate_group(STACK, members(DOWN, active=False), set()).status == PEND


# ---------------------------------------------------------------- API + scheduler


def _monitor_json(name, **kw):
    return {"name": name, "type": "tcp", "target": "127.0.0.1", "config": {"port": 9}, **kw}


async def _create(client, auth, payload):
    response = await client.post("/api/v1/monitors", json=payload, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


@needs_services
async def test_group_api_validation(client, auth):
    a = await _create(client, auth, _monitor_json("a"))
    b = await _create(client, auth, _monitor_json("b"))
    group = await _create(
        client, auth, {"name": "g", "type": "group", "member_ids": [a["id"], b["id"]], "config": redundancy()}
    )
    assert group["member_ids"] == [a["id"], b["id"]] and group["target"] == ""
    assert group["config"]["mode"] == "redundancy"

    bad = [
        {"name": "x", "type": "group", "member_ids": []},  # no members
        {"name": "x", "type": "group", "member_ids": [a["id"]], "config": redundancy(min_up=2)},  # min_up > n
        {"name": "x", "type": "group", "member_ids": [9999]},  # unknown member
        {**_monitor_json("x"), "member_ids": [a["id"]]},  # members on a non-group
    ]
    for payload in bad:
        assert (await client.post("/api/v1/monitors", json=payload, headers=auth)).status_code == 422, payload

    # Nesting is allowed, loops are not.
    outer = await _create(client, auth, {"name": "outer", "type": "group", "member_ids": [group["id"]]})
    loop = await client.patch(
        f"/api/v1/monitors/{group['id']}", json={"member_ids": [outer["id"]]}, headers=auth
    )
    assert loop.status_code == 422 and "itself" in loop.json()["detail"]
    self_ref = await client.patch(
        f"/api/v1/monitors/{group['id']}", json={"member_ids": [group["id"]]}, headers=auth
    )
    assert self_ref.status_code == 422

    # Deleting a member removes it from the group.
    await client.delete(f"/api/v1/monitors/{b['id']}", headers=auth)
    assert (await client.get(f"/api/v1/monitors/{group['id']}", headers=auth)).json()["member_ids"] == [
        a["id"]
    ]


@needs_services
async def test_group_status_follows_members(client, auth, session):
    a = await _create(client, auth, _monitor_json("node-a"))
    b = await _create(client, auth, _monitor_json("node-b"))
    group = await _create(
        client,
        auth,
        {"name": "cluster", "type": "group", "member_ids": [a["id"], b["id"]], "config": redundancy()},
    )
    stack = await _create(
        client, auth, {"name": "stack", "type": "group", "member_ids": [group["id"], a["id"]]}
    )

    async def set_status(monitor_id, status):
        monitor = await session.get(Monitor, monitor_id)
        monitor.status = status
        await session.commit()

    await set_status(a["id"], UP)
    await set_status(b["id"], UP)
    await check_monitor_once(group["id"])
    await check_monitor_once(stack["id"])
    session.expire_all()
    assert (await session.get(Monitor, group["id"])).status == UP
    assert (await session.get(Monitor, stack["id"])).status == UP

    # node-b goes down for real: its check fails (port 9 is closed, retries=0) → group degrades right away,
    # without waiting for the group's own interval.
    await check_monitor_once(b["id"])
    session.expire_all()
    cluster = await session.get(Monitor, group["id"])
    assert (await session.get(Monitor, b["id"])).status == DOWN
    assert cluster.status == DEG and "1/2" in cluster.last_message
    # The stack contains the (degraded) cluster, so it's degraded too.
    assert (await session.get(Monitor, stack["id"])).status == DEG

    # node-a fails as well → cluster down → stack down.
    await check_monitor_once(a["id"])
    session.expire_all()
    assert (await session.get(Monitor, group["id"])).status == DOWN
    assert (await session.get(Monitor, stack["id"])).status == DOWN

    groups = (await session.scalars(select(Monitor).where(Monitor.type == MonitorType.GROUP))).all()
    assert all(g.last_latency_ms is None for g in groups)


@needs_services
async def test_group_form_in_admin(client, auth):
    from .test_ui import csrf_from, login

    a = await _create(client, auth, _monitor_json("svc-a"))
    b = await _create(client, auth, _monitor_json("svc-b"))
    await login(client, "admin")
    form = await client.get("/admin/monitors/config-fields", params={"type": "group"})
    assert "svc-a" in form.text and 'name="cfg_mode"' in form.text

    page = await client.get("/admin/monitors/new")
    created = await client.post(
        "/admin/monitors/new",
        data={
            "csrf_token": csrf_from(page.text),
            "name": "Pair",
            "type": "group",
            "target": "",
            "interval_s": "30",
            "timeout_s": "10",
            "retries": "0",
            "active": "on",
            "cfg_mode": "redundancy",
            "cfg_min_up": "1",
            "cfg_degraded_on_member_failure": "on",
            "member_ids": [str(a["id"]), str(b["id"])],
        },
    )
    assert created.status_code == 303, created.text
    detail = await client.get(created.headers["location"])
    assert "Redundancy · 1 of 2 must be up" in detail.text and "svc-b" in detail.text
    member_page = await client.get(f"/admin/monitors/{a['id']}")
    assert "Part of groups" in member_page.text and "Pair" in member_page.text


@needs_services
async def test_status_page_lists_group_members(client, auth):
    # Regression: members of a group on a status page weren't eager-loaded and the page crashed.
    a = await _create(client, auth, _monitor_json("node-a"))
    paused = await _create(client, auth, _monitor_json("node-paused", active=False))
    group = await _create(
        client,
        auth,
        {"name": "Cluster", "type": "group", "member_ids": [a["id"], paused["id"]], "config": redundancy()},
    )
    await client.post(
        "/api/v1/status-pages",
        json={
            "slug": "grp",
            "title": "G",
            "groups": [{"name": "Core", "items": [{"monitor_id": group["id"]}]}],
        },
        headers=auth,
    )
    page = await client.get("/s/grp")
    assert page.status_code == 200, page.text
    assert 'class="members"' in page.text and "node-a" in page.text and "redundant" in page.text
    assert "node-paused" not in page.text  # paused members are hidden

    summary = (await client.get("/api/v1/public/pages/grp/summary")).json()
    component = summary["groups"][0]["components"][0]
    assert component["group_mode"] == "redundancy" and [m["name"] for m in component["members"]] == ["node-a"]


@needs_services
async def test_multi_selects_use_two_column_picker(client, auth):
    from .test_ui import login

    await client.post("/api/v1/status-pages", json={"slug": "p1", "title": "P1"}, headers=auth)
    await login(client, "admin")
    for url in ("/admin/incidents/new", "/admin/maintenance/new"):
        html = (await client.get(url)).text
        assert "data-dual-list" in html and "Hold Ctrl" not in html, url
    fields = (await client.get("/admin/monitors/config-fields", params={"type": "group"})).text
    assert "data-dual-list" in fields
    assert "js/dual-list.js" in (await client.get("/admin")).text
