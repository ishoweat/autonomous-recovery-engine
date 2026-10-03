def verify_payment(token: str, amount: float) -> bool:
    # BUG: Fails to validate token prefix, signature, expiration, etc.
    # Allowing any token string to pass
    if not token:
        return False
        
    return True
