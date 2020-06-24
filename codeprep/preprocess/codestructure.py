# SPDX-FileCopyrightText: 2020 2020 Hlib Babii <hlibbabii@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import bisect
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from codeprep.util.misc import cum_sum


@dataclass(frozen=True)
class PureSnippetStructure:
    subtokens_in_each_line: List[int]
    _cumulative_sizes: List[int] = field(repr=False, hash=False, compare=False)

    @classmethod
    def of(cls, subtokens_in_each_line: List[int]) -> 'PureSnippetStructure':
        return cls(subtokens_in_each_line, cum_sum(subtokens_in_each_line))

    @staticmethod
    def empty() -> 'PureSnippetStructure':
        return PureSnippetStructure.of([0])

    @staticmethod
    def empty_line() -> 'PureSnippetStructure':
        return PureSnippetStructure.of([0, 0])

    def __len__(self) -> int:
        return self._cumulative_sizes[-1]

    def tie_to_working_dir(self, path: Path, first_line: int, firt_token_in_line) -> 'SnippetStructure':
        return SnippetStructure(self.subtokens_in_each_line, self._cumulative_sizes, path, first_line, firt_token_in_line)

    def _merge_lines(self, other: 'PureSnippetStructure') -> Tuple[List[int], List[int]]:
        lines_combines = self.subtokens_in_each_line[:-1] + \
                         [self.subtokens_in_each_line[-1] + other.subtokens_in_each_line[0]] + \
                         other.subtokens_in_each_line[1:]
        cumul = self._cumulative_sizes[:-1] + [x + self._cumulative_sizes[-1] for x in other._cumulative_sizes]
        return lines_combines, cumul

    def merge(self, other: 'PureSnippetStructure') -> 'PureSnippetStructure':
        lines_combines, cumul = self._merge_lines(other)
        return PureSnippetStructure(lines_combines, cumul)

    def _split_lines(self, second_part_start_index: int):
        line_to_be_split = bisect.bisect_right(self._cumulative_sizes, second_part_start_index, 0, len(self._cumulative_sizes))
        total_lengths_of_previous_lines = self._cumulative_sizes[line_to_be_split - 1] if line_to_be_split > 0 else 0
        position_to_split_in_line = second_part_start_index - total_lengths_of_previous_lines

        lines_in_first = self.subtokens_in_each_line[:line_to_be_split]
        cumul_lines_in_first = self._cumulative_sizes[:line_to_be_split]
        if line_to_be_split < len(self.subtokens_in_each_line):
            lines_in_first.append(position_to_split_in_line)
            cumul_lines_in_first.append((cumul_lines_in_first[-1] if cumul_lines_in_first else 0) + position_to_split_in_line)
            first_line_in_second = [self.subtokens_in_each_line[line_to_be_split] - position_to_split_in_line]
        else:
            first_line_in_second = [0]
        lines_in_second = first_line_in_second + self.subtokens_in_each_line[line_to_be_split+1:]
        return lines_in_first, cumul_lines_in_first, lines_in_second

    def split(self, second_part_start_index: int) -> Tuple['PureSnippetStructure', 'PureSnippetStructure']:
        lines_in_first, cumul_lines_in_first, lines_in_second = self._split_lines(second_part_start_index)
        return PureSnippetStructure(lines_in_first, cumul_lines_in_first), PureSnippetStructure.of(lines_in_second)


