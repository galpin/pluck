from abc import ABC, abstractmethod
from typing import Dict, Iterable

import pandas as pd

__all__ = ("DataFrameLibrary", "PandasDataFrameLibrary", "Records", "DataFrame")

Records = Iterable[Dict]
DataFrame = pd.DataFrame


class DataFrameLibrary(ABC):
    """
    Base class for data frame libraries.
    """

    @abstractmethod
    def create(self, data: Records) -> DataFrame:
        """
        Create a data frame from the given records.

        :param data: The records to create the data frame from.
        :return: The created data frame.
        """
        raise NotImplementedError()

    @abstractmethod
    def rename(self, df: DataFrame, columns: dict[str, str]) -> DataFrame:
        """
        Renames the columns in the data-frame.

        :param df: The data-frame.
        :param columns: The map of old to new column names.
        :return: The data-frame with the renamed columns.
        """
        raise NotImplementedError()


class PandasDataFrameLibrary(DataFrameLibrary):
    """
    The Pandas library.
    """

    def create(self, data: Records) -> DataFrame:
        return pd.DataFrame(data)

    def rename(self, df: DataFrame, columns: dict[str, str]) -> DataFrame:
        return df.rename(columns=columns)
