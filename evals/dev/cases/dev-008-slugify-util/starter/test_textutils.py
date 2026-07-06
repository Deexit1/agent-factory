from textutils import shout


def test_shout_uppercases_and_appends_bang():
    assert shout("hello") == "HELLO!"