@dataclass(frozen=True)
class SnippetStructure(PureSnippetStructure):
    """
    >>> snippet_a = SnippetStructure.from_path_and_lines(Path(''), [3], 2, 17)
    >>> snippet_a.split(4)
    (.: [3], start: (2:17), .: [0], start: (2:20))
    >>> snippet_a.split(0)
    (.: [0], start: (2:17), .: [3], start: (2:17))
    >>> snippet_a.split(2)
    (.: [2], start: (2:17), .: [1], start: (2:19))
    >>> snippet_a.split(3)
    (.: [3], start: (2:17), .: [0], start: (2:20))

    >>> snippet_b = SnippetStructure.from_path_and_lines(Path(''), [3, 0, 0, 4], 2, 17)
    >>> len(snippet_b)
    7
    >>> snippet_b.split(3)
    (.: [3, 0, 0, 0], start: (2:17), .: [4], start: (5:0))
    >>> snippet_b.split(7)
    (.: [3, 0, 0, 4], start: (2:17), .: [0], start: (5:4))
    >>> first, second = snippet_b.split(4)
    >>> first
    .: [3, 0, 0, 1], start: (2:17)
    >>> len(first)
    4
    >>> second
    .: [3], start: (5:1)
    >>> len(second)
    3
    >>> second.merge(first)
    Traceback (most recent call last):
    ...
    ValueError: Snippets are not adjacent.
    >>> second_partial = second.split(1)[1]
    >>> first.merge(second_partial)
    Traceback (most recent call last):
    ...
    ValueError: Snippets are not adjacent.
    >>> third = first.merge(second)
    >>> third
    .: [3, 0, 0, 4], start: (2:17)
    >>> third == snippet_b
    True
    >>> len(third)
    7

    """
    path: Path
    first_line: int
    first_token_in_line: int

    @classmethod
    def from_path_and_lines(cls, path: Path, subtokens_in_each_line: List[int],
                            first_line: int, first_token_in_line: int) -> 'SnippetStructure':
        return SnippetStructure(subtokens_in_each_line, cum_sum(subtokens_in_each_line), path, first_line, first_token_in_line)

    def untie_from_file(self) -> PureSnippetStructure:
        return PureSnippetStructure(self.subtokens_in_each_line, self._cumulative_sizes)

    def merge(self, other: 'SnippetStructure') -> 'SnippetStructure':
        if self.path != other.path:
            raise ValueError("Cannot merge two different files.")

        if self.last_line() != other.first_line:
            raise ValueError("Snippets are not adjacent.")

        if self.last_token_position_at_line(other.first_line) != other.first_token_in_line:
            raise ValueError("Snippets are not adjacent.")

        lines, cumul = self._merge_lines(other)
        return SnippetStructure(lines, cumul, self.path, self.first_line, self.first_token_in_line)

    def split(self, second_part_start_index: int) -> Tuple['SnippetStructure', 'SnippetStructure']:
        lines1, lines1_cumul, lines2 = self._split_lines(second_part_start_index)

        first_token_in_line = lines1[-1] + (self.first_token_in_line if len(lines1) == 1 else 0)
        return SnippetStructure(lines1, lines1_cumul, self.path, self.first_line, self.first_token_in_line), \
               SnippetStructure.from_path_and_lines(self.path, lines2, self.first_line + len(lines1) - 1, first_token_in_line)

    def last_token_position_at_line(self, line: int) -> int:
        """
        >>> snippet = SnippetStructure.from_path_and_lines(Path(''), [3, 4, 0], 2, 17)
        >>> snippet.last_token_position_at_line(2)
        20
        >>> snippet.last_token_position_at_line(3)
        4
        >>> snippet.last_token_position_at_line(4)
        0
        >>> snippet.last_token_position_at_line(5)
        Traceback (most recent call last):
        ...
        IndexError: list index out of range
        """
        relative_line = line - self.first_line
        last_token_position = self.subtokens_in_each_line[relative_line]
        if relative_line == 0:
            last_token_position += self.first_token_in_line
        return last_token_position

    def last_line(self) -> int:
        """
        >>> snippet = SnippetStructure.from_path_and_lines(Path(''), [3], 2, 17)
        >>> snippet.last_line()
        2
        >>> snippet = SnippetStructure.from_path_and_lines(Path(''), [3, 0], 2, 17)
        >>> snippet.last_line()
        3
        """
        return self.first_line + len(self.subtokens_in_each_line) - 1

    def __len__(self) -> int:
        return len(self.untie_from_file())

    def __iter__(self):
        return SnippetIterator(self)

    def __repr__(self):
        return f'{self.path}: {self.subtokens_in_each_line}, start: ({self.first_line}:{self.first_token_in_line})'


class SnippetIterator:
    def __init__(self, snippet_structure: SnippetStructure):
        self.snippet_structure = snippet_structure

        self.current_line = snippet_structure.first_line
        self.current_token = snippet_structure.first_token_in_line

    def __next__(self) -> 'CodeLocation':
        while self.current_token == self.snippet_structure.last_token_position_at_line(self.current_line):
            self.current_line += 1
            if self.current_line > self.snippet_structure.last_line():
                raise StopIteration
            self.current_token = 0

        current_token = self.current_token
        self.current_token += 1
        return CodeLocation(self.snippet_structure.path, self.current_line, current_token)


