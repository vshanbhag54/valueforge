from valueforge import agents


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates":[{"content":{"parts":[{"text":"Evidence review note"}]}}]}


def test_gemini_key_is_sent_in_header_not_url_or_query(monkeypatch):
    calls=[]

    def fake_post(url, **kwargs):
        calls.append((url,kwargs))
        return FakeResponse()

    monkeypatch.setattr(agents.requests,"post",fake_post)
    report,meta=agents.run_ai_committee(
        {"name":"Example Ltd","symbol":"EXAMPLE","exchange":"NSE"},
        api_key="secret-test-key",
        model="gemini-3.5-flash-lite",
    )
    assert meta["agents_run"]==4
    assert len(calls)==5
    assert "secret-test-key" not in report
    for url,kwargs in calls:
        assert "secret-test-key" not in url
        assert kwargs.get("params") is None
        assert kwargs["headers"]["x-goog-api-key"]=="secret-test-key"
        assert kwargs["timeout"]==(10,60)
