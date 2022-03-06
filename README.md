
# Pluck 🚀 🍊

![PyPI](https://img.shields.io/pypi/v/pluck-graphql) ![GitHub](https://img.shields.io/github/license/galpin/pluck)

Pluck is a GraphQL client that transforms queries into Pandas data-frames.

## Installation

Install Pluck from [PyPi](https://pypi.org/project/pluck-graphql/):

```bash
pip install pluck-graphql
```

## Introduction

The easiest way to get started is to use `pluck.read_graphql` to execute a query.

Let's read the first five SpaceX launches into a data-frame:


```python
import pluck

SpaceX = "https://api.spacex.land/graphql"

query = """
{
  launches(limit: 5) {
    mission_name
    launch_date_local
    rocket {
      rocket_name
    }
  }
}
"""
frame, = pluck.read_graphql(query, url=SpaceX)
frame
```

| launches.mission_name   | launches.launch_date_local   | launches.rocket.rocket_name   |
|:------------------------|:-----------------------------|:------------------------------|
| Thaicom 6           | 2014-01-06T14:06:00-04:00| Falcon 9                  |
| AsiaSat 6           | 2014-09-07T01:00:00-04:00| Falcon 9                  |
| OG-2 Mission 2      | 2015-12-22T21:29:00-04:00| Falcon 9                  |
| FalconSat           | 2006-03-25T10:30:00+12:00| Falcon 1                  |
| CRS-1               | 2012-10-08T20:35:00-04:00| Falcon 9                  |


### Implicit Mode

The query above uses _implicit mode_. This is where the entire response is normalized into a single data-frame and the nested fields are separated by a period.

The return value from `read_graphql` is an instance of `PluckResponse`. This object is _iterable_ and enumerates the data-frames in the query. Because this query uses _implicit mode_, the iterator contains only a single data-frame (note that the trailing comma is still required).

### @frame directive

But Pluck is more powerful than _implicit mode_ because it provides a custom `@frame` directive.

The `@frame` directive specifies portions of the GraphQL response that we want to transform into data-frames. The directive is removed before the query is sent to the GraphQL server.

Using the same query, rather than use implicit mode, let's pluck the `launches` field from the response:


```python
query = """
{
  launches(limit: 5) @frame {
    mission_name
    launch_date_local
    rocket {
      rocket_name
    }
  }
}
"""
launches, = pluck.read_graphql(query, url=SpaceX)
launches
```

| mission_name   | launch_date_local     | rocket.rocket_name   |
|:---------------|:--------------------------|:---------------------|
| Thaicom 6  | 2014-01-06T14:06:00-04:00 | Falcon 9         |
| AsiaSat 6  | 2014-09-07T01:00:00-04:00 | Falcon 9         |
| OG-2 Mission 2 | 2015-12-22T21:29:00-04:00 | Falcon 9         |
| FalconSat  | 2006-03-25T10:30:00+12:00 | Falcon 1         |
| CRS-1      | 2012-10-08T20:35:00-04:00 | Falcon 9         |


The column names are no longer prefixed with `launches` because it is now the root of the data-frame.

### Multiple @frame directives

We can also pluck multiple data-frames from the a single GraphQL query.

Let's query the first five SpaceX `rockets` as well: 


```python
query = """
{
  launches(limit: 5) @frame {
    mission_name
    launch_date_local
    rocket {
      rocket_name
    }
  }
  rockets(limit: 5) @frame {
    name
    type
    company
    height {
      meters
    }
    mass {
      kg
    }
  }
}
"""
launches, rockets = pluck.read_graphql(query, url=SpaceX)
```

Now we have the original `launches` and a new `rockets` data-frame:


```python
rockets
```

| name     | type   | company   |   height.meters |   mass.kg |
|:-------------|:-------|:----------|----------------:|----------:|
| Falcon 1 | rocket | SpaceX|           22.25 |     30146 |
| Falcon 9 | rocket | SpaceX|           70|   