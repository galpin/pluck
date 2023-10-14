
# Pluck 🚀 🍊

![PyPI](https://img.shields.io/pypi/v/pluck-graphql) ![GitHub](https://img.shields.io/github/license/galpin/pluck)

Pluck is a GraphQL client that transforms queries into Pandas data-frames.

## Installation

Install Pluck from [PyPi](https://pypi.org/project/pluck-graphql/):

```bash
pip install pluck-graphql
```

## Introduction

The easiest way to get started is to use `pluck.execute` to execute a query.

Let's read the first five SpaceX launches into a data-frame:


```python
import pluck

SpaceX = "https://main--spacex-l4uc6p.apollographos.net/graphql"

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
frame, = pluck.execute(query, url=SpaceX)
frame
```

| launches.mission_name   | launches.launch_date_local   | launches.rocket.rocket_name   |
|:------------------------|:-----------------------------|:------------------------------|
| FalconSat           | 2006-03-25T10:30:00+12:00| Falcon 1                  |
| DemoSat             | 2007-03-21T13:10:00+12:00| Falcon 1                  |
| Trailblazer         | 2008-08-03T15:34:00+12:00| Falcon 1                  |
| RatSat              | 2008-09-28T11:15:00+12:00| Falcon 1                  |
| RazakSat            | 2009-07-13T15:35:00+12:00| Falcon 1                  |


### Implicit Mode

The query above uses _implicit mode_. This is where the entire response is normalized into a single data-frame.

The return value from `execute` is an instance of `pluck.Response`. This object is _iterable_ and enumerates the data-frames in the query. Because this query uses _implicit mode_, the iterator contains only a single data-frame (note that the trailing comma is still required).

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
launches, = pluck.execute(query, url=SpaceX)
launches
```

| mission_name   | launch_date_local     | rocket.rocket_name   |
|:---------------|:--------------------------|:---------------------|
| FalconSat  | 2006-03-25T10:30:00+12:00 | Falcon 1         |
| DemoSat    | 2007-03-21T13:10:00+12:00 | Falcon 1         |
| Trailblazer| 2008-08-03T15:34:00+12:00 | Falcon 1         |
| RatSat     | 2008-09-28T11:15:00+12:00 | Falcon 1         |
| RazakSat   | 2009-07-13T15:35:00+12:00 | Falcon 1         |


The column names are no longer prefixed with `launches` because it is now the root of the data-frame.

### Multiple @frame directives

We can also pluck multiple data-frames from a single GraphQL query.

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
launches, rockets = pluck.execute(query, url=SpaceX)
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

For example, let's query the first five `rockets` and their `payload_weights`:


```python
query = """
{
  rockets(limit: 5) @frame {
    id
    type
    name
    payload_weights {
      name
      kg
    }
  }
}
"""
rockets, = pluck.execute(query, url=SpaceX)
rockets
```

| id                   | type   | name     | payload_weights.name      |   payload_weights.kg |
|:-------------------------|:-------|:-------------|:------------------------------|---------------------:|
| 5e9d0d95eda69955f709d1eb | rocket | Falcon 1 | Low Earth Orbit           |                  450 |
| 5e9d0d95eda69973a809d1ec | rocket | Falcon 9 | Low Earth Orbit           |                22800 |
| 5e9d0d95eda69973a809d1ec | rocket | Falcon 9 | Geosynchronous Transfer Orbit |                 8300 |
| 5e9d0d95eda69973a809d1ec | rocket | Falcon 9 | Mars Orbit                |                 4020 |
| 5e9d0d95eda69974db09d1ed | rocket | Falcon Heavy | Low Earth Orbit           |                63800 |
| 5e9d0d95eda69974db09d1ed | rocket | Falcon Heavy | Geosynchronous Transfer Orbit |                26700 |
| 5e9d0d95eda69974db09d1ed | rocket | Falcon Heavy | Mars Orbit                |                16800 |
| 5e9d0d95eda69974db09d1ed | rocket | Falcon Heavy | Pluto Orbit               |                 3500 |
| 5e9d0d96eda699382d09d1ee | rocket | Starship | Low Earth Orbit           |               150000 |
| 5e9d0d96eda699382d09d1ee | rocket | Starship | Mars Orbit                |               100000 |
| 5e9d0d96eda699382d09d1ee | rocket | Starship | Moon Orbit                |               100000 |


Rather than five rows, we have 11; each row contains a rocket and it's payload.

### Nested @frame directives

Frames can also be nested and if a nested `@frame` is within a list, the rows are combined into a single data-frame.

For example, we can pluck the top five `rockets` and `engines`:


```python
query = """
{
  rockets(limit: 5) @frame {
    id
    type
    name
    engines @frame {
      number
      type
      version
    }
  }
}
"""
rockets, engines = pluck.execute(query, url=SpaceX)
```

Now we have the `rockets`:


```python
rockets
```

| id                   | type   | name     |   engines.number | engines.type   | engines.version   |
|:-------------------------|:-------|:-------------|-----------------:|:---------------|:------------------|
| 5e9d0d95eda69955f709d1eb | rocket | Falcon 1 |                1 | merlin     | 1C            |
| 5e9d0d95eda69973a809d1ec | rocket | Falcon 9 |                9 | merlin     | 1D+           |
| 5e9d0d95eda69974db09d1ed | rocket | Falcon Heavy |               27 | merlin     | 1D+           |
| 5e9d0d96eda699382d09d1ee | rocket | Starship |               37 | raptor     |               |


And we also have the `engines` data-frame that has been combined from every item in `rockets`:


```python
engines
```

|   number | type   | version   |
|---------:|:-------|:----------|
|        1 | merlin | 1C    |
|        9 | merlin | 1D+   |
|       27 | merlin | 1D+   |
|       37 | raptor |       |


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
launches, = pluck.execute(query, url=SpaceX)
launches
```

| mission | launch_date           | rocket.name   |
|:------------|:--------------------------|:--------------|
| FalconSat   | 2006-03-25T10:30:00+12:00 | Falcon 1  |
| DemoSat | 2007-03-21T13:10:00+12:00 | Falcon 1  |
| Trailblazer | 2008-08-03T15:34:00+12:00 | Falcon 1  |
| RatSat  | 2008-09-28T11:15:00+12:00 | Falcon 1  |
| RazakSat| 2009-07-13T15:35:00+12:00 | Falcon 1  |


### Column names

Columns are named according to the JSON path of the element in the response.

However, we can use a different naming strategy by specifying `column_names` to `execute`.

For example, let's use `short` for the column names:


```python
query = """
{
  launches: launches(limit: 5) @frame {
    name: mission_name
    launch_date: launch_date_local
    rocket {
      rocket: rocket_name
    }
  }
}
"""
launches, = pluck.execute(query, column_names="short", url=SpaceX)
launches
```

| name    | launch_date           | rocket   |
|:------------|:--------------------------|:---------|
| FalconSat   | 2006-03-25T10:30:00+12:00 | Falcon 1 |
| DemoSat | 2007-03-21T13:10:00+12:00 | Falcon 1 |
| Trailblazer | 2008-08-03T15:34:00+12:00 | Falcon 1 |
| RatSat  | 2008-09-28T11:15:00+12:00 | Falcon 1 |
| RazakSat| 2009-07-13T15:35:00+12:00 | Falcon 1 |


If the short column name results in a conflict (two or more columns with the same name), the conflict is resolved by
prefixing the name with the name of it's parent.

The naming strategy can also be changed per data-frame by specifying a `dict[str, str]` where the key is name of the
data-frame.

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
launches, = pluck.execute(query, url=SpaceX)
launches
```

| mission |
|:------------|
| FalconSat   |
| DemoSat |
| Trailblazer |
| RatSat  |
| RazakSat|


### Responses

Most of the time, Pluck is used to transform the GraphQL query directly into one or more data-frames. However, it is also possible to retreive the the raw GraphQL response (as well as the data-frames) by not immeadiately iterating over the return value.

The return value is a `pluck.Response` object and contains the `data` and `errors` from the raw GraphQL response and map of `Dict[str, DataFrame]` containing each data-frame in the query. The name of the frame corresponds to the field on which the `@frame` directive is placed or `default` when using implicit mode.


```python
query = """
{
  launches(limit: 5) @frame {
    id
    mission_name
    rocket {
      rocket_name
    }
  }
  landpads(limit: 5) @frame {
    id
    full_name
    wikipedia
  }
}
"""
response = pluck.execute(query, url=SpaceX)

# print(response.data.keys())
# print(response.errors)
# print(response.frames.keys())

launches, landpads = response
launches
print()
landpads
```

| id                   | mission_name   | rocket.rocket_name   |
|:-------------------------|:---------------|:---------------------|
| 5eb87cd9ffd86e000604b32a | FalconSat  | Falcon 1         |
| 5eb87cdaffd86e000604b32b | DemoSat    | Falcon 1         |
| 5eb87cdbffd86e000604b32c | Trailblazer| Falcon 1         |
| 5eb87cdbffd86e000604b32d | RatSat     | Falcon 1         |
| 5eb87cdcffd86e000604b32e | RazakSat   | Falcon 1         |
    
| id                   | full_name                 | wikipedia                                                                            |
|:-------------------------|:------------------------------|:-----------------------------------------------------------------------------------------|
| 5e9e3032383ecb267a34e7c7 | Landing Zone 1            | https://en.wikipedia.org/wiki/Landing_Zones_1_and_2                                  |
| 5e9e3032383ecb90a834e7c8 | Landing Zone 2            | https://en.wikipedia.org/wiki/Landing_Zones_1_and_2                                  |
| 5e9e3032383ecb554034e7c9 | Landing Zone 4            | https://en.wikipedia.org/wiki/Vandenberg_AFB_Space_Launch_Complex_4#LZ-4_landing_history |
| 5e9e3032383ecb6bb234e7ca | Of Course I Still Love You| https://en.wikipedia.org/wiki/Autonomous_spaceport_drone_ship                        |
| 5e9e3032383ecb761634e7cb | Just Read The Instructions V1 | https://en.wikipedia.org/wiki/Autonomous_spaceport_drone_ship                        |


### pluck.create

Pluck also provides a `create` factory function which returns a customized `execute` function which closes over the `url` and other configuration.


```python
execute = pluck.create(url=SpaceX)

query = """
{
  launches(limit: 5) @frame {
    id
    mission_name
    rocket {
      rocket_name
    }
  }
}
"""
launches, = execute(query)
launches
```

| id                   | mission_name   | rocket.rocket_name   |
|:-------------------------|:---------------|:---------------------|
| 5eb87cd9ffd86e000604b32a | FalconSat  | Falcon 1         |
| 5eb87cdaffd86e000604b32b | DemoSat    | Falcon 1         |
| 5eb87cdbffd86e000604b32c | Trailblazer| Falcon 1         |
| 5eb87cdbffd86e000604b32d | RatSat     | Falcon 1         |
| 5eb87cdcffd86e000604b32e | RazakSat   | Falcon 1         |

