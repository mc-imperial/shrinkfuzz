from hypothesis import assume, given, strategies as st

from shrinkfuzz.shrinker import partition_on, partition_to_string


@given(st.binary(), st.integers(0, 255))
def test_partition_back_to_string(string, b):
    assume(b in string)
    parts = partition_on(string, b)
    assert partition_to_string(string, parts) == string
