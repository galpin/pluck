# Changes

## 0.5.0
* New: Adds `pluck.ask`, which answers a natural-language question by using an LLM to generate a GraphQL query and then executing it (see README.md for details).

`ask` introspects the target schema, generates a query via a pluggable `QueryGenerator` and executes it through the same pipeline as `execute` (so the `@frame` directive and `column_names` still apply). The generated query is available on the response as `Response.query`.

By default it uses a cheap, single-shot generator (one LLM call, with the query validated against the schema locally and one corrective retry) and escalates to a more robust agentic generator only if the generated query actually fails — a staged fallback that is fast when it works and robust when it doesn't. The `fallback` argument controls or disables the escalation.

The default generators are built on [smolagents](https://github.com/huggingface/smolagents), an optional dependency installed with `pip install "pluck-graphql[llm]"`. Any model supported by smolagents can be used, and the `QueryGenerator` abstraction allows plugging in a completely custom engine.

## 0.4.0
* Fix: Only fields that are within the selection set of the original query are now returned as columns.

This prevents the creation of erroneous columns that were previously added only by virtue of being nested beneath a
branch that was incomplete.

For example, given the following query:

```graphql
{
  launchesPast {
    mission_name
    launch_site {
      site_name_long
    }
  }
}
```

And the following GraphQL response:

```json
{
  "data": {
    "launchesPast": [
        {
            "mission_name": "Launch 1",
            "launch_site": {
              "site_name_long": "Launch Site 1"
            }
        },
        {
            "mission_name": "Launch 2",
            "launch_site": null
        }
    ]
  }
}
```

Previously this would result in a DataFrame with three columns: `mission_name`, `site_name_long` and `launch_site`. 
The `launch_site` column is only present because it is an incomplete branch in the second `launchesPast`.

Now, the DataFrame will correctly provide only the `mission_name` and `site_name_long` columns.

* New: Nested frames are now guaranteed to be returned in the order they appear in the query.

## 0.3.5
* Fix: Ensure rename to short column names is invariant to order!

## 0.3.4
* Breaking Change: Renames `read_graphql` to `execute`!
* New: Adds initial support for transforming column names (see README.md for details).

## 0.2.0
* New: Use `orjson` serialization if the package is installed (otherwise continues to use `json`).
