def paginate(items, page, page_size):
    """Return the slice of items for the given 1-indexed page."""
    start = page * page_size
    end = start + page_size
    return items[start:end]
