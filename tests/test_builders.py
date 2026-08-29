"""Builders pinned to the evaluated outputs recorded in the research notebook."""

from mrm import builders


def test_scalar_matches_notebook():
    assert builders.scalar(4) == [
        [1, 1, [2], []],
        [2, 0, [3]],
        [2, 0, [4]],
        [2, 0, [5]],
        [2, 0, [1]],
    ]
    assert builders.scalar(3, 0, 8, (2, 1)) == [
        [2, 1, [2], [8]],
        [1, 0, [3]],
        [1, 0, [4]],
        [1, 0, [1]],
    ]


def test_divide_matches_notebook():
    assert builders.divide(4) == [
        [2, 0, [2]],
        [1, 1, [3], []],
        [1, 1, [4], []],
        [1, 1, [5], []],
        [1, 1, [1], []],
    ]


def test_multiply_matches_notebook():
    assert builders.multiply() == [
        [1, 1, [2], []],
        [2, 1, [3], [5]],
        [3, 0, [4]],
        [4, 0, [2]],
        [3, 1, [6], [1]],
        [2, 0, [5]],
    ]


def test_power_matches_notebook():
    assert builders.power() == [
        [5, 1, [2], []],
        [1, 1, [3], [8]],
        [2, 1, [4], [6]],
        [3, 0, [5]],
        [4, 0, [3]],
        [3, 1, [7], [2]],
        [2, 0, [6]],
        [4, 1, [9], [1]],
        [1, 0, [8]],
    ]


def test_add_and_subtract_match_notebook():
    assert builders.add() == [[1, 1, [2], []], [2, 0, [1]]]
    assert builders.subtract() == [[1, 1, [2], []], [2, 1, [1], []]]


def test_polynomial_creater_matches_notebook():
    assert builders.polynomial_creater() == [
        [5, 1, [2], [10]],
        [1, 1, [3], [8]],
        [2, 1, [4], [6]],
        [3, 0, [5]],
        [4, 0, [3]],
        [3, 1, [7], [2]],
        [2, 0, [6]],
        [4, 1, [9], [1]],
        [1, 0, [8]],
        [4, 1, [11], [13]],
        [1, 0, [12]],
        [1, 0, [10]],
        [2, 1, [14], []],
        [1, 0, [13]],
    ]


def test_collatz_instructions_match_notebook():
    assert builders.collatz_instructions() == [
        [2, 1, [2], [8]],
        [1, 0, [3]],
        [1, 0, [4]],
        [1, 0, [1]],
        [1, 0, [6]],
        [2, 1, [7], [8]],
        [2, 1, [5], [8]],
        [1, 1, [9], [4, 6]],
        [2, 0, [8]],
    ]


def test_fibonacci_instructions_match_notebook():
    assert builders.fibonacci_instructions() == [
        [2, 1, [2], [4]],
        [3, 0, [3]],
        [4, 0, [1]],
        [1, 1, [5], [6]],
        [3, 0, [4]],
        [3, 1, [7], [8]],
        [2, 0, [6]],
        [4, 1, [9], [1]],
        [1, 0, [8]],
    ]


def test_collatz_trajectory_matches_notebook_101():
    assert builders.collatz_trajectory(101) == [
        101,
        304,
        152,
        76,
        38,
        19,
        58,
        29,
        88,
        44,
        22,
        11,
        34,
        17,
        52,
        26,
        13,
        40,
        20,
        10,
        5,
        16,
        8,
        4,
        2,
        1,
    ]
