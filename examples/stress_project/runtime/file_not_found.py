"""Case 38: file_not_found (valid syntax; crashes when run)"""

def helper_38_sum(values):
    """Sum numbers, skipping None."""
    total = 0
    for v in values:
        if v is not None:
            total += v
    return total


def helper_38_stats(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(clean), "max": max(clean), "mean": sum(clean) / len(clean)}


class Box38:
    def __init__(self, items=None):
        self.items = list(items or [])

    def add(self, item):
        self.items.append(item)
        return self

    def total(self):
        return helper_38_sum(self.items)



open('/nonexistent/path/file.txt').read()
