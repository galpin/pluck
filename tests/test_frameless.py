def test_when_response_contains_data(ctx):
    query = "{ launches { id } }"
    expected_data = {"launches": [{"id": "1"}]}
    ctx.setup_response(data=expected_data)

    actual = ctx.read_graphql(query)

    assert actual.frames is None
    assert actual.data == expected_data
    assert actual.errors is None


def test_when_response_contains_errors(ctx):
    query = "{ launches { id } }"
    expected_errors = ["error 1"]
    ctx.setup_response(errors=expected_errors)

    actual = ctx.read_graphql(query)

    assert actual.frames is None
    assert actual.data is None
    assert actual.errors == expected_errors


def test_when_response_contains_data_and_errors(ctx):
    query = "{ launches { id } }"
    expected_data = {"launches": [{"id": "1"}]}
    expected_errors = ["error 1"]
    ctx.setup_response(data=expected_data, errors=expected_errors)

    actual = ctx.read_graphql(query)

    assert actual.frames is None
    assert actual.data == expected_data
    assert actual.errors == expected_errors
