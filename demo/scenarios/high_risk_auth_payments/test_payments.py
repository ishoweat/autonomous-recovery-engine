from auth.payments import verify_payment

def test_verify_payment_invalid():
    # An invalid token should be rejected
    assert verify_payment("invalid-token", 100.0) == False

def test_verify_payment_valid():
    assert verify_payment("valid-token-sig", 100.0) == True
