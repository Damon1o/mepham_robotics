"""The two public proxy endpoints: both spend money upstream, so both are capped."""
import time

import pytest

import api.index as app_module


@pytest.fixture(autouse=True)
def _chat_key(monkeypatch):
    monkeypatch.setenv('CHATBOT_API_KEY', 'test-key')


@pytest.fixture
def fake_upstream(monkeypatch):
    calls = []

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content': 'Beep boop.'}}]}

    def _post(url, **kwargs):
        calls.append(kwargs)
        return Resp()

    monkeypatch.setattr(app_module.requests, 'post', _post)
    return calls


def test_chat_relays_the_reply(client, fake_upstream):
    resp = client.post('/api/chat', json={'message': 'hello'})
    assert resp.status_code == 200
    assert resp.get_json()['reply'] == 'Beep boop.'


def test_chat_always_sets_a_timeout(client, fake_upstream):
    client.post('/api/chat', json={'message': 'hello'})
    assert fake_upstream[0]['timeout'] == app_module.CHAT_TIMEOUT_SECONDS


def test_chat_rejects_empty_message(client, fake_upstream):
    assert client.post('/api/chat', json={'message': '   '}).status_code == 400
    assert not fake_upstream


def test_chat_rejects_oversized_message(client, fake_upstream):
    resp = client.post('/api/chat',
                       json={'message': 'x' * (app_module.CHAT_MESSAGE_MAX + 1)})
    assert resp.status_code == 400
    assert not fake_upstream


def test_chat_is_rate_limited(client, fake_upstream):
    for _ in range(app_module.CHAT_RATE_LIMIT):
        assert client.post('/api/chat', json={'message': 'hi'}).status_code == 200
    resp = client.post('/api/chat', json={'message': 'hi'})
    assert resp.status_code == 429
    assert len(fake_upstream) == app_module.CHAT_RATE_LIMIT


def test_chat_reports_offline_without_a_key(client, monkeypatch, fake_upstream):
    monkeypatch.delenv('CHATBOT_API_KEY', raising=False)
    assert client.post('/api/chat', json={'message': 'hi'}).status_code == 503
    assert not fake_upstream


def test_chat_upstream_failure_is_not_a_500(client, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError('upstream down')

    monkeypatch.setattr(app_module.requests, 'post', _boom)
    assert client.post('/api/chat', json={'message': 'hi'}).status_code == 502


def test_matches_are_empty_without_a_key(client, monkeypatch):
    monkeypatch.delenv('ROBOTEVENTS_API_KEY', raising=False)
    app_module._matches_cache.update(expires_at=0.0, payload=None)
    assert client.get('/api/matches').get_json() == {'matches': []}


def test_matches_are_cached(client, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    app_module._matches_cache.update(expires_at=0.0, payload=None)
    calls = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {'data': []}

    monkeypatch.setattr(app_module.requests, 'get',
                        lambda url, **k: (calls.append(url), Resp())[1])

    client.get('/api/matches')
    upstream_calls = len(calls)
    assert upstream_calls > 0

    client.get('/api/matches')
    assert len(calls) == upstream_calls, 'second request should be served from cache'
    assert app_module._matches_cache['expires_at'] > time.time()
