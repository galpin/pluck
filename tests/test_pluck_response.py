# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import pytest

from pluck import PluckResponse


def test_iter_raises_when_query_was_frameless():
    sut = PluckResponse(data={}, errors=None, frames=None)

    with pytest.raises(AssertionError):
        iter(sut)
