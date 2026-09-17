def test_login_page_opts_out_of_form_interceptor(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'data-native-submit' in resp.data
