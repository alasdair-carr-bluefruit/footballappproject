"""Early-access form endpoint (public, unauthenticated)."""
import backend.api.routers.public as public_mod


def test_early_access_emails_founder(client, monkeypatch):
    calls: list = []
    monkeypatch.setattr(public_mod, "send_early_access_email",
                        lambda email, name, message: calls.append((email, name, message)))
    r = client.post("/api/early-access",
                    json={"email": "coach@example.com", "name": "Sam", "message": "U9s"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert calls == [("coach@example.com", "Sam", "U9s")]


def test_early_access_rejects_bad_email(client, monkeypatch):
    calls: list = []
    monkeypatch.setattr(public_mod, "send_early_access_email",
                        lambda *a: calls.append(a))
    r = client.post("/api/early-access", json={"email": "not-an-email"})
    assert r.status_code == 422
    assert calls == []  # never attempted a send


def test_early_access_honeypot_is_dropped(client, monkeypatch):
    calls: list = []
    monkeypatch.setattr(public_mod, "send_early_access_email",
                        lambda *a: calls.append(a))
    r = client.post("/api/early-access",
                    json={"email": "bot@example.com", "website": "http://spam"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert calls == []  # honeypot tripped → silently dropped, no email


def test_early_access_send_failure_surfaces_502(client, monkeypatch):
    def boom(*a):
        raise RuntimeError("resend down")
    monkeypatch.setattr(public_mod, "send_early_access_email", boom)
    r = client.post("/api/early-access", json={"email": "coach@example.com"})
    assert r.status_code == 502
