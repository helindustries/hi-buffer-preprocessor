#  Copyright 2023-2025 $author, All rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt in this repository file going up the directory tree.
#

import os.path
import re
import sys
from dataclasses import dataclass
from typing import Optional, Union

data_widths = {"uint8_t": 1, "uint16_t": 2, "uint32_t": 4, "uint64_t": 8,
               "int8_t": 1, "int16_t": 2, "int32_t": 4, "int64_t": 8,
               "float": 4, "double": 8, "bool": 1, "char": 1,
               int: 8, float: 8, bool: 1}
def get_data_width(data_type: Union[str, type]) -> Optional[int]:
    """
    Get the width of a data type in bytes
    :param data_type: The C or Python data type
    :return: The byte width of the data type

    >>> get_data_width("uint8_t")
    1
    >>> get_data_width("uint16_t")
    2
    >>> get_data_width("uint32_t")
    4
    >>> get_data_width("uint64_t")
    8
    >>> get_data_width(str) is None
    True
    >>> get_data_width(int)
    8
    """
    return data_widths.get(data_type.strip(), None)

def common_prefix(lhs, rhs, max_length) -> int:
    """
    Return the length of the common prefix of(lhs and rhs

    >>> common_prefix("foo", "foobar", 3)
    3
    >>> common_prefix("foo", "bar", 5)
    0
    >>> common_prefix("foo", "foo", 3)
    3
    >>> common_prefix("foobar", "foo", 4)
    3
    >>> common_prefix("foobar", "foo", 1)
    1
    """
    lhs_len = len(lhs)
    count = min(len(rhs), max_length)
    for i in range(count):
        if lhs[i % lhs_len] != rhs[i]:
            return i
    return count

if __name__ == "__main__":
    import doctest
    doctest.testmod()
