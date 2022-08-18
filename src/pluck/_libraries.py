# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

from abc import ABC, abstractmethod
from typing import Dict, Iterable

import pandas as pd

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


class PandasDataFrameLibrary(DataFrameLibrary):
    """
    The Pandas library.
    """

    def create(self, data: Records) -> DataFrame:
        return pd.DataFrame(data)
