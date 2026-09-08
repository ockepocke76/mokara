"""Tests for the read-only public endpoints (category-scoped leaderboard)."""
import os

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def test_leaderboard_meta_is_category_scoped():
    r = client.get("/leaderboard/meta", headers=SECRET)
    assert r.status_code == 200
    body = r.json()
    keys = [c["key"] for c in body["categories"]]
    assert keys == ["CONTRIBUTION_ONLY", "WITHDRAWAL_ONLY", "HYBRID"]
    assert body["default_category"] == "WITHDRAWAL_ONLY"
    # Profiles cascade per category
    wd = body["profiles_by_category"]["WITHDRAWAL_ONLY"]
    assert any(p["key"] == "conservative" for p in wd)
    assert not any(p["key"] == "aggressive_growth" for p in wd)
    acc = body["profiles_by_category"]["CONTRIBUTION_ONLY"]
    assert any(p["key"] == "aggressive_growth" for p in acc)
    # Every profile ships weights with metric names
    assert all(p["weights"] and p["weights"][0]["name"] for p in wd)
    # Per-category evaluation docs
    assert "score_components_markdown" in body["evaluation_info"]["HYBRID"]


def test_leaderboard_defaults_profile_to_category_balanced():
    r = client.get("/leaderboard?category=WITHDRAWAL_ONLY", headers=SECRET)
    assert r.status_code == 200
    body = r.json()
    assert body["profile"] == "balanced_withdrawal"
    assert body["profile_is_balanced"] is True
    scores = [e["score"] or 0 for e in body["entries"]]
    assert scores == sorted(scores, reverse=True)
    for i, e in enumerate(body["entries"], start=1):
        assert e["rank"] == i
        assert e["category"] == "WITHDRAWAL_ONLY"
        assert "metric_grid" in e and "scenario_results" in e and "badge" in e


def test_leaderboard_rejects_unknown_category():
    assert (
        client.get("/leaderboard?category=NOPE", headers=SECRET).status_code
        == 422
    )


def test_leaderboard_cross_category_profile_falls_back():
    # A profile from another category is replaced by the category's balanced one
    r = client.get(
        "/leaderboard?category=WITHDRAWAL_ONLY&profile=aggressive_growth",
        headers=SECRET,
    )
    assert r.status_code == 200
    assert r.json()["profile"] == "balanced_withdrawal"


def test_leaderboard_clone_requires_auth():
    r = client.post("/leaderboard/999999/clone", headers=SECRET)
    assert r.status_code == 401


def test_community_stats_and_beta_status():
    r = client.get("/community-stats", headers=SECRET)
    assert r.status_code == 200
    for key in ("total_simulations", "total_strategies", "top_strategies"):
        assert key in r.json()

    r = client.get("/beta-status", headers=SECRET)
    assert r.status_code == 200
    assert "is_full" in r.json()


def test_public_requires_internal_secret():
    for path in ("/leaderboard", "/community-stats", "/beta-status"):
        assert client.get(path).status_code == 401
