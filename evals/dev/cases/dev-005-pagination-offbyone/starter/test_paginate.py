from paginate import paginate


def test_first_page_returns_first_slice():
    items = list(range(10))
    assert paginate(items, 1, 3) == [0, 1, 2]


def test_second_page_returns_second_slice():
    items = list(range(10))
    assert paginate(items, 2, 3) == [3, 4, 5]
