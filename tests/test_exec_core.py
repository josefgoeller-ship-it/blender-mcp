"""Unit tests for the JSON-safety half of exec_core, which needs no Blender."""

import exec_core
import pytest


def test_primitives_pass_through():
    assert exec_core.to_jsonable({"n": 1, "f": 1.5, "s": "hi", "b": True, "z": None}) == {
        "n": 1,
        "f": 1.5,
        "s": "hi",
        "b": True,
        "z": None,
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_become_strings_because_json_cannot_spell_them(value):
    assert isinstance(exec_core.to_jsonable(value), str)


def test_sets_and_tuples_become_lists():
    assert sorted(exec_core.to_jsonable({3, 1, 2})) == [1, 2, 3]
    assert exec_core.to_jsonable((1, 2)) == [1, 2]


def test_dict_keys_are_stringified():
    assert exec_core.to_jsonable({1: "a"}) == {"1": "a"}


def test_long_strings_are_clipped_with_a_note():
    clipped = exec_core.to_jsonable("x" * (exec_core.MAX_STRING + 50))
    assert clipped.endswith("more characters]")
    assert len(clipped) < exec_core.MAX_STRING + 100


def test_long_lists_are_truncated():
    result = exec_core.to_jsonable(list(range(exec_core.MAX_ITEMS + 100)))
    assert len(result) == exec_core.MAX_ITEMS


def test_deep_nesting_stops_at_the_depth_limit():
    deep = current = {}
    for _ in range(exec_core.MAX_DEPTH + 5):
        current["next"] = {}
        current = current["next"]
    result = exec_core.to_jsonable(deep)
    depth = 0
    while isinstance(result, dict) and "next" in result:
        result = result["next"]
        depth += 1
    assert depth <= exec_core.MAX_DEPTH


def test_bytes_are_summarised_rather_than_inlined():
    assert exec_core.to_jsonable(b"abcd") == "<4 bytes>"


def test_unknown_objects_fall_back_to_repr():
    class Opaque:
        def __repr__(self):
            return "<opaque thing>"

    assert exec_core.to_jsonable(Opaque()) == "<opaque thing>"


def test_datablock_like_objects_are_summarised_by_name_and_type():
    class FakeRNA:
        identifier = "Object"

    class FakeDatablock:
        bl_rna = FakeRNA()
        name = "Cube"

    assert exec_core.to_jsonable(FakeDatablock()) == {"__blender__": "Object", "name": "Cube"}
