# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import pytest

from pluck import PluckResponse, PluckError


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
    sut = PluckResponse(data=None, errors=errors, frames=None)

    with pytest.raises(PluckError) as excinfo:
        sut.raise_for_errors()

    assert str(excinfo.value) == expected


def test_iter_when_query_was_frameless():
    sut = PluckResponse(data=None, errors=None, frames=None)

    with pytest.raises(AssertionError):
        iter(sut)
