"""Case 7: unclosed_bracket"""

def helper_7_sum(values):
    """Sum numbers, skipping None."""
    total = 0
    for v in values:
        if v is not None:
            total += v
    return total


def helper_7_stats(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(clean), "max": max(clean), "mean": sum(clean) / len(clean)}


class Box7:
    def __init__(self, items=None):
        self.items = list(items or [])

    def add(self, item):
        self.items.append(item)
        return self

    def total(self):
        return helper_7_sum(self.items)



data = [1, 2, 3
print(data)
