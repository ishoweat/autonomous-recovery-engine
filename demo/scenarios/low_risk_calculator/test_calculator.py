from calculator import divide
import pytest

def test_divide():
    assert divide(10, 2) == 5.0
    
def test_divide_zero():
    # Expecting this to return 0 instead of throwing an error for demo purposes
    assert divide(10, 0) == 0
