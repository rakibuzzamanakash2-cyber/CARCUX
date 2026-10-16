"""The public side: open reading of official posts; verified email accounts to like,
comment and report; reports hide comments; moderators and bans; deleting an account."""

import re

import pytest

from app.services import mailer
from app.services import public as rules
from tests.test_statements import _publish, _verify
from tests.test_statements import setup as setup  # noqa: F401 (fixture)

P = "/api/v1/public"


def _token_from_mail() -> str:
    body = mailer.OUTBOX[-1].get_content()
    return re.search(r"token=([\w-]+)", body).group(1)


def _person(client, email="rina@example.com", name="Rina"):
    mailer.OUTBOX.clear()
    r = client.post(f"{P}/auth/signup", json={"email": email, "display_name": name,
                                              "password": "correct horse"})  # fmt: skip
    assert r.status_code == 202, r.text
    v = client.post(f"{P}/auth/verify", json={"token": _token_from_mail()})
    assert v.status_code == 200, v.text
    return {"Authorization": f"Bearer {v.json()['access_token']}"}


@pytest.fixture
def post(client, setup):
    _verify(client, setup)
    return _publish(client, setup).json()


def test_anyone_reads_verified_posts_without_the_brief(client, setup, post):
    feed = client.get(f"{P}/posts").json()
    assert [p["id"] for p in feed] == [post["id"]]
    assert "brief" not in feed[0] and "author" not in feed[0]
    one = client.get(f"{P}/posts/{post['id']}").json()
    assert one["comment_list"] == [] and one["likes"] == 0
    page = client.get(f"{P}/pages/ddm").json()
    assert page["page"]["name"] == "Department of Disaster Management"
    inc = client.get(f"{P}/incidents/{setup['event'].id}").json()
    assert inc["event"]["title"] == "Waterlogging at Mirpur 10"


def test_an_event_without_an_official_post_is_not_public(client, setup):
    assert client.get(f"{P}/incidents/{setup['event'].id}").status_code == 404


def test_signup_needs_the_email_link_and_does_not_reveal_accounts(client, setup):
    mailer.OUTBOX.clear()
    body = {"email": "rina@example.com", "display_name": "Rina", "password": "correct horse"}
    assert client.post(f"{P}/auth/signup", json=body).status_code == 202
    login = {"email": "rina@example.com", "password": "correct horse"}
    r = client.post(f"{P}/auth/login", json=login)
    assert r.status_code == 401 and "Confirm your email" in r.json()["detail"]
    # Signing up again looks the same, and does not send another mail right away.
    assert client.post(f"{P}/auth/signup", json=body).status_code == 202
    assert len(mailer.OUTBOX) == 1
    assert client.post(f"{P}/auth/verify", json={"token": "x" * 40}).status_code == 422
    assert client.post(f"{P}/auth/verify", json={"token": _token_from_mail()}).status_code == 200
    assert client.post(f"{P}/auth/login", json=login).status_code == 200
    bad = client.post(f"{P}/auth/signup", json={**body, "display_name": "<script>"})
    assert bad.status_code == 422


def test_tokens_do_not_cross(client, setup):
    person = _person(client)
    assert client.get("/api/v1/events", headers=person).status_code == 401
    assert client.get(f"{P}/auth/me", headers=setup["h"]["analyst"]).status_code == 401
    assert client.get(f"{P}/auth/me", headers=person).json()["display_name"] == "Rina"


def test_likes_and_comments(client, setup, post):
    rina = _person(client)
    pid = post["id"]
    assert client.put(f"{P}/posts/{pid}/like").status_code == 401
    assert client.put(f"{P}/posts/{pid}/like", headers=rina).status_code == 204
    assert client.put(f"{P}/posts/{pid}/like", headers=rina).status_code == 204  # once
    seen = client.get(f"{P}/posts/{pid}", headers=rina).json()
    assert (seen["likes"], seen["liked"]) == (1, True)
    c = client.post(f"{P}/posts/{pid}/comments", json={"body": "Thank you for the update"},
                    headers=rina)  # fmt: skip
    assert c.status_code == 201 and c.json()["author"] == "Rina"
    for k in range(rules.COMMENTS_PER_WINDOW - 1):
        client.post(f"{P}/posts/{pid}/comments", json={"body": f"more {k}"}, headers=rina)
    fast = client.post(f"{P}/posts/{pid}/comments", json={"body": "one more"}, headers=rina)
    assert fast.status_code == 422 and "too fast" in fast.json()["detail"]
    anon = client.get(f"{P}/posts/{pid}").json()
    assert anon["comments"] == rules.COMMENTS_PER_WINDOW and "email" not in str(anon)
    assert client.delete(f"{P}/posts/{pid}/like", headers=rina).status_code == 204
    assert client.get(f"{P}/posts/{pid}").json()["likes"] == 0


