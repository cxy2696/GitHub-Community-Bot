from __future__ import annotations

from github_community_bot.logging_setup import redact
from github_community_bot.metrics import Metrics


def test_metrics_render_and_labels():
    metrics = Metrics()
    metrics.inc("messages_total", platform="discord")
    metrics.inc("messages_total", platform="discord")
    metrics.inc("messages_total", platform="telegram")
    metrics.set_gauge("queue_depth", 2)
    rendered = metrics.render()
    assert 'messages_total{platform="discord"} 2' in rendered
    assert 'messages_total{platform="telegram"} 1' in rendered
    assert "queue_depth 2" in rendered
    assert "bot_uptime_seconds" in rendered
    assert metrics.get_counter("messages_total", platform="discord") == 2


def test_redaction():
    cases = [
        "token=ghp_abcdefghijklmnopqrstuvwxyz123456",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "xoxb-123456789012-abcdefghijkl",
        "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
    ]
    for value in cases:
        assert "ghp_" not in redact(value)
        assert "xoxb-" not in redact(value)
        assert "AAHdq" not in redact(value)
    assert redact("ordinary log line") == "ordinary log line"
