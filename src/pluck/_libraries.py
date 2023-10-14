from abc import ABC, abstractmethod
from typing import Dict, Iterable

import pandas as pd

__all__ = ("DataFrameLibrary", "PandasDataFrameLibrary", "Records", "DataFrame")

Records = Iterable[Dict]
DataFrame = pd.DataFrame


class DataFrameLibrary(ABC):
    @abstractmethod
    def create(self, data: Records) -> DataFrame:
        raise NotImplementedError()

    @abstractmethod
    def rename(self, df: DataFrame, columns: dict[str, str]) -> DataFrame:
        raise NotImplementedError()


class PandasDataFrameLibrary(DataFrameLibrary):
    def create(self, data: Records) -> DataFrame:
        return pd.DataFrame(data)

    def rename(self, df: DataFrame, columns: dict[str, str]) -> DataFrame:
        return df.rename(columns=columns)
