from auth import verify
def test_verify():
    assert verify(None) == False
