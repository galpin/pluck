import pytest

from pluck import PluckError


def test_when_contains_data(ctx):
    expected = {"launches": [{"id": "1"}]}
    ctx.setup_response(data=expected)

    actual = ctx.read_graphql(
        query="{ launches { id } }",
    )

    assert actual.data == expected
    assert actual.errors is None


def test_when_contains_errors(ctx):
    expected = ["error 1"]
    ctx.setup_response(data=None, errors=expected)

    actual = ctx.read_graphql(
        query="{ launches { id } }",
    )

    assert actual.data is None
    assert actual.errors == expected


def test_when_contains_data_and_errors(ctx):
    expected_data = {"launches": [{"id": "1"}]}
    expected_errors = ["error 1"]
    ctx.setup_response(data=expected_data, errors=expected_errors)

    actual = ctx.read_graphql(
        query="{ launches { id } }",
    )

    assert actual.data == expected_data
    assert actual.errors == expected_errors


def test_when_contains_no_data_and_no_errors(ctx):
    ctx.setup_response(data=None, errors=None)

    with pytest.raises(PluckError):
        ctx.read_graphql(
            query="{ launches { id } }",
        )


def test_when_body_is_null(ctx):
    ctx.setup_response(body=None)

    with pytest.raises(PluckError):
        ctx.read_graphql(
            query="{ launches { id } }",
        )
