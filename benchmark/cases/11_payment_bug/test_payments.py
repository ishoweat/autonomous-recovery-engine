from payments import charge
def test_charge():
    assert charge(-10) == False
