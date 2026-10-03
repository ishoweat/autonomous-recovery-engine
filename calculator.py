# Contents for calculator.py
# File loaded from Sahil707-pop/autonomous-recovery-engine


def calculate_average(numbers):
    if not numbers:
        return 0.0
    total = sum(numbers)
    return total / len(numbers)