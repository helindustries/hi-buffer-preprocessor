#  Copyright 2023-2025 $author, All rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt in this repository file going up the directory tree.
#

from array import array

def bit_width_per_value(value):
    width = 0
    while (2 ** width) <= value:
        width += 1
    return width if value > 0 else 1

class Bitstream(object):
    def __init__(self):
        self.buffer: list[int] = []
        self.read_position = 0
        self.write_position = 0
        self.current_byte = 0
    def append(self, count: int, value: int):
        buffer = self.buffer
        current_byte = self.current_byte
        write_position = self.write_position
        bit = count - 1
        for _ in range(count):
            current_byte = (current_byte << 1) | ((value >> (bit)) & 1)
            bit -= 1
            write_position += 1
            if write_position == 8:
                buffer.append(current_byte)
                current_byte = 0
                write_position = 0
        self.write_position = write_position
        self.current_byte = current_byte
        self.buffer = buffer
    def read(self, count: int) -> int:
        value = 0
        position = self.read_position
        buffer = self.buffer
        current_byte = self.current_byte
        for _ in range(count):
            if (position & 7) == 0:
                if position // 8 >= len(buffer):
                    break
                else:
                    current_byte = buffer[position // 8]
            value = (value << 1) | ((current_byte >> (7 - (position & 7))) & 1)
            position += 1
        self.read_position = position
        self.current_byte = current_byte
        return value
    def to_array(self) -> array:
        if self.write_position > 0:
            self.buffer.append(self.current_byte << (8 - self.write_position))
        return array('B', self.buffer)
    def from_array(self, data: array):
        self.buffer = list(data)
        self.read_position = 0
        self.current_byte = 0
        self.write_position = 0
