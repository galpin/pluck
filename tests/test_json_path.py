from pluck._json import JsonPath


def test_new():
    expected = JsonPath("a", "b", "c")
    actual = JsonPath(*expected)
    assert actual == expected


def test_add():
    expected = JsonPath("a", "b", "c", "d")
    actual = JsonPath("a", "b").add("c", "d")
    assert actual is not expected
    assert actual == expected
