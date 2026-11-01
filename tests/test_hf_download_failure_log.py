"""SITE-UNSTICK-1e: each failed HF download is logged with its status (429 / timeout / reset); a 429 is routed to
Master's HF STATUS row, anything else retries as now (next poll)."""
import io, os, socket, sys, urllib.error
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import export_panel_cut as epc  # noqa: E402


@pytest.mark.parametrize("exc,status,route", [
    (urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(b"")), "429", "master_hf_status_row"),
    (urllib.error.URLError(socket.timeout("timed out")), "timeout", "retry_next_poll"),
    (socket.timeout("timed out"), "timeout", "retry_next_poll"),
    (ConnectionResetError(104, "Connection reset by peer"), "reset", "retry_next_poll"),
    (urllib.error.HTTPError("u", 503, "Unavailable", {}, io.BytesIO(b"")), "503", "retry_next_poll"),
])
def test_failed_hf_download_logs_status(tmp_path, monkeypatch, exc, status, route):
    log = tmp_path / "data-refresh.log"
    monkeypatch.setenv("REFRESH_LOG", str(log))
    monkeypatch.setenv("HF_READ_TOKEN", "x")

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(epc.urllib.request, "urlopen", boom)
    with pytest.raises(type(exc)):
        epc.hf_get("snapshots/2026-11-01.json.gz")
    line = log.read_text().strip()
    assert f"job=hf_download status=failed http={status} path=snapshots/2026-11-01.json.gz route={route}" in line
