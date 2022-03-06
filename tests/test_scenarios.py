import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import httpretty
import pandas as pd
import pytest

import pluck


@dataclass
class Scenario:
    name: str
    query: Path
    response: Path
    expected: Path


def get_scenarios():
    for file in glob.iglob("scenarios/*.graphql"):
        query = Path(file)
        response = query.with_suffix(".json")
        expected = query.with_suffix(".expected.json")
        yield query.name, Scenario(query.name, query, response, expected)


@httpretty.activate
@pytest.mark.parametrize("name,scenario", get_scenarios())
def test_scenarios(name, scenario):
    url = "http://api/graphql"
    query = scenario.query.read_text()
    response = json.load(scenario.response.open())
    httpretty.register_uri(httpretty.POST, url, body=json.dumps(response))

    actual = pluck.read_graphql(query, url=url)

    assert actual.data == response.get("data")
    assert actual.errors == response.get("errors")
    assert_frames(scenario.expected, actual.frames)


def assert_frames(path: Path, actual: Dict[str, pd.DataFrame]):
    if not path.exists():
        dto = prepare(actual)
        json.dump(dto, path.open("w"), indent=True)
        return

    expected = json.load(path.open())
    actual = prepare(actual)
    assert actual == expected


def prepare(actual: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
    return {
        name: frame.fillna("").to_dict(orient="records")
        for name, frame in actual.items()
    }
