#  Copyright 2025 $author, All rights reserved.
from dataclasses import dataclass
from typing import Union, Iterable, Optional, Callable
from array import array

from .utilities import common_prefix
from .bitstream import Bitstream, bit_width_per_value
from .process_controller import ProcessController

def sanitize_buffer_address(buffer: Union[str, list, array, bytes], address_bits: int) -> int:
    """
    Determine the maximum bit size for the buffer, based on the buffer size and the maximum window bits.
    :param buffer:
    :param max_window_bits:
    :return:

    >>> sanitize_buffer_address("foobar", 16)
    3
    >>> sanitize_buffer_address("foobar", 2)
    2
    """
    return min(bit_width_per_value(len(buffer)), address_bits)

@dataclass
class LZSSEncodingStatistics:
    minimum_backreference: int = 1
    max_window_bits: int = 16
    max_length_bits: int = 16
    size_bit_count: int = 22
    literals: int = 0
    references: int = 0
    max_window = 0
    max_length = 0
    def __init__(self, codec: 'LZSSCodec'):
        self.minimum_backreference = codec.minimum_backreference
        self.max_window_bits = codec.max_window_bits
        self.max_length_bits = codec.max_length_bits
        self.overhead_bits = codec.size_bit_count + 4 + 4 + 2
    def add_literal(self):
        self.literals += 1
    def add(self, offset, length):
        self.references += 1
        if offset > self.max_window:
            if offset > (2 ** self.max_window_bits):
                print(f"Offset {offset}, {length} exceeds {2 ** self.max_window_bits}")
            self.max_window = offset
        if length > self.max_length:
            self.max_length = length
    def size(self):
        size = self.overhead_bits
        size += self.literals * 9
        size += self.references * (1 + self.max_window_bits + self.max_length_bits)
        return (size + 7) // 8
class LZSSCodec(object):
    def __init__(self, max_window_bits, max_length_bits, size_bit_count = 22):
        """

        :param max_window_bits: Bit count for the lookback values
        :param max_length_bits: Bit count for the length values
        :param size_bit_count: Bit count for the size of the compressed data, defaults to 22 bits,
                               so 2**22 items at 9 or max_window_bits + max_length_bits bits
                               each, reasonably assumed to be 4MB of compressed data.
        """
        self.max_window_bits = max_window_bits
        self.max_length_bits = max_length_bits
        self.size_bit_count = size_bit_count
        reference_size = 1 + self.max_window_bits + self.max_length_bits
        if reference_size < 9:
            self.minimum_backreference = 1
        elif reference_size < 17:
            self.minimum_backreference = 2
        elif reference_size < 25:
            self.minimum_backreference = 3
        else:
            self.minimum_backreference = 4
    def compress(self, data: bytes) -> tuple[list[Union[int, tuple[int, int]]], LZSSEncodingStatistics]:
        candidate_cache = {}
        results = []
        minimum_backreference = self.minimum_backreference
        max_length = minimum_backreference + (2 ** self.max_length_bits) - 1
        history = (2 ** self.max_window_bits) + 1
        statistics = LZSSEncodingStatistics(self)
        position = 0
        while position < len(data):
            possible_slice = data[position:position + minimum_backreference]
            candidate_cache_entry = candidate_cache.get(possible_slice, None)
            if candidate_cache_entry is None:
                candidate_cache[possible_slice] = [position]
                results.append(data[position])
                position += 1
                statistics.add_literal()
            else:
                best_candidate = position
                best_length = 0
                oldest = position - history
                new_candidates = []
                for pos in candidate_cache_entry:
                    if pos > oldest:
                        new_candidates.append(pos)
                        if best_length < max_length:
                            prefix = common_prefix(data[pos:position], data[position:], max_length)
                            if prefix > best_length:
                                best_length = prefix
                                best_candidate = pos
                new_candidates.append(position)
                candidate_cache[possible_slice] = new_candidates
                if best_length >= minimum_backreference:
                    results.append((best_candidate - position, best_length))
                    statistics.add(position - best_candidate, best_length)
                    position += best_length
                else:
                    results.append(data[position])
                    position += 1
                    statistics.add_literal()
        return results, statistics
    def decompress(self, compressed_buffer: Iterable[Union[int, tuple[int, int]]]) -> bytes:
        bytebuffer = array("B")
        for entry in compressed_buffer:
            value = entry
            if isinstance(entry, tuple) or isinstance(entry, list):
                if len(entry) < 2:
                    value = entry[0]
                else:
                    offset, length = entry
                    for i in range(length):
                        bytebuffer.append(bytebuffer[offset])
                    continue

            if isinstance(value, str):
                value = ord(value)
            bytebuffer.append(value)
        return bytes(bytebuffer)
    def to_binary(self, compressed_data: list[Union[int, tuple[int, int]]]) -> Optional[array]:
        bitstream = Bitstream()
        bitstream.append(4, self.max_window_bits - 3)
        bitstream.append(4, self.max_length_bits - 1)
        bitstream.append(2, self.minimum_backreference - 1)
        bitstream.append(self.size_bit_count, len(compressed_data))

        for entry in compressed_data:
            if isinstance(entry, tuple) or isinstance(entry, list):
                if len(entry) < 2:
                    value = entry[0]
                else:
                    (offset, length) = entry
                    bitstream.append(1, 1)
                    bitstream.append(self.max_window_bits, -offset - 1)
                    bitstream.append(self.max_length_bits, length - self.minimum_backreference)
                    continue
            else:
                value = entry
            if isinstance(value, str):
                value = ord(value)
            bitstream.append(1, 0)
            bitstream.append(8, value)
        return bitstream.to_array()
    def from_binary(self, data: array) -> bytes:
        bitstream = Bitstream()
        bitstream.from_array(data)

        max_window_bits = bitstream.read(4) + 3
        length = bitstream.read(4) + 1
        minimum_backreference = bitstream.read(2) + 1
        compressed_data = []
        count = bitstream.read(self.size_bit_count)

        # Compressed data
        for _ in range(count):
            if bitstream.read(1):
                offset = -bitstream.read(max_window_bits) - 1
                count = bitstream.read(length) + minimum_backreference
                compressed_data.append((offset, count))
            else:
                compressed_data.append(chr(bitstream.read(8)))

        return self.decompress(compressed_data)

