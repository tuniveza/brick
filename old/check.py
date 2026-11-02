"""Snap the bricks of a program together and print the world after each one.

Usage: python3 check.py program.txt
"""
import sys

from bricks import KNOWN, brick_from_line
from world import World


def read_program(path):
    """The program's lines, skipping empty lines and # notes."""
    with open(path) as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line and not line.startswith("#")]


def snap(line, world):
    """Turn one line into a brick and snap it onto the world. Returns (brick, refusal)."""
    brick = brick_from_line(line)
    if brick is None:
        return None, f"I don't recognise this line. Known bricks: {KNOWN}."
    return brick, world.add(brick)


def main():
    world = World()
    print(f"start\n    world: {world.describe()}")
    for line in read_program(sys.argv[1]):
        brick, problem = snap(line, world)
        if problem:
            print(f"{line}\n    REFUSED: {problem}")
        else:
            print(f"{line}\n    does: {brick.does}\n    world: {world.describe()}")


if __name__ == "__main__":
    main()
