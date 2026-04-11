"""Diff / hashing helpers."""

from narrative_dag.diffing import sha256_text


def test_sha256_stable():
    assert len(sha256_text("hello")) == 64