# We only support sentinel-based RLE encoding and flag encoding, we use the following as sentinel
# value, although depending on the bit-width of the values, it may be truncated to a sub-value.
_rle_sentinel = 0x08192A3B4C5D6E7F
def rle_sentinel_for_bit_width(bit_width: int):
    """
    Return a sentinel value for RLE encoding, that is suitable for the given bit width.
    :param bit_width: The bit width of the values to encode
    :return: A sentinel value that is suitable for the given bit width
    >>> hex(rle_sentinel_for_bit_width(8))
    '0x7f'
    >>> hex(rle_sentinel_for_bit_width(16))
    '0x6e7f'
    >>> hex(rle_sentinel_for_bit_width(32))
    '0x4c5d6e7f'
    """
    return _rle_sentinel & ((1 << bit_width) - 1)
@dataclass
class RLEncodingStatistics:
    literals: int = 0
    references: int = 0
    max_length: int = 0
    sentinel: Optional[int] = None
    sentinel_count: int = 0
    def __init__(self, codec):
        self.bit_width = codec.bit_width
        self.use_sentinel = codec.bit_width & 3 == 0
        self.dynamic_sentinel = codec.dynamic_sentinel
        self.header_bits = 7 + 1 + codec.size_bits + codec.bit_width if self.use_sentinel else 0
    def add_literal(self):
        self.literals += 1
    def add(self, length):
        self.references += 1
        if length > self.max_length:
            self.max_length = length
    def analyze_sentinel(self, compression_result: list[Union[int, tuple[int, int]]]):
        if self.use_sentinel:
            if self.dynamic_sentinel:
                # Let's figure out which glyph is used least in data and if there are any gaps. We only check
                # values, that don't have a repeat yet, as those would not result in a lower encoding size.
                self.sentinel = None
                self.sentinel_count = 0
                value_map = {}
                for entry in compression_result:
                    if isinstance(entry, tuple) or isinstance(entry, list):
                        continue
                    value_map[entry] = value_map.get(entry, 0) + 1
                for i in range(1 << self.bit_width):
                    if i not in value_map:
                        self.sentinel = i
                        break
                else:
                    least_used_value = min(value_map.items(), key=lambda x: x[1])
                    self.sentinel = least_used_value[0]
                    self.sentinel_count = least_used_value[1]
            else:
                self.sentinel = rle_sentinel_for_bit_width(self.bit_width)

            if self.sentinel_count < 1:
                for entry in compression_result:
                    if isinstance(entry, tuple) or isinstance(entry, list):
                        continue
                    if entry == self.sentinel:
                        self.sentinel_count += 1
    def size(self):
        # This does not account for the sentinel value causing repeats
        bit_width = self.bit_width
        if not self.use_sentinel:
            bit_width += 1
        size = self.header_bits
        size += self.literals * bit_width
        size += self.references * bit_width * (3 if self.use_sentinel else 2)
        size += self.sentinel_count * bit_width * 2
        return (size + 7) // 8
