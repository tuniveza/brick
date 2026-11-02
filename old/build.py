"""Build a runnable program from a plain-English file.

Usage: python3 build.py program.txt output
"""
import os
import sys

from bricks import stop
from check import read_program, snap
from world import World
from wrapper import wrap


def build(lines):
    """Check every line, then wrap the bricks. Returns (program bytes or None, refusals)."""
    world, bricks, refusals = World(), [], []
    for line in lines:
        brick, problem = snap(line, world)
        if problem:
            refusals.append(f"{line}\n    refused: {problem}")
        else:
            bricks.append(brick)
    if refusals:
        return None, refusals
    if world.running:
        bricks.append(stop())    # no stop written: stop cleanly anyway
    return wrap(bricks), []


def main():
    program, refusals = build(read_program(sys.argv[1]))
    if refusals:
        print("Not built. Fix these lines first:\n" + "\n".join(refusals))
        sys.exit(1)
    with open(sys.argv[2], "wb") as f:
        f.write(program)
    os.chmod(sys.argv[2], 0o755)
    print(f"Built {sys.argv[2]} ({len(program)} bytes).")


if __name__ == "__main__":
    main()
