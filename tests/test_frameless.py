def test_when_response_contains_data(ctx):
    expected_data = {"launches": [{"id": "1"}]}
    ctx.setup_response(data=expected_data)

    actual = ctx.read_graphql("{ launches { id } }")

    assert actual.frames is None
    assert actual.data == expected_data
    assert actual.errors is None


def test_when_response_contains_errors(ctx):
    expected_errors = ["error 1"]
    ctx.setup_response(errors=expected_errors)

    actual = ctx.read_graphql("{ launches { id } }")

    assert actual.frames is None
    assert actual.data is None
    assert actual.errors == expected_errors


def test_when_response_contains_data_and_errors(ctx):
    expected_data = {"launches": [{"id": "1"}]}
    expected_errors = ["error 1"]
    ctx.setup_response(data=expected_data, errors=expected_errors)

    actual = ctx.read_graphql("{ launches { id } }")

    assert actual.frames is None
    assert actual.data == expected_data
    assert actual.errors == expected_errors
