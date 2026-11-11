from __future__ import annotations

from github_community_bot.platforms.base import chunk_text


def test_chunk_text_short():
    assert chunk_text("hello", 20) == ["hello"]


def test_chunk_text_respects_boundaries_and_keeps_all_words():
    text = "word " * 50
    chunks = chunk_text(text, 40)
    assert all(len(chunk) <= 40 for chunk in chunks)
    assert " ".join(chunks).split() == text.split()


def test_chunk_text_hard_split_long_word():
    chunks = chunk_text("x" * 25, 10)
    assert "".join(chunks) == "x" * 25
    assert all(len(chunk) <= 10 for chunk in chunks)


def test_chunk_text_rejects_bad_limit():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("hello", 0)
