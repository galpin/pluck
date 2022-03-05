from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable

__all__ = ("DataFrameLibrary", "PandasDataFrameLibrary", "Records", "DataFrame")

Records = Iterable[Dict]
DataFrame = Any


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


class PandasDataFrameLibrary(DataFrameLibrary):
    """
    The Pandas library.
    """

    def create(self, data: Records) -> DataFrame:
        from pandas import DataFrame

        return DataFrame(data)
