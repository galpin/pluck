# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import itertools

import pytest

from pluck._normalization import normalize


def scalars():
    yield (
        "Scalars",
        [
            {
                "str": "s",
            },
            {
                "int": 1,
            },
            {
                "float": 1.1,
            },
            {
                "bool": True,
            },
            {
                "null": None,
            },
        ],
        [
            {"str": "s"},
            {"int": 1},
            {"float": 1.1},
            {"bool": True},
            {"null": None},
        ],
    )


def roots():
    yield (
        "Object as root",
        {
            "a": 1,
        },
        [
            {"a": 1},
        ],
    )
    yield (
        "Array as root",
        [
            {
                "a": 1,
            },
            {
                "a": 2,
            },
        ],
        [
            {"a": 1},
            {"a": 2},
        ],
    )
    yield (
        "Scalar array as root",
        [
            [
                1,
                2,
                3,
            ]
        ],
        [
            {"?": 1},
            {"?": 2},
            {"?": 3},
        ],
    )
    yield (
        "Str as root",
        [
            "s",
        ],
        [
            {"?": "s"},
        ],
    )
    yield (
        "Int as root",
        [
            1,
        ],
        [
            {"?": 1},
        ],
    )
    yield (
        "Float as root",
        [
            1.1,
        ],
        [
            {"?": 1.1},
        ],
    )
    yield (
        "Bool as root",
        [
            False,
        ],
        [
            {"?": False},
        ],
    )
    yield (
        "Null as root",
        [
            None,
        ],
        [{}],
    )


def fields():
    yield (
        "One field",
        {
            "a": 1,
        },
        [
            {"a": 1},
        ],
    )
    yield (
        "Multiple fields",
        {
            "a": 1,
            "b": 2,
        },
        [
            {"a": 1, "b": 2},
        ],
    )
    yield (
        "One nested field",
        {
            "a": 1,
            "b": {
                "c": 2,
            },
        },
        [
            {"a": 1, "b.c": 2},
        ],
    )
    yield (
        "Nested fields",
        {
            "a": 1,
            "b": {
                "c": 2,
            },
            "d": {
                "e": 3,
            },
        },
        [
            {"a": 1, "b.c": 2, "d.e": 3},
        ],
    )
    yield (
        "Two nested fields",
        {
            "a": 1,
            "b": {
                "c": {
                    "d": 2,
                }
            },
        },
        [
            {
                "a": 1,
                "b.c.d": 2,
            },
        ],
    )
    yield (
        "Object fields do not match",
        {
            "a": [
                {"b": 1},
                {"c": 2},
                {"d": 3, "e": 4},
            ],
        },
        [
            {"a.b": 1},
            {"a.c": 2},
            {"a.d": 3, "a.e": 4},
        ],
    )