class RLECodec(object):
    def __init__(self, bit_width: int, dynamic_sentinel: bool = True, size_bits: int = 24):
        self.bit_width = bit_width
        self.size_bits = size_bits
        self.dynamic_sentinel = dynamic_sentinel
        self.use_sentinel = bit_width & 3 == 0
        self.minimum_loop = 3 if self.use_sentinel else 2
    def compress(self, data: bytes) -> tuple[list[Union[int, tuple[int, int]]], RLEncodingStatistics]:
        byte_width = (self.bit_width + 7) // 8
        result = []
        statistics = RLEncodingStatistics(self)
        position = 0
        max_count = 1 << (self.bit_width + 1)
        if not self.use_sentinel:
            max_count <<= 1

        def _get_value(data: bytes):
            value = 0
            for byte in range(min(byte_width, len(data))):
                digit = data[byte] & 0xFF
                if isinstance(digit, str):
                    digit = ord(digit)
                value = value | ((digit & 0xFF) << (byte * 8))
            return value

        while position < len(data):
            value = _get_value(data[position:position + byte_width])
            count = 1
            position += byte_width
            for i in range(position, len(data), byte_width):
                if value != _get_value(data[i:i + byte_width]):
                    break
                count += 1
                position += byte_width
                if count >= max_count:
                    break
            if count >= self.minimum_loop:
                result.append((value, count))
                statistics.add(count)
            else:
                for _ in range(count):
                    result.append(value)
                    statistics.add_literal()
        statistics.analyze_sentinel(result)
        return result, statistics
    def decompress(self, compressed: Iterable[Union[int, tuple[int, int]]]) -> bytes:
        byte_width = (self.bit_width + 7) // 8
        bytebuffer = array("B")
        for entry in compressed:
            if isinstance(entry, tuple) or isinstance(entry, list):
                (value, count) = entry
            else:
                value, count = entry, 1
            if isinstance(value, str):
                value = ord(value)
            valuebuffer = array("B")
            for i in range(byte_width):
                valuebuffer.append(value  & 0xFF)
                value >>= 8
            for i in range(count):
                bytebuffer.extend(valuebuffer)
        return bytes(bytebuffer)
    def to_binary(self, compressed_data: list[Union[int, tuple[int, int]]], statistics: RLEncodingStatistics) -> Optional[array]:
        bitstream = Bitstream()
        bitstream.append(7, self.bit_width - 1)

        # We will try to keep the buffer byte-aligned, if the following bit is set, the buffer
        # uses a sentinel value, since we are using full bytes for the data values. So if
        # we are encoding ASCII, it is worth setting bit-width to 7 instead of 8, so we can
        # use the more beneficial flag encoding.
        bitstream.append(1, self.use_sentinel)
        bitstream.append(self.size_bits, len(compressed_data) - 1)
        # If use_sentinel is 1, expect another
        sentinel = 0
        if self.use_sentinel:
            sentinel = statistics.sentinel
            bitstream.append(self.bit_width, sentinel)
        count_width = self.bit_width + (0 if self.use_sentinel else 1)

        def append_repeat(value, count):
            if self.use_sentinel:
                bitstream.append(self.bit_width, sentinel)
                bitstream.append(self.bit_width, value)
            else:
                bitstream.append(1, 1)
                bitstream.append(self.bit_width, value)
            bitstream.append(count_width, count - 1)

        for entry in compressed_data:
            if isinstance(entry, tuple) or isinstance(entry, list):
                append_repeat(*entry)
            elif self.use_sentinel and entry == sentinel:
                append_repeat(entry, 1)
            else:
                if not self.use_sentinel:
                    bitstream.append(1, 0)
                if isinstance(entry, str):
                    entry = ord(entry)
                bitstream.append(self.bit_width, entry)

        return bitstream.to_array()
    def from_binary(self, data: array) -> bytes:
        bitstream = Bitstream()
        bitstream.from_array(data)

        self.bit_width = bitstream.read(7) + 1
        use_sentinel = bitstream.read(1)
        count = bitstream.read(self.size_bits) + 1
        # Blank read, sentinel is here for reference, but taken care of by repeat sequences
        if use_sentinel:
            sentinel = bitstream.read(self.bit_width)

        compressed_data = []
        for _ in range(count):
            if use_sentinel:
                value = bitstream.read(self.bit_width)
                if value == sentinel:
                    value = bitstream.read(self.bit_width)
                    count = bitstream.read(self.bit_width) + 1
                    compressed_data.append((value, count))
                else:
                    compressed_data.append(value)
            else:
                repeat = bitstream.read(1)
                value = bitstream.read(self.bit_width)
                if repeat:
                    count = bitstream.read(self.bit_width + 1) + 1
                    compressed_data.append((value, count))
                else:
                    compressed_data.append(value)
        return compressed_data
