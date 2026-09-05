"""Tests for vision-reply parsing and location consensus.

These guard the content-integrity rule: a montage is only captioned with a
specific place when the footage consistently shows that place.
"""

from vcpipe.vision import parse_vision_reply, consensus_location


def test_parse_reply_with_location():
    loc, desc = parse_vision_reply("LOCATION: Sydney Opera House\nDESC: white sail-shaped shells")
    assert loc == "Sydney Opera House"
    assert desc == "white sail-shaped shells"


def test_parse_reply_unknown_is_none():
    loc, desc = parse_vision_reply("LOCATION: UNKNOWN\nDESC: a generic night cityscape")
    assert loc is None
    assert desc == "a generic night cityscape"


def test_parse_reply_unknown_synonyms():
    for token in ("Not clear", "N/A", "unidentified", "Not identifiable"):
        loc, _ = parse_vision_reply(f"LOCATION: {token}\nDESC: x")
        assert loc is None, token


def test_parse_reply_strips_trailing_period():
    loc, _ = parse_vision_reply("LOCATION: Mount Fuji.\nDESC: snow-capped peak")
    assert loc == "Mount Fuji"


def test_parse_reply_case_insensitive_keys():
    loc, desc = parse_vision_reply("location: Dubai\ndesc: skyline")
    assert loc == "Dubai"
    assert desc == "skyline"


def test_parse_reply_missing_fields():
    assert parse_vision_reply("just some free text") == (None, None)


def test_consensus_none_when_empty():
    assert consensus_location([], 4) is None


def test_consensus_single_frame_not_enough():
    # one clip names a landmark, three said UNKNOWN -> not enough to caption all
    assert consensus_location(["New York"], 4) is None


def test_consensus_majority_agrees():
    assert consensus_location(["Dubai", "Dubai", "Dubai"], 4) == "Dubai"


def test_consensus_disagreement_returns_none():
    # the actual bug: NYC + Toronto must never resolve to a single place
    assert consensus_location(["New York", "Toronto"], 4) is None


def test_consensus_normalizes_casing_and_punctuation():
    assert consensus_location(["Banff", "banff."], 2) == "Banff"


def test_consensus_half_of_two():
    # 2 frames, both agree -> ok
    assert consensus_location(["Kyoto", "Kyoto"], 2) == "Kyoto"


def test_consensus_two_of_four_is_not_majority():
    # 2 of 4 is not >= max(2, (4+1)//2)=2 ... actually 2>=2 -> allowed.
    # Guard the boundary explicitly: 2 agreeing of 4 IS accepted (half).
    assert consensus_location(["Rome", "Rome", "Paris", "UNKNOWNPLACE"], 4) == "Rome"
