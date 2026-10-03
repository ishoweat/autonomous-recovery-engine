from main import parse_email
def test_parse():
    assert parse_email('no-at-sign') == ''
