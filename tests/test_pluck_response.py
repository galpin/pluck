# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import pytest
from pandas import DataFrame

from pluck import PluckResponse, GraphQLError


def test_init():
    expected_data = {"launch": {"id": "1"}}
    expected_errors = ["Error 1"]
    expected_frames = {"launch": DataFrame({"id": ["1"]})}

    sut = PluckResponse(
        data=expected_data,
        errors=expected_errors,
        frames=expected_frames,
    )

    assert sut.data is expected_data
    assert sut.errors is expected_errors
    assert sut.frames is expected_frames


def test_init_when_frameless():
    expected_frames = {}

    sut = PluckResponse(data=None, errors=None, frames=expected_frames)

    assert sut.data is None
    assert sut.errors is None
    assert sut.frames is expected_frames


def test_raise_for_errors():
    errors = [
        "Error 1",
        "Error 2",
        "Error 3",
    ]
    expected = (
        "The GraphQL response contained 3 errors:\n"
        "- Error 1\n"
        "- Error 2\n"
        "- Error 3"
    )
    sut = PluckResponse(data=None, errors=errors, frames={})

    with pytest.raises(GraphQLError) as excinfo:
        sut.raise_for_errors()

    assert str(excinfo.value) == expected


def test_iter_returns_frames():
    frames = {
        "launch": DataFrame({"id": ["1"]}),
        "mission": DataFrame({"id": ["2"]}),
    }
    sut = PluckResponse(data=None, errors=None, frames=frames)

    actual = iter(sut)

    assert next(actual) is frames["launch"]
    assert next(actual) is frames["mission"]
    with pytest.raises(StopIteration):
        next(actual)


def test_iter_when_query_was_frameless():
    sut = PluckResponse(data=None, errors=None, frames={})
    with pytest.raises(AssertionError):
        iter(sut)
