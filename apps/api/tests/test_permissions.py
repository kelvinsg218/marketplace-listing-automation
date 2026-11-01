from __future__ import annotations

import pytest


@pytest.fixture
def team(new_api):
    owner, admin, editor, viewer = new_api(), new_api(), new_api(), new_api()
    owner.register("owner@example.com", org="Loja")
    for client, email in ((admin, "admin@example.com"), (editor, "editor@example.com"),
                          (viewer, "viewer@example.com")):
        client.register(email, org=f"Pessoal {email}")
    org = owner.org_id()
    for email, role in (("admin@example.com", "admin"), ("editor@example.com", "editor"),
                        ("viewer@example.com", "viewer")):
        assert owner.post(f"/api/orgs/{org}/members", json={"email": email, "role": role}).status_code == 201
    return org, owner, admin, editor, viewer


def test_viewer_reads_but_cannot_write(team):
    org, owner, admin, editor, viewer = team
    p = owner.add_product(org, "S1")
    assert viewer.get(f"/api/orgs/{org}/products").status_code == 200
    assert viewer.post(f"/api/orgs/{org}/products", json={"sku": "S2", "name": "x"}).status_code == 403
    assert viewer.patch(f"/api/orgs/{org}/products/{p['id']}", json={"name": "x"}).status_code == 403
    assert viewer.delete(f"/api/orgs/{org}/products/{p['id']}").status_code == 403
    assert viewer.get(f"/api/orgs/{org}/audit").status_code == 403


def test_editor_writes_catalog_but_not_members(team):
    org, owner, admin, editor, viewer = team
    assert editor.post(f"/api/orgs/{org}/products", json={"sku": "S2", "name": "x"}).status_code == 201
    assert editor.post(f"/api/orgs/{org}/members",
                       json={"email": "owner@example.com", "role": "viewer"}).status_code == 403


def test_admin_manages_members_but_not_owners(team, new_api):
    org, owner, admin, editor, viewer = team
    viewer_id = viewer.get("/api/auth/me").json()["user"]["id"]
    owner_id = owner.get("/api/auth/me").json()["user"]["id"]
    assert admin.patch(f"/api/orgs/{org}/members/{viewer_id}", json={"role": "editor"}).status_code == 200
    assert admin.patch(f"/api/orgs/{org}/members/{viewer_id}", json={"role": "owner"}).status_code == 403
    assert admin.delete(f"/api/orgs/{org}/members/{owner_id}").status_code == 403
    assert admin.delete(f"/api/orgs/{org}/members/{viewer_id}").status_code == 204
    assert viewer.get(f"/api/orgs/{org}/products").status_code == 404  # removed member loses access at once


def test_last_owner_cannot_leave_or_be_demoted(team):
    org, owner, *_ = team
    owner_id = owner.get("/api/auth/me").json()["user"]["id"]
    assert owner.patch(f"/api/orgs/{org}/members/{owner_id}", json={"role": "admin"}).status_code == 409
    assert owner.delete(f"/api/orgs/{org}/members/{owner_id}").status_code == 409


def test_member_changes_are_audited(team):
    org, owner, admin, editor, viewer = team
    actions = [e["action"] for e in owner.get(f"/api/orgs/{org}/audit").json()]
    assert actions.count("member.added") == 3 and "org.created" in actions


def test_add_member_errors(team):
    org, owner, *_ = team
    assert owner.post(f"/api/orgs/{org}/members",
                      json={"email": "ghost@example.com", "role": "viewer"}).status_code == 404
    assert owner.post(f"/api/orgs/{org}/members",
                      json={"email": "editor@example.com", "role": "viewer"}).status_code == 409
