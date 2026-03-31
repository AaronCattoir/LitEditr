"""API tests: quick-coach (sparkle) and bookmark session restore."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from narrative_dag.api import app as app_module
from narrative_dag.db import init_db
from narrative_dag.schemas import (
    CharacterDatabase,
    CharacterEntry,
    Chunk,
    DocumentState,
    GenreIntention,
    PlotOverview,
)
from narrative_dag.store.run_store import RunStore, serialize_story_wide_for_api


def _reset_app_singletons() -> None:
    app_module._service = None
    app_module._job_store = None


@pytest.fixture
def suppress_analyze_job(monkeypatch):
    """Keep async analyze jobs in `queued` so dedupe tests see an active job."""

    def noop(_job_id: str, _payload: dict) -> None:
        return None

    monkeypatch.setattr("narrative_dag.api.app._run_analyze_job", noop)


def _client_for_db(monkeypatch, db_path: str) -> TestClient:
    monkeypatch.setattr("narrative_dag.config.DEFAULT_DB_PATH", db_path)
    # New DB path must clear cached service/job store from prior tests.
    _reset_app_singletons()
    init_db(db_path)
    from narrative_dag.api.app import app

    return TestClient(app)


@pytest.fixture
def client_isolated(monkeypatch, tmp_path):
    db_path = str(tmp_path / "api.sqlite")
    return _client_for_db(monkeypatch, db_path)


def _seed_run_with_chunk(conn, document_id: str, revision_id: str, run_id: str, chunk_id: str) -> None:
    rs = RunStore(conn)
    rs.save_run_meta(
        run_id,
        genre="literary_fiction",
        title="T",
        author="A",
        document_id=document_id,
        revision_id=revision_id,
    )
    ds = DocumentState(
        plot_overview=PlotOverview(story_point="A story", plot_summary="Summary here."),
        character_database=CharacterDatabase(characters=[CharacterEntry(canonical_name="Alex")]),
    )
    rs.save_document_state(run_id, ds)
    ch = Chunk(id=chunk_id, text="Paragraph one.", position=0, start_char=0, end_char=14)
    artifact = {
        "target_chunk": ch.model_dump(),
        "context_window": {
            "target_chunk": ch.model_dump(),
            "previous_chunks": [],
            "next_chunks": [],
            "global_summary": "",
        },
        "detector_results": {},
        "critic_result": None,
        "defense_result": None,
        "current_judgment": None,
    }
    rs.save_chunk_artifact(run_id, chunk_id, 0, artifact)


def test_runtime_providers_endpoint(client_isolated):
    r = client_isolated.get("/v1/runtime/providers")
    assert r.status_code == 200
    data = r.json()
    assert data.get("default_provider") in ("openai", "gemini")
    provs = data.get("providers") or []
    assert len(provs) == 2
    ids = {p["id"] for p in provs}
    assert ids == {"openai", "gemini"}
    for p in provs:
        assert "configured" in p and isinstance(p["configured"], bool)
        assert "models" in p and "fast" in p["models"] and "pro" in p["models"]


def test_quick_coach_202_when_no_map_and_dedupes(client_isolated, suppress_analyze_job):
    r = client_isolated.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]
    r = client_isolated.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Hello world.\n\nSecond."})
    rev_id = r.json()["revision_id"]
    p = {"chunk_id": "c1", "genre": "literary_fiction"}
    r1 = client_isolated.post(f"/v1/revisions/{rev_id}/quick-coach", json=p)
    assert r1.status_code == 202
    j1 = r1.json()
    assert "job_id" in j1
    assert j1.get("reason") == "full_analysis_required"
    r2 = client_isolated.post(f"/v1/revisions/{rev_id}/quick-coach", json=p)
    assert r2.status_code == 202
    j2 = r2.json()
    assert j2["job_id"] == j1["job_id"]
    assert j2.get("reason") == "full_analysis_already_queued"


def test_analyze_dedupes_same_as_quick_coach(client_isolated, suppress_analyze_job):
    r = client_isolated.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]
    r = client_isolated.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Body."})
    rev_id = r.json()["revision_id"]
    r1 = client_isolated.post(f"/v1/revisions/{rev_id}/analyze", json={"genre": "literary_fiction"})
    assert r1.status_code == 202
    jid = r1.json()["job_id"]
    r2 = client_isolated.post(f"/v1/revisions/{rev_id}/analyze", json={"genre": "literary_fiction"})
    assert r2.status_code == 202
    assert r2.json()["job_id"] == jid
    assert r2.json().get("reason") == "full_analysis_already_queued"


def test_quick_coach_200_with_story_map(monkeypatch, tmp_path):
    db_path = str(tmp_path / "seed.sqlite")
    client = _client_for_db(monkeypatch, db_path)
    conn = init_db(db_path)
    r = client.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Hello world."})
    rev_id = r.json()["revision_id"]
    _seed_run_with_chunk(conn, doc_id, rev_id, "run-seed", "c1")

    resp = client.post(
        f"/v1/revisions/{rev_id}/quick-coach",
        json={"chunk_id": "c1", "focus": "pacing"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["run_id"] == "run-seed"
    assert data["advice"]["headline"]


def test_quick_coach_422_run_wrong_revision(monkeypatch, tmp_path):
    db_path = str(tmp_path / "seed2.sqlite")
    client = _client_for_db(monkeypatch, db_path)
    conn = init_db(db_path)
    r = client.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "A"})
    rev_id = r.json()["revision_id"]
    _seed_run_with_chunk(conn, doc_id, rev_id, "run-x", "c1")

    bad = client.post(
        f"/v1/revisions/{rev_id}/quick-coach",
        json={"chunk_id": "c1", "run_id": "nonexistent-run"},
    )
    assert bad.status_code == 422


def test_bookmarks_and_restore(monkeypatch, tmp_path):
    db_path = str(tmp_path / "bm.sqlite")
    client = _client_for_db(monkeypatch, db_path)
    conn = init_db(db_path)
    r = client.post("/v1/documents", json={"title": "Doc"})
    doc_id = r.json()["document_id"]
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Story text."})
    rev_id = r.json()["revision_id"]
    _seed_run_with_chunk(conn, doc_id, rev_id, "run-bm", "c1")

    cr = client.post(
        f"/v1/documents/{doc_id}/bookmarks",
        json={"label": "session-a", "revision_id": rev_id, "run_id": "run-bm", "metadata": {"panel": "coach"}},
    )
    assert cr.status_code == 200
    bid = cr.json()["bookmark_id"]

    lr = client.get(f"/v1/documents/{doc_id}/bookmarks")
    assert lr.status_code == 200
    assert len(lr.json()["bookmarks"]) == 1
    assert lr.json()["bookmarks"][0]["label"] == "session-a"

    rest = client.get(f"/v1/bookmarks/{bid}/restore")
    assert rest.status_code == 200
    payload = rest.json()
    assert payload["revision"]["full_text"] == "Story text."
    assert payload["bookmark"]["metadata"]["panel"] == "coach"
    assert payload["run"]["run_id"] == "run-bm"
    assert payload["run"]["has_story_map"] is True

    dr = client.delete(f"/v1/bookmarks/{bid}")
    assert dr.status_code == 200
    lr2 = client.get(f"/v1/documents/{doc_id}/bookmarks")
    assert lr2.json()["bookmarks"] == []


def test_latest_analysis_endpoint_returns_saved_run(monkeypatch, tmp_path):
    db_path = str(tmp_path / "latest.sqlite")
    client = _client_for_db(monkeypatch, db_path)
    conn = init_db(db_path)
    r = client.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Body."})
    rev_id = r.json()["revision_id"]
    _seed_run_with_chunk(conn, doc_id, rev_id, "run-latest", "c1")

    out = client.get(f"/v1/revisions/{rev_id}/latest-analysis")
    assert out.status_code == 200
    payload = out.json()
    assert payload["revision_id"] == rev_id
    assert payload["run_id"] == "run-latest"
    assert payload["report"]["run_id"] == "run-latest"
    assert isinstance(payload["report"]["chunk_judgments"], list)
    rs = RunStore(conn)
    ds = rs.get_document_state("run-latest")
    assert ds is not None
    sw = payload["report"]["story_wide"]
    assert sw == serialize_story_wide_for_api(ds)
    assert sw["plot_overview"]["story_point"] == "A story"
    gi = payload["report"].get("genre_intention")
    assert gi == {
        "genre": "literary_fiction",
        "subgenre_tags": [],
        "tone_descriptors": [],
        "reference_authors": [],
        "short_story_single_chapter": False,
    }


def test_latest_analysis_includes_genre_intention_from_document_state(monkeypatch, tmp_path):
    db_path = str(tmp_path / "latest_gi.sqlite")
    client = _client_for_db(monkeypatch, db_path)
    conn = init_db(db_path)
    r = client.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Body."})
    rev_id = r.json()["revision_id"]
    rs = RunStore(conn)
    rs.save_run_meta(
        "run-gi",
        genre="ignored_when_doc_state_has_intention",
        title="T",
        author="A",
        document_id=doc_id,
        revision_id=rev_id,
    )
    ds = DocumentState(
        genre_intention=GenreIntention(
            genre="science_fiction",
            subgenre_tags=["space_opera"],
            tone_descriptors=["hopeful"],
            reference_authors=["C. L. Moore"],
            short_story_single_chapter=True,
        ),
        plot_overview=PlotOverview(story_point="Stars."),
        character_database=CharacterDatabase(characters=[]),
    )
    rs.save_document_state("run-gi", ds)
    ch = Chunk(id="c1", text="Hi.", position=0, start_char=0, end_char=3)
    rs.save_chunk_artifact(
        "run-gi",
        "c1",
        0,
        {
            "target_chunk": ch.model_dump(),
            "context_window": {
                "target_chunk": ch.model_dump(),
                "previous_chunks": [],
                "next_chunks": [],
                "global_summary": "",
            },
            "detector_results": {},
            "critic_result": None,
            "defense_result": None,
            "current_judgment": None,
        },
    )

    out = client.get(f"/v1/revisions/{rev_id}/latest-analysis")
    assert out.status_code == 200
    gi = out.json()["report"]["genre_intention"]
    assert gi == {
        "genre": "science_fiction",
        "subgenre_tags": ["space_opera"],
        "tone_descriptors": ["hopeful"],
        "reference_authors": ["C. L. Moore"],
        "short_story_single_chapter": True,
    }


def test_latest_analysis_endpoint_does_not_require_story_map(monkeypatch, tmp_path):
    db_path = str(tmp_path / "latest_no_map.sqlite")
    client = _client_for_db(monkeypatch, db_path)
    conn = init_db(db_path)
    rs = RunStore(conn)
    r = client.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Hello."})
    rev_id = r.json()["revision_id"]
    rs.save_run_meta("run-no-map", genre="literary_fiction", document_id=doc_id, revision_id=rev_id)
    ch = Chunk(id="c1", text="Hello.", position=0, start_char=0, end_char=6)
    rs.save_chunk_artifact(
        "run-no-map",
        "c1",
        0,
        {
            "target_chunk": ch.model_dump(),
            "context_window": {
                "target_chunk": ch.model_dump(),
                "previous_chunks": [],
                "next_chunks": [],
                "global_summary": "",
            },
            "detector_results": {},
            "critic_result": None,
            "defense_result": None,
            "current_judgment": None,
        },
    )

    out = client.get(f"/v1/revisions/{rev_id}/latest-analysis")
    assert out.status_code == 200
    payload = out.json()
    assert payload["run_id"] == "run-no-map"
    assert payload["report"]["run_id"] == "run-no-map"
    assert payload["report"]["genre_intention"] == {
        "genre": "literary_fiction",
        "subgenre_tags": [],
        "tone_descriptors": [],
        "reference_authors": [],
        "short_story_single_chapter": False,
    }


def test_latest_analysis_fallback_prefers_document_run_with_story_map(monkeypatch, tmp_path):
    db_path = str(tmp_path / "latest_doc_fallback_story_map.sqlite")
    client = _client_for_db(monkeypatch, db_path)
    conn = init_db(db_path)
    rs = RunStore(conn)

    r = client.post("/v1/documents", json={})
    doc_id = r.json()["document_id"]

    # Older analyzed revision with story-wide document state.
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "Old revision body."})
    old_rev_id = r.json()["revision_id"]
    _seed_run_with_chunk(conn, doc_id, old_rev_id, "run-old-with-map", "c1")

    # New head revision with no run yet -> should fall back to old run with map.
    r = client.post(f"/v1/documents/{doc_id}/revisions", json={"text": "New edited revision body."})
    head_rev_id = r.json()["revision_id"]

    # Add a newer run on the old revision that lacks map/state to ensure map-first preference.
    rs.save_run_meta(
        "run-newer-no-map",
        genre="literary_fiction",
        title="T",
        author="A",
        document_id=doc_id,
        revision_id=old_rev_id,
        analysis_kind="full",
    )
    ch = Chunk(id="c2", text="Newer chunk.", position=0, start_char=0, end_char=11)
    rs.save_chunk_artifact(
        "run-newer-no-map",
        "c2",
        0,
        {
            "target_chunk": ch.model_dump(),
            "context_window": {
                "target_chunk": ch.model_dump(),
                "previous_chunks": [],
                "next_chunks": [],
                "global_summary": "",
            },
            "detector_results": {},
            "critic_result": None,
            "defense_result": None,
            "current_judgment": None,
        },
    )

    out = client.get(f"/v1/revisions/{head_rev_id}/latest-analysis")
    assert out.status_code == 200
    payload = out.json()
    assert payload["from_fallback"] is True
    assert payload["run_id"] == "run-old-with-map"
    assert payload["run_revision_id"] == old_rev_id
    assert payload["report"]["story_wide"] is not None
    assert payload["report"]["story_wide"]["plot_overview"]["story_point"] == "A story"


def test_chapter_crud_and_manuscript(client_isolated):
    r = client_isolated.post("/v1/documents", params={"title": "Doc"})
    assert r.status_code == 200
    doc_id = r.json()["document_id"]

    c1 = client_isolated.post(
        f"/v1/documents/{doc_id}/chapters",
        json={"title": "Chapter One", "sort_order": 0},
    )
    assert c1.status_code == 200
    chapter_id = c1.json()["chapter_id"]

    c2 = client_isolated.post(
        f"/v1/documents/{doc_id}/chapters",
        json={"title": "Chapter Two", "sort_order": 1},
    )
    assert c2.status_code == 200

    listing = client_isolated.get(f"/v1/documents/{doc_id}/chapters")
    assert listing.status_code == 200
    chapters = listing.json()["chapters"]
    assert len(chapters) == 2
    assert chapters[0]["title"] == "Chapter One"
    assert chapters[1]["title"] == "Chapter Two"

    patch = client_isolated.patch(
        f"/v1/chapters/{chapter_id}",
        json={"title": "Chapter 1", "sort_order": 3},
    )
    assert patch.status_code == 200
    assert patch.json()["updated"] is True

    rev = client_isolated.post(
        f"/v1/documents/{doc_id}/revisions",
        json={"text": "<<<EDITR_CHAPTER id=\"a\" title=\"Chapter 1\">>>\nBody."},
    )
    assert rev.status_code == 200
    manuscript = client_isolated.get(f"/v1/documents/{doc_id}/manuscript")
    assert manuscript.status_code == 200
    assert manuscript.json()["current_revision"]["full_text"].startswith("<<<EDITR_CHAPTER")

    delete = client_isolated.delete(f"/v1/chapters/{chapter_id}")
    assert delete.status_code == 200
    listing_after = client_isolated.get(f"/v1/documents/{doc_id}/chapters")
    assert len(listing_after.json()["chapters"]) == 1


def test_analyze_rejects_invalid_client_chunks_422(client_isolated, suppress_analyze_job):
    r = client_isolated.post("/v1/documents")
    doc_id = r.json()["document_id"]
    r = client_isolated.post(
        f"/v1/documents/{doc_id}/revisions",
        json={"text": "abcdef"},
    )
    rev_id = r.json()["revision_id"]

    bad = client_isolated.post(
        f"/v1/revisions/{rev_id}/analyze",
        json={
            "genre": "literary_fiction",
            "chunks": [
                {"chunk_id": "c1", "start_char": 0, "end_char": 3},
                # gap at [3,4) should trigger 422 from pre-enqueue validator
                {"chunk_id": "c2", "start_char": 4, "end_char": 6},
            ],
        },
    )
    assert bad.status_code == 422