def dimensions():
    yield (
        "Dimension: one dimension",
        {
            "a": 1,
            "b": [
                {"c": 2},
                {"c": 3},
            ],
        },
        [
            {"a": 1, "b.c": 2},
            {"a": 1, "b.c": 3},
        ],
    )
    yield (
        "Dimension: two dimensions",
        {
            "a": 1,
            "b": [
                {"c": 2},
                {"c": 3},
            ],
            "d": [
                {"e": 4},
                {"e": 5},
            ],
        },
        [
            {"a": 1, "b.c": 2, "d.e": 4},
            {"a": 1, "b.c": 2, "d.e": 5},
            {"a": 1, "b.c": 3, "d.e": 4},
            {"a": 1, "b.c": 3, "d.e": 5},
        ],
    )
    yield (
        "Dimension: nested dimensions",
        {
            "a": 1,
            "b": [
                {
                    "c": [
                        {"e": 4},
                        {"e": 5},
                    ],
                },
            ],
        },
        [
            {"a": 1, "b.c.e": 4},
            {"a": 1, "b.c.e": 5},
        ],
    )
    yield (
        "Dimension: nested two dimensions",
        {
            "a": 1,
            "b": [
                {
                    "c": [
                        {"d": 4},
                        {"d": 5},
                    ],
                    "e": [
                        {"f": 6},
                        {"f": 7},
                    ],
                },
            ],
        },
        [
            {"a": 1, "b.c.d": 4, "b.e.f": 6},
            {"a": 1, "b.c.d": 4, "b.e.f": 7},
            {"a": 1, "b.c.d": 5, "b.e.f": 6},
            {"a": 1, "b.c.d": 5, "b.e.f": 7},
        ],
    )
    yield (
        "Dimension: two dimensions (unbalanced)",
        {
            "a": 1,
            "b": [
                {"c": 2},
                {"c": 3},
            ],
            "d": [
                {"e": 4},
            ],
        },
        [
            {"a": 1, "b.c": 2, "d.e": 4},
            {"a": 1, "b.c": 3, "d.e": 4},
        ],
    )
    yield (
        "Dimension: many dimensions (unbalanced)",
        {
            "a": 1,
            "b": [
                {"c": 2},
                {"c": 3},
            ],
            "d": [
                {"e": 4},
            ],
            "f": [],
            "g": {
                "h": [
                    {"i": 5},
                    {"i": 6},
                    {"i": 7},
                ],
            },
        },
        [
            {"a": 1, "b.c": 2, "d.e": 4, "g.h.i": 5},
            {"a": 1, "b.c": 2, "d.e": 4, "g.h.i": 6},
            {"a": 1, "b.c": 2, "d.e": 4, "g.h.i": 7},
            {"a": 1, "b.c": 3, "d.e": 4, "g.h.i": 5},
            {"a": 1, "b.c": 3, "d.e": 4, "g.h.i": 6},
            {"a": 1, "b.c": 3, "d.e": 4, "g.h.i": 7},
        ],
    )
    yield (
        "Dimension: empty dimension",
        {
            "a": 1,
            "b": [],
        },
        [
            {"a": 1},
        ],
    )
    yield (
        "Dimension: empty dimensions",
        {
            "a": 1,
            "b": [
                {"c": 2},
                {"c": 3},
            ],
            "d": [],
        },
        [
            {"a": 1, "b.c": 2},
            {"a": 1, "b.c": 3},
        ],
    )
    yield (
        "Dimension: scalar dimension",
        {
            "a": 1,
            "b": [
                "s",
                1,
                1.1,
                True,
                None,
            ],
        },
        [
            {"a": 1, "b": "s"},
            {"a": 1, "b": 1},
            {"a": 1, "b": 1.1},
            {"a": 1, "b": True},
        ],
    )
    yield (
        "Dimension: nested dimensions",
        {
            "a": 1,
            "b": [
                [
                    {"c": 2},
                    {"c": 3},
                ],
                [
                    {"d": 4},
                    {"d": 5},
                ],
            ],
        },
        [
            {"a": 1, "b.c": 2},
            {"a": 1, "b.c": 3},
            {"a": 1, "b.d": 4},
            {"a": 1, "b.d": 5},
        ],
    )
    yield (
        "Dimension: multiple nested dimensions (unbalanced)",
        {
            "a": 1,
            "b": [
                [
                    {"c": 2},
                    {"c": 3},
                ],
            ],
            "d": [
                [
                    {"e": 4},
                ],
            ],
        },
        [
            {"a": 1, "b.c": 2, "d.e": 4},
            {"a": 1, "b.c": 3, "d.e": 4},
        ],
    )
    yield (
        "Dimension: empty nested dimensions",
        [
            {
                "a": 1,
                "b": [
                    {"c": 2},
                    {"c": 3},
                ],
                "d": [],
            },
            {
                "a": 1,
                "b": [
                    {"c": 2},
                    {"c": 3},
                ],
                "d": [
                    {"e": 4},
                    {"e": 5},
                    {},
                ],
            },
        ],
        [
            {"a": 1, "b.c": 2},
            {"a": 1, "b.c": 3},
            {"a": 1, "b.c": 2, "d.e": 4},
            {"a": 1, "b.c": 2, "d.e": 5},
            {"a": 1, "b.c": 2},
            {"a": 1, "b.c": 3, "d.e": 4},
            {"a": 1, "b.c": 3, "d.e": 5},
            {"a": 1, "b.c": 3},
        ],
    )
    yield (
        "Dimension: dimension with null",
        [
            {
                "a": 1,
                "b": [
                    {"c": 2},
                    {"c": 3},
                ],
                "d": [None],
            },
            {
                "a": 1,
                "b": [
                    {"c": 2},
                    {"c": 3},
                ],
                "d": [
                    {"e": 4},
                    {"e": 5},
                ],
            },
        ],
        [
            {"a": 1, "b.c": 2},
            {"a": 1, "b.c": 3},
            {"a": 1, "b.c": 2, "d.e": 4},
            {"a": 1, "b.c": 2, "d.e": 5},
            {"a": 1, "b.c": 3, "d.e": 4},
            {"a": 1, "b.c": 3, "d.e": 5},
        ],
    )


@pytest.mark.parametrize(
    "name, obj, expected",
    itertools.chain(
        scalars(),
        roots(),
        fields(),
        dimensions(),
    ),
)
def test_normalize(name, obj, expected):
    actual = normalize(obj)
    assert actual == expected


def test_custom_separator():
    obj = {
        "a": {
            "b": 1,
        }
    }
    actual = normalize(obj, separator="_")
    assert actual == [{"a_b": 1}]


def test_custom_fallback():
    obj = 42
    actual = normalize(obj, fallback="???")
    assert actual == [{"???": 42}]


def test_no_fallback():
    obj = 42
    actual = normalize(obj, fallback=None)
    assert actual == [{"": 42}]
