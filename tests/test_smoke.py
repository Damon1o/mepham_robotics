def test_login_page_opts_out_of_form_interceptor(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'data-native-submit' in resp.data


def test_login_page_has_no_forgot_password_link(client):
    resp = client.get('/login')
    assert b'href="/forgot-password"' not in resp.data
    assert b'name="remember"' in resp.data
    assert b'contact a team admin' in resp.data.lower()