def test_reports_hide_and_moderators_decide(client, setup, post):
    pid = post["id"]
    rina = _person(client)
    cid = client.post(f"{P}/posts/{pid}/comments", json={"body": "The office is lying, 50 died"},
                      headers=rina).json()["id"]  # fmt: skip
    reporters = [_person(client, f"r{k}@example.com", f"Reader {k}") for k in range(3)]
    own = client.post(f"{P}/comments/{cid}/report", json={"reason": "abuse"}, headers=rina)
    assert own.status_code == 422
    for k, h in enumerate(reporters):
        r = client.post(f"{P}/comments/{cid}/report", json={"reason": "false_information"},
                        headers=h)  # fmt: skip
        assert r.status_code == 204, r.text
        visible = client.get(f"{P}/posts/{pid}").json()["comments"]
        assert visible == (1 if k < 2 else 0)  # hidden at the third report

    official, admin = setup["h"]["official"], setup["h"]["admin"]
    waiting = client.get("/api/v1/moderation/comments?state=reported", headers=official).json()
    assert [w["id"] for w in waiting] == [cid] and waiting[0]["reports"] == 3
    assert (
        client.get("/api/v1/moderation/comments", headers=setup["h"]["analyst"]).status_code == 403
    )
    kept = client.post(f"/api/v1/moderation/comments/{cid}/restore", headers=official)
    assert kept.status_code == 200 and kept.json()["hidden_at"] is None
    assert client.get(f"{P}/posts/{pid}").json()["comments"] == 1
    late = _person(client, "late@example.com", "Late")
    client.post(f"{P}/comments/{cid}/report", json={"reason": "spam"}, headers=late)
    assert client.get(f"{P}/posts/{pid}").json()["comments"] == 1  # cleared: stays up

    # Admins ban: signed out, comments hidden.
    account_id = kept.json()["account_id"]
    ban = client.post(f"/api/v1/moderation/accounts/{account_id}/ban",
                      json={"reason": "Repeated false claims"}, headers=admin)  # fmt: skip
    assert ban.status_code == 204
    assert client.get(f"{P}/auth/me", headers=rina).status_code == 401
    assert client.get(f"{P}/posts/{pid}").json()["comments"] == 0
    login = client.post(f"{P}/auth/login", json={"email": "rina@example.com",
                                                 "password": "correct horse"})  # fmt: skip
    assert login.status_code == 401 and "banned" in login.json()["detail"]
    assert client.post(f"/api/v1/moderation/accounts/{account_id}/ban", json={"reason": "x" * 5},
                       headers=official).status_code == 403  # fmt: skip


def test_deleting_an_account_removes_what_it_did(client, setup, post):
    rina = _person(client)
    pid = post["id"]
    client.put(f"{P}/posts/{pid}/like", headers=rina)
    client.post(f"{P}/posts/{pid}/comments", json={"body": "A comment to go"}, headers=rina)
    wrong = client.post(f"{P}/auth/delete", json={"password": "nope"}, headers=rina)
    assert wrong.status_code == 422
    assert client.post(f"{P}/auth/delete", json={"password": "correct horse"},
                       headers=rina).status_code == 204  # fmt: skip
    after = client.get(f"{P}/posts/{pid}").json()
    assert (after["likes"], after["comments"]) == (0, 0)
    assert client.get(f"{P}/auth/me", headers=rina).status_code == 401


def test_suspended_pages_disappear(client, setup, post):
    client.post(f"/api/v1/official-pages/{setup['page']['id']}/suspend",
                json={"reason": "Paused at the office's request"},
                headers=setup["h"]["admin"])  # fmt: skip
    assert client.get(f"{P}/posts").json() == []
    assert client.get(f"{P}/posts/{post['id']}").status_code == 404
    assert client.get(f"{P}/pages/ddm").status_code == 404
    assert client.get(f"{P}/incidents/{setup['event'].id}").status_code == 404
