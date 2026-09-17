def test_login_page_opts_out_of_form_interceptor(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'data-native-submit' in resp.data


def test_login_page_links_to_forgot_password(client):
    resp = client.get('/login')
    assert b'href="/forgot-password"' in resp.data
    assert b'name="remember"' in resp.data
