# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

from abc import ABC, abstractmethod
from typing import Dict, Iterable

import pandas as pd

Records = Iterable[Dict]
DataFrame = pd.DataFrame


class DataFrameLibrary(ABC):
    @abstractmethod
    def create(self, data: Records) -> DataFrame:
        raise NotImplementedError()


class PandasDataFrameLibrary(DataFrameLibrary):
    def create(self, data: Records) -> DataFrame:
        return pd.DataFrame(data)
