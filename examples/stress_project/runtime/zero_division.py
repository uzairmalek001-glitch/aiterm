"""Case 31: zero_division (valid syntax; crashes when run)"""

def helper_31_sum(values):
    """Sum numbers, skipping None."""
    total = 0
    for v in values:
        if v is not None:
            total += v
    return total


def helper_31_stats(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(clean), "max": max(clean), "mean": sum(clean) / len(clean)}


class Box31:
    def __init__(self, items=None):
        self.items = list(items or [])

    def add(self, item):
        self.items.append(item)
        return self

    def total(self):
        return helper_31_sum(self.items)



def avg(xs):
    return sum(xs) / len(xs)

print(avg([]))
