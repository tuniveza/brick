# Progress

## Where we are
Steps 1–3 are done. **Step 4: your turn to try it.**

## What works
- **The world** (`world.py`) keeps track of: running or stopped, colour, style,
  cursor line, and saved answers. It checks each brick before allowing it,
  and can describe itself in one line.
- **The shelf** (`bricks.py`) has 10 bricks: say, blank line, ask, colour,
  bold, plain, clear, beep, wait, stop. Each one states what it needs,
  what it changes and what it does, in plain English.
- **The machine pieces** (`machine.py`) are four frozen blocks of x86-64 bytes
  that all the bricks are built from: show text, show a saved answer,
  read an answer, end.
- **The wrapper** (`wrapper.py`) fills in the blanks (addresses and lengths)
  and wraps everything in an ELF file. The demo comes out at 1,485 bytes.
- **Refusals**: an unsaved [name], an unknown colour, an unknown line,
  anything after stop. If any line is refused, nothing gets built.
- If there's no `stop`, one is added at the end automatically.
- **Tests** (`test_bricks.py`) run each brick in a real pseudo-terminal and
  type answers like a person would. 5 tests, all passing.

## How to try it
    python3 check.py examples/good.txt               # see the world after each line
    python3 check.py examples/bad.txt                # see the refusals
    python3 build.py examples/demo.txt out/demo      # build
    ./out/demo                                       # run
    python3 test_bricks.py                           # run the tests

Write your own program as a `.txt` file, one brick per line. Lines starting
with `#` are notes and get skipped.

## Frozen (proven, don't rewrite)
The 10 bricks above and the 4 machine pieces.

## Limits right now
- An answer can be at most 256 bytes. Anything longer is left for the next question.
- `[name]` only works inside `say`, not inside `ask` questions.
- Phrasing is strict: `say "hello"` works, `say hello` doesn't.

## Next (when you say so)
- Loose English on top (pick out known words in order, ignore the rest).
- Numbers, loops, choices.

## For you to decide
- Should `[name]` also work inside `ask "..."` questions? (e.g. `ask "How old are you, [name]?" as age`)
- When a line is refused, should the tool also suggest the closest known brick
  (e.g. "colour pink" -> "did you mean purple?")?
