"""Tests for the read-only public endpoints."""
import os

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def test_leaderboard_meta():
    r = client.get("/leaderboard/meta", headers=SECRET)
    assert r.status_code == 200
    body = r.json()
    assert "WITHDRAWAL_ONLY" in body["categories"]
    keys = {p["key"] for p in body["profiles"]}
    assert "conservative" in keys
    assert all(p["name"] for p in body["profiles"])


def test_leaderboard_entries_shape_and_ranking():
    r = client.get("/leaderboard?limit=10", headers=SECRET)
    assert r.status_code == 200
    entries = r.json()["entries"]
    scores = [e["score"] or 0 for e in entries]
    assert scores == sorted(scores, reverse=True)
    for i, e in enumerate(entries, start=1):
        assert e["rank"] == i
        assert "strategy_name" in e and "scores" in e


def test_leaderboard_category_filter():
    r = client.get("/leaderboard?category=WITHDRAWAL_ONLY", headers=SECRET)
    assert r.status_code == 200
    for e in r.json()["entries"]:
        assert e["category"] == "WITHDRAWAL_ONLY"


def test_community_stats_and_beta_status():
    r = client.get("/community-stats", headers=SECRET)
    assert r.status_code == 200
    body = r.json()
    for key in ("total_simulations", "total_strategies", "top_strategies"):
        assert key in body

    r = client.get("/beta-status", headers=SECRET)
    assert r.status_code == 200
    assert "is_full" in r.json()


def test_public_requires_internal_secret():
    for path in ("/leaderboard", "/community-stats", "/beta-status"):
        assert client.get(path).status_code == 401
