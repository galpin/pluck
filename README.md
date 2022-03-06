
# Pluck 🚀 🍊

![PyPI](https://img.shields.io/pypi/v/pluck-graphql) ![GitHub](https://img.shields.io/github/license/galpin/pluck)

Pluck is a GraphQL client that transforms queries into Pandas data-frames.

## Installation

Install Pluck from PyPi:

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
| Falcon 9 | rocket | SpaceX|           70|    549054 |
| Falcon Heavy | rocket | SpaceX|           70|   1420788 |
| Starship | rocket | SpaceX|          118|   1335000 |


### Lists

When a response includes a list, the data-frame is automatically expanded to include one row per item in the list. This is repeated for every subsequent list in the response.

For example, let's query the first five `capsules` and which missions they have been used for:


```python
query = """
{
  capsules(limit: 5) @frame {
    id
    type
    status
    missions {
      name
    }
  }
}
"""
capsules, = pluck.read_graphql(query, url=SpaceX)
capsules
```

| id   | type   | status| missions.name   |
|:-----|:-----------|:----------|:----------------|
| C105 | Dragon 1.1 | unknown   | CRS-3       |
| C101 | Dragon 1.0 | retired   | COTS 1      |
| C109 | Dragon 1.1 | destroyed | CRS-7       |
| C110 | Dragon 1.1 | active| CRS-8       |
| C110 | Dragon 1.1 | active| CRS-14      |
| C106 | Dragon 1.1 | active| CRS-4       |
| C106 | Dragon 1.1 | active| CRS-11      |
| C106 | Dragon 1.1 | active| CRS-19      |


Rather than five rows, we have seven; each row contains a capsule and a mission.

### Nested @frame directives

Frames can also be nested and if a nested `@frame` is within a list, the rows are combined into a single data-frame.

For example, we can pluck the top five `cores` and their `missions`:


```python
query = """
{
  cores(limit: 5) @frame {
    id
    status
    missions @frame {
      name
      flight
    }
  }
}
"""
cores, missions = pluck.read_graphql(query, url=SpaceX)
```

Now we have the `cores`:


```python
cores
```

| id| status   | missions.name            |   missions.flight |
|:------|:---------|:-----------------------------|------------------:|
| B1015 | lost | CRS-6                    |                22 |
| B0006 | lost | CRS-1                    |                 9 |
| B1034 | lost | Inmarsat-5 F4            |                40 |
| B1016 | lost | TürkmenÄlem 52°E / MonacoSAT |                23 |
| B1025 | inactive | CRS-9                    |                32 |
| B1025 | inactive | Falcon Heavy Test Flight |                55 |


And we also have the `missions` data-frame that has been combined from every item in `cores`:


```python
missions
```

| name                     |   flight |
|:-----------------------------|---------:|
| CRS-6                    |       22 |
| CRS-1                    |        9 |
| Inmarsat-5 F4            |       40 |
| TürkmenÄlem 52°E / MonacoSAT |       23 |
| CRS-9                    |       32 |
| Falcon Heavy Test Flight |       55 |


### Aliases

Column names can be modified using normal GraphQL aliases.

For example, let's tidy-up the field names in the `launches` data-frame:


```python
query = """
{
  launches(limit: 5) @frame {
    mission: mission_name
    launch_date: launch_date_local
    rocket {
      name: rocket_name
    }
  }
}
"""
launches, = pluck.read_graphql(query, url=SpaceX)
launches
```

| mission    | launch_date           | rocket.name   |
|:---------------|:--------------------------|:--------------|
| Thaicom 6  | 2014-01-06T14:06:00-04:00 | Falcon 9  |
| AsiaSat 6  | 2014-09-07T01:00:00-04:00 | Falcon 9  |
| OG-2 Mission 2 | 2015-12-22T21:29:00-04:00 | Falcon 9  |
| FalconSat  | 2006-03-25T10:30:00+12:00 | Falcon 1  |
| CRS-1      | 2012-10-08T20:35:00-04:00 | Falcon 9  |


### Leaf fields

The `@frame` directive can also be used on leaf fields.

For example, we can extract only the name of the mission from past launches:


```python
query = """
{
  launchesPast(limit: 5) {
    mission: mission_name @frame
  }
}
"""
launches, = pluck.read_graphql(query, url=SpaceX)
launches
```

| mission                 |
|:----------------------------|
| Starlink-15 (v1.0)      |
| Sentinel-6 Michael Freilich |
| Crew-1                  |
| GPS III SV04 (Sacagawea)|
   