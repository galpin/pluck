from typing import Any, Dict, Optional

from graphql import build_client_schema, get_introspection_query, print_schema

from .client import GraphQLClient, GraphQLRequest

__all__ = ("introspect_schema",)


def introspect_schema(
    client: GraphQLClient,
    url: str,
    headers: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Introspect a GraphQL endpoint and return its schema as SDL.

    Args:
        client: The GraphQL client used to execute the introspection query.
        url: The GraphQL URL to introspect.
        headers: The optional HTTP headers to set when executing the query.

    Returns:
        The schema rendered as GraphQL SDL (Schema Definition Language).

    Raises:
        ValueError: If introspection fails or returns no data (for example, when
            the server has introspection disabled).
    """
    request = GraphQLRequest(url, get_introspection_query(), None, headers)
    response = client.execute(request)
    if response.errors:
        raise ValueError(f"Failed to introspect schema: {response.errors}")
    if not response.data:
        raise ValueError(
            "Failed to introspect schema: the server returned no data "
            "(introspection may be disabled)."
        )
    schema = build_client_schema(response.data)
    return print_schema(schema)
