# Console Brick System: Build Spec

## What this is
A tool that turns plain English into a raw Linux program. No C, no compiler,
no programming language in between. Words point at frozen blocks of machine
bytes ("bricks"). The bricks live inside a "world" that knows what exists and
decides what's allowed.

This spec covers the **console only**, on **Linux x86-64** (CachyOS).
Goal: get a small working version so the owner can see the idea function.

## The owner
Directs and decides; doesn't write code. Explain what you did in plain
English after each step. **Simplicity is a hard constraint**: small files,
short functions, plain names, readable in one sitting.

## The three parts
1. **The world (the referee).** The console and everything in it:
   - is it running or stopped
   - current colour and style
   - where the cursor is
   - which answers are saved (memory)
   It checks every brick before allowing it and updates itself after.
   It can say what exists right now in one plain-English line.

2. **The bricks (the shelf).** Each brick says three things:
   - **Needs**: what must be true first (e.g. "say hi [name]" needs `name` saved)
   - **Changes**: what it changes in the world
   - **Does**: what it does on screen
   If a need isn't met, refuse with a friendly English message that says
   what to do instead.

3. **The wrapper.** Turns the finished bricks into machine bytes, fills in
   the blanks (addresses, lengths), and wraps them in a minimal ELF file
   you can run. Raw Linux syscalls only (write, read, exit). No libc.

## First bricks
| Brick | Needs | Changes | Does |
|---|---|---|---|
| say "text" | running; any [name] saved | cursor to next line | shows text |
| blank line | running | cursor to next line | empty line |
| ask "question" as name | running | saves name | asks, waits for answer |
| colour red/green/... | running; known colour | colour | next text in that colour |
| bold | running | style | next text bold |
| plain | running | colour and style reset | back to normal |
| clear | running | cursor to top | wipes the screen |
| beep | running | nothing | terminal beep |
| wait | running | cursor to next line | "Press Enter to continue..." |
| stop | running | stopped (resets colours first) | ends program |

Default: if the program doesn't say stop, it stops cleanly anyway.

## Build order (one step at a time; show the owner each one working)
1. Build the world and the bricks, with no bytes yet. Snap a few bricks
   together and print the world's state after each one. Show it refusing
   bad moves (a name before it's asked for, an unknown colour,
   anything after stop).
2. Add the wrapper. Build a demo program from bricks and run it.
3. Add a test that builds and runs the demo. Use a pseudo-terminal for
   typed input, because piped input can arrive as several lines at once.
4. Stop and let the owner try it.

## Rules
- Bricks are frozen once they're proven. Add new ones; don't rewrite old ones.
- Every new brick gets a test that actually runs it.
- Correct first. Speed tricks come later and must never change behaviour.

## Later (not now)
- Loose English on top: pick out known words in order, ignore the rest
  ("computer, can you make it say hello twice").
- Numbers, loops, choices.
- Same words with different bricks per platform (Mac, Windows, Android).
- Other worlds: GUI, game, music. Same shape: things, needs, changes, does.
