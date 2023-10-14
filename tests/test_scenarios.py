import json
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import httpretty
import pandas as pd
import pytest

import pluck


@dataclass
class ScenarioInfo:
    name: str
    query: Path
    response: Path
    expected: Path
    setup_module: str

    def load_setup_module(self):
        try:
            return importlib.import_module(self.setup_module)
        except ModuleNotFoundError:
            return None


def get_scenarios():
    root = Path(__file__).parent
    for file in root.glob("scenarios/*.graphql"):
        query = Path(file)
        response = query.with_suffix(".json")
        expected = query.with_suffix(".expected.json")
        setup = f"{query.parent.name}.{query.stem}"
        yield query.name, ScenarioInfo(query.name, query, response, expected, setup)


@httpretty.activate
@pytest.mark.parametrize("name,scenario", get_scenarios())
def test_scenarios(name, scenario):
    url = "http://api/graphql"
    query = scenario.query.read_text()
    response = json.load(scenario.response.open(encoding="utf-8"))
    httpretty.register_uri(httpretty.POST, url, body=json.dumps(response))
    setup = scenario.load_setup_module()
    kwargs = setup.get_kwargs() if setup else {}

    actual = pluck.read_graphql(query, url=url, **kwargs)

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
