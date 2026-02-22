from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable

import pandas as pd

__all__ = ("DataFrameLibrary", "PandasDataFrameLibrary", "Records", "DataFrame")

Records = Iterable[Dict]
DataFrame = pd.DataFrame


class DataFrameLibrary(ABC):
    @abstractmethod
    def create(self, data: Records) -> DataFrame:
        raise NotImplementedError()

    def create_from_dict(self, data: dict[str, list]) -> DataFrame:
        """Create a DataFrame from columnar data {col_name: [values...]}."""
        return self.create(data)

    def create_from_arrow(self, record_batch: Any) -> DataFrame:
        """Create a DataFrame from a PyArrow RecordBatch."""
        return self.create_from_dict(record_batch.to_pydict())

    @abstractmethod
    def rename(self, df: DataFrame, columns: dict[str, str]) -> DataFrame:
        raise NotImplementedError()


class PandasDataFrameLibrary(DataFrameLibrary):
    def create(self, data: Records) -> DataFrame:
        return pd.DataFrame(data)

    def create_from_dict(self, data: dict[str, list]) -> DataFrame:
        return pd.DataFrame(data)

    def create_from_arrow(self, record_batch: Any) -> DataFrame:
        return record_batch.to_pandas()

    def rename(self, df: DataFrame, columns: dict[str, str]) -> DataFrame:
        return df.rename(columns=columns)
