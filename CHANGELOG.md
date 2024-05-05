# Changes

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
