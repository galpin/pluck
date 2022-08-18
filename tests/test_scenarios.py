# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import pandas as pd
import pytest


@dataclass
class Scenario:
    name: str
    query: Path
    response: Path
    expected: Path


def get_scenarios():
    root = Path(__file__).parent
    for file in root.glob("scenarios/*.graphql"):
        query = Path(file)
        response = query.with_suffix(".json")
        expected = query.with_suffix(".expected.json")
        yield query.name, Scenario(query.name, query, response, expected)


@pytest.mark.parametrize("name,scenario", get_scenarios())
def test_scenarios(ctx, name, scenario):
    query = scenario.query.read_text()
    response = json.load(scenario.response.open())
    ctx.setup_response(**response)

    actual = ctx.read_graphql(query)

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
