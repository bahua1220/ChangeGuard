import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from repolens.analytics import frames
from repolens.reports import SummaryError, build_ai_payload, generate_ai_report, summary_key, validate_summary


@pytest.fixture
def payload(snapshot):
    return build_ai_payload(*frames(snapshot))


def valid_result(payload):
    commit = payload["commits"][0]
    return {"highlights": [{"text": "记录了仓库文件变化。", "evidence": [{"commit_hash": commit["commit_hash"], "files": [commit["files"][0]["path"]]}]}], "limitations": ["示例响应，用于接口测试。"]}


def test_rejects_fabricated_commit_and_mismatched_file(payload):
    result = valid_result(payload)
    assert validate_summary(result, payload)["mode"] == "ai"
    wrong = copy.deepcopy(result)
    wrong["highlights"][0]["evidence"][0]["commit_hash"] = "fabricated"
    with pytest.raises(SummaryError, match="提交"):
        validate_summary(wrong, payload)
    wrong = copy.deepcopy(result)
    wrong["highlights"][0]["evidence"][0]["files"] = ["not-in-this-commit.py"]
    with pytest.raises(SummaryError, match="文件"):
        validate_summary(wrong, payload)


@pytest.mark.parametrize("value", [[], {}, {"highlights": []}, {"highlights": [{"text": "no evidence"}]}])
def test_rejects_malformed_or_unsupported_summary(payload, value):
    with pytest.raises(SummaryError):
        validate_summary(value, payload)


def test_cache_tracks_model_and_input(payload):
    key = summary_key(payload, "https://example.test/v1", "model-a")
    assert key != summary_key(payload, "https://example.test/v1", "model-b")
    changed = copy.deepcopy(payload)
    changed["commits"][0]["message"] += "different"
    assert key != summary_key(changed, "https://example.test/v1", "model-a")


@pytest.mark.parametrize("use_ids", [False, True])
def test_real_http_adapter_against_local_fixture(payload, use_ids):
    seen = {}
    expected = valid_result(payload)
    if use_ids:
        expected = {"highlights": [{"text": "记录了仓库文件变化。", "evidence_ids": [payload["commits"][0]["files"][0]["evidence_id"]]}], "limitations": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            response = json.dumps({"choices": [{"message": {"content": json.dumps(expected)}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = generate_ai_report(payload, f"\t http://127.0.0.1:{server.server_port}/v1 \n", " fixture-model ", "")
        assert result["mode"] == "ai"
        assert result["model"] == "fixture-model"
        assert seen["path"] == "/v1/chat/completions"
        assert seen["body"]["response_format"] == {"type": "json_object"}
        if use_ids:
            assert result["highlights"][0]["evidence"] == valid_result(payload)["highlights"][0]["evidence"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_rejects_plaintext_remote_endpoint(payload):
    with pytest.raises(SummaryError, match="HTTPS"):
        generate_ai_report(payload, "http://example.test/v1", "model", "")


def test_evidence_ids_resolve_exact_commit_and_file(payload):
    first = payload["commits"][0]
    ref = first["files"][0]["evidence_id"]
    result = validate_summary({"highlights": [{"text": "有代码变化", "evidence_ids": [ref, ref]}], "limitations": []}, payload)
    assert result["highlights"][0]["evidence"] == [{"commit_hash": first["commit_hash"], "files": [first["files"][0]["path"]]}]
    with pytest.raises(SummaryError, match="依据编号"):
        validate_summary({"highlights": [{"text": "无效引用", "evidence_ids": ["C999F999"]}]}, payload)


def test_internal_control_character_in_api_url_has_friendly_error(payload):
    with pytest.raises(SummaryError, match="API Base URL"):
        generate_ai_report(payload, "https://api.exa\tmple.test/v1", "model", "")