CodecStatistics = LZSSEncodingStatistics

@dataclass
class CompressionResult:
    window_bits: int
    length_bits: int
    size: int
    compressed: Union[array|list[Union[int, tuple[int, int]]]]
    statistics: Optional[CodecStatistics] = None
    pass_count: int = 0
    def __lt__(self, other):
        return self.size < other.size
    def __le__(self, other):
        return self.size <= other.size
class CompressionRunner:
    """
    A runner for compressing buffers with different lookback and length combinations.
    """
    codec: Callable
    controller = ProcessController()
    buffer: bytes = b""
    worse_allowed: int = 0
    print_progress: bool = False
    def __init__(self, codec: Callable, buffer: bytes, max_window_bits: int = 16, max_length_bits = None, max_threads: int = 8):
        """
        Initialize the runner with a codec, buffer and parameters for the compression.
        :param codec: The codec to use for compression
        :param buffer: The buffer to compress
        :param max_window_bits: The maximum lookback to use for compression
        :param max_length: The maximum length to use for compression
        :param max_threads: The maximum number of threads to use for compression
        """
        self.codec = codec
        self.buffer = buffer
        self.controller = ProcessController(max_threads, True, True)
        self.max_window_bits = sanitize_buffer_address(buffer, max_window_bits)
        self.max_length_bits = sanitize_buffer_address(buffer, max_length_bits) if max_length_bits is not None else self.max_window_bits
        self.results = self.controller.manager.list()
    def find_best_compression(self) -> tuple[array, CompressionResult]:
        """
        Find the best compression for a buffer by trying different lookback and length combinations.

        This assumes, that the buffer is interleaved in a maximum of lookback bytes with a maximum length of length.
        To figure out lookback and length, assume the maximum lookback for the given buffer size is the best, then
        try to decrease lookback and observe results improving until the suitable buffer size, before they start to
        deteriorate. Assume there may be a few worse results for lookback, that may still result in better outcomes
        with different lengths, so include them as well.
        """
        def find_reversion(series, max_key: int, get_key: Callable[[CompressionResult], int]) -> tuple[Optional[int], int]:
            lowest_size = float("inf")
            expected_key = lowest_size_key = max_key
            allowed_worse = self.worse_allowed

            for result in sorted(series, key=get_key, reverse=True):
                key = get_key(result)
                if key != expected_key:
                    return None, self.worse_allowed
                if result.size > lowest_size:
                    allowed_worse -= 1
                    if allowed_worse < 0:
                        return lowest_size_key, allowed_worse
                else:
                    if result.size < lowest_size:
                        allowed_worse = self.worse_allowed
                    lowest_size_key = key
                    lowest_size = result.size
                expected_key -= 1
            return lowest_size_key, allowed_worse
        def join_finished():
            if self.controller.max_threads == 1:
                print(".", end="")
                return 1
            count = self.controller.join_finished()
            if self.print_progress:
                print("." * count, end="")
            return count
        def best_result():
            return None if len(self.results) < 1 else min(self.results, key=lambda x: x.size)
        def filter_for_threads(iterable: Iterable):
            for value in iterable:
                if self.controller.available() > 0:
                    yield value
                    if self.controller.max_threads == 1:
                        return
                else:
                    return
        def compress(window_bits: int, length_bits: int):
            def run_compression(window_bits: int, length: int):
                codec = self.codec(window_bits, length)
                comp, statistics = codec.compress(self.buffer)
                result = CompressionResult(window_bits, length, statistics.size(), comp, statistics)
                self.results.append(result)

            if (next((r for r in self.results if r.window_bits == window_bits and r.length_bits == length_bits), False) == False
                    and 2 < window_bits <= self.max_window_bits and 0 < length_bits <= self.max_length_bits):
                self.controller.start(run_compression, (window_bits, length_bits))
        def finished(condition):
            return ((self.controller.max_threads > 1 and self.controller.running() < 1)
                    or (self.controller.max_threads == 1 and condition))
        # Instead of just starting to iterate, try to split the first series between window_bits and length
        # results, it is highly likely that this is enough to find close to the best result already.
        initial_window_bits_count = (self.controller.max_threads + 1) // 2
        start_window_bits = self.max_window_bits - initial_window_bits_count
        start_length_bits = self.max_length_bits - self.controller.max_threads + initial_window_bits_count - 1

        for window_bits in range(self.max_window_bits, start_window_bits, -1):
            compress(window_bits, self.max_length_bits)
        for length_bits in range(self.max_length_bits - 1, start_length_bits, -1):
            compress(self.max_window_bits, length_bits)

        window_bits = start_window_bits
        lowest_window_bits = self.max_window_bits
        while True:
            if join_finished() > 0:
                series = [r for r in self.results if r.length_bits == self.max_length_bits]
                lowest_window_bits, allowed_worse = find_reversion(series, self.max_window_bits, lambda r: r.window_bits)
                if lowest_window_bits is not None and allowed_worse < 0:
                    break
            for window_bits in filter_for_threads(range(window_bits, 2, -1)):
                compress(window_bits, self.max_length_bits)
                window_bits -= 1
            if finished(window_bits < 3):
                if self.controller.max_threads == 1:
                    series = [r for r in self.results if r.length_bits == self.max_length_bits]
                    lowest_window_bits, _ = find_reversion(series, self.max_window_bits, lambda r: r.window_bits)
                break

        # We could do something fancy here to get closer to our original value, but we already ran max_threads / 2
        # iterations with max_window_bits, to get the best results, we need to complete that series.
        length_bits = min(r.length_bits for r in self.results if r.window_bits == self.max_window_bits)
        lowest_length_bits = 1

        while True:
            if join_finished() > 0:
                series = [r for r in self.results if r.window_bits == self.max_window_bits]
                lowest_length_bits, allowed_worse = find_reversion(series, self.max_length_bits, lambda r: r.length_bits)
                if lowest_length_bits is not None and allowed_worse < 0:
                    break
            for length_bits in filter_for_threads(range(length_bits, 0, -1)):
                compress(self.max_window_bits, length_bits)
                length_bits -= 1
            if finished(length_bits < 1):
                if self.controller.max_threads == 1:
                    series = [r for r in self.results if r.window_bits == self.max_window_bits]
                    lowest_length_bits, _ = find_reversion(series, self.max_length_bits, lambda r: r.length_bits)
                break

        additional_combinations = []
        for window_bits in range(lowest_window_bits - 1, lowest_window_bits + 1):
            if (window_bits > 2) and (window_bits <= self.max_window_bits):
                for length_bits in range(lowest_length_bits - 1, lowest_length_bits + 1):
                    if (length_bits > 0) and (length_bits <= self.max_length_bits):
                        additional_combinations.append((window_bits, length_bits))
        while True:
            join_finished()
            for window_bits, length_bits in filter_for_threads(additional_combinations):
                compress(window_bits, length_bits)
                additional_combinations.remove((window_bits, length_bits))
            if finished(len(additional_combinations) < 1):
                break

        result = best_result()
        result.pass_count = len(self.results)
        return self.codec(result.window_bits, result.length_bits).to_binary(result.compressed), result

if __name__ == "__main__":
    import doctest
    doctest.testmod()