@dataclass
class CodeBaseStructure:
    """
    >>> snippet = SnippetStructure.from_path_and_lines(Path(''), [3, 4], 2, 17)
    >>> snippet_a, snippet_b = snippet.split(5)
    >>> prepped_code = CodeBaseStructure.of([snippet_a, snippet_b])
    >>> prepped_code.split(7)
    (CodeBaseStructure(snippets=[.: [3, 2], start: (2:17), .: [2], start: (3:2)]), CodeBaseStructure(snippets=[]))
    >>> prepped_code.split(99)
    (CodeBaseStructure(snippets=[.: [3, 2], start: (2:17), .: [2], start: (3:2)]), CodeBaseStructure(snippets=[]))
    >>> first, second = prepped_code.split(2)
    >>> first
    CodeBaseStructure(snippets=[.: [2], start: (2:17)])
    >>> len(first)
    2
    >>> second
    CodeBaseStructure(snippets=[.: [1, 2], start: (2:19), .: [2], start: (3:2)])
    >>> len(second)
    5
    >>> third = first.merge(second)
    >>> third
    CodeBaseStructure(snippets=[.: [3, 4], start: (2:17)])
    >>> third = prepped_code
    >>> len(third)
    7
    >>> another_code_structure = CodeBaseStructure.of([snippet_a, snippet_a.split(1000)[1], snippet_b])
    >>> prepped_code_iterator = iter(another_code_structure)
    >>> next(prepped_code_iterator)
    .: (2:17)
    >>> next(prepped_code_iterator)
    .: (2:18)
    >>> next(prepped_code_iterator)
    .: (2:19)
    >>> next(prepped_code_iterator)
    .: (3:0)
    >>> next(prepped_code_iterator)
    .: (3:1)
    >>> next(prepped_code_iterator)
    .: (3:2)
    >>> next(prepped_code_iterator)
    .: (3:3)
    >>> next(prepped_code_iterator)
    Traceback (most recent call last):
    ...
    StopIteration
    """
    snippets: List[SnippetStructure]
    _cumulative_sizes: List[int] = field(repr=False, hash=False, compare=False)

    @classmethod
    def empty(cls) -> 'CodeBaseStructure':
        return cls([], [])

    @classmethod
    def of(cls, snippets: List[SnippetStructure]) -> 'CodeBaseStructure':
        return CodeBaseStructure(snippets, cum_sum(map(lambda x: len(x), snippets)))

    def add_snippet(self, prepped_snippet: SnippetStructure) -> 'CodeBaseStructure':
        if not self.snippets or self.snippets[-1].path != prepped_snippet.path:
            self.snippets.append(prepped_snippet)
            self._cumulative_sizes.append(len(self) + len(prepped_snippet))
        else:
            self.snippets[-1] = self.snippets[-1].merge(prepped_snippet)
            self._cumulative_sizes[-1] += len(prepped_snippet)
        return self

    def merge(self, code_base_structure: 'CodeBaseStructure') -> 'CodeBaseStructure':
        for snippet in code_base_structure.snippets:
            self.add_snippet(snippet)
        return self

    def split(self, second_part_start_index: int) -> Tuple['CodeBaseStructure', 'CodeBaseStructure']:
        snippet_to_be_split = bisect.bisect_right(self._cumulative_sizes, second_part_start_index, 0, len(self._cumulative_sizes))
        total_lengths_of_previous_snippets = self._cumulative_sizes[snippet_to_be_split - 1] if snippet_to_be_split > 0 else 0
        position_to_split_in_snippet = second_part_start_index - total_lengths_of_previous_snippets
        if snippet_to_be_split < len(self._cumulative_sizes):
            first, second = self.snippets[snippet_to_be_split].split(position_to_split_in_snippet)
            snippets_in_first = self.snippets[:snippet_to_be_split]
            cumul_length_first = self._cumulative_sizes[:snippet_to_be_split]
            first_code_base_structure = CodeBaseStructure(snippets_in_first, cumul_length_first)
            if len(first) > 0:
                first_code_base_structure.add_snippet(first)
            snippets_in_second = [second] + self.snippets[snippet_to_be_split+1:]
            return first_code_base_structure, CodeBaseStructure.of(snippets_in_second)
        else:
            return CodeBaseStructure(self.snippets, self._cumulative_sizes), CodeBaseStructure.empty()

    def __len__(self) -> int:
        return self._cumulative_sizes[-1] if self._cumulative_sizes else 0

    def __iter__(self):
        return CodeBaseIterator(self)


class CodeBaseIterator:
    def __init__(self, code_base_structure: CodeBaseStructure):
        self.code_base_structure = code_base_structure

        self.current_snippet = 0
        self.snippet_iterator = iter(self.code_base_structure.snippets[0]) if self.code_base_structure.snippets else iter([])

    def __next__(self) -> 'CodeLocation':
        try:
            return next(self.snippet_iterator)
        except StopIteration:
            self.current_snippet += 1
            while self.current_snippet < len(self.code_base_structure.snippets):
                # while because there might en empty snippets
                self.snippet_iterator = iter(self.code_base_structure.snippets[self.current_snippet])
                try:
                    return next(self.snippet_iterator)
                except StopIteration:
                    self.current_snippet += 1
            raise StopIteration


@dataclass(frozen=True)
class CodeLocation:
    path: Path
    line: int
    token: int

    def __repr__(self) -> str:
        return f'{self.path}: ({self.line}:{self.token})'