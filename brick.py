"""Turn a plain-English file into a runnable Linux program.

  brick game.txt              makes ./game and runs it (brick game works too); a program
                              that uses window words (put the window on the left...) gets
                              a console window of its own
  brick window game.txt       makes it and runs it in a new console window
  brick here game.txt         makes it and runs it right here, in this terminal
  brick build game.txt        only makes ./game
  brick gui                   a window to write, run and watch it being made (brick gui game.txt)
                              brick gui --app: in a window of its own (what the brick launcher opens)
  brick export game.txt       writes game.brick: the program and everything brick made from it,
                              as plain text, to give to Claude to read (Save .brick in brick gui)
  brick bits game.txt         writes the program as brick materials, next to game.txt (Save bits in
                              brick gui): game.sand  the bare 1s and 0s, one unbroken stream
                                          game.clay  the 1s and 0s row by row, each stretch labelled
                                          game.shale the same rows in hex
                                          game.cement the actual program file, byte for byte (it runs)
                              brick sand game.txt (or clay, shale, cement) writes just that one
  brick neural setup          the neural reader: a language model on this computer (Ollama, started and
                              stopped with brick) that suggests readings brick isn't sure of. brick neural:
                              is it ready; brick neural off / on; brick neural model qwen2.5:7b
  brick scramble 10           10 broken, errored paragraphs of directions, and how brick did with each
                              (the factory practises on these by itself while brick runs)
  brick review game.txt       the lines brick had to guess in game.txt: say if they're right, or fix them.
                              brick also asks after each run ("Did it do what you meant?")
  brick help                  every phrase it understands
  brick help dictionary       every everyday word it knows, and what each means here
                              (brick help dictionary colours: just one group)
  brick factory               the factory: it makes and watches directions, and teaches the dictionary
                              and the textual universe. It runs by itself while brick gui is open or a
                              program runs here; brick factory runs it in this terminal, to watch it
  brick factory always / off  keep it running all the time, or stop that (brick factory status)
  brick factory learn x.brick learn from these files now
  brick director              the English Director: scrambles a batch of directions and reports what brick
                              gets wrong (texts/director-report.txt). With Claude Code installed, Claude
                              then fixes brick's code for them (instructions: texts/director.txt)
  brick feeder                the dictionary feeder: a batch of learning now, checked by the tests. With
                              Claude Code installed, Claude also settles words that need judgement
"""
import os
import shutil
import subprocess
import sys

import dictionary
from actions import help_text
from compiler import Compiler
from expressions import Problem

# How to open a new console window with each terminal app: (app, its id for the window, its title, command)
TERMINALS = [
    ("kitty", lambda name, title, command: ["kitty", "--class", name] + command),
    ("foot", lambda name, title, command: ["foot", "--app-id", name, "--title", title] + command),
    ("alacritty", lambda name, title, command: ["alacritty", "--class", name, "--title", title, "-e"] + command),
    ("wezterm", lambda name, title, command: ["wezterm", "start", "--class", name, "--"] + command),
    ("konsole", lambda name, title, command: ["konsole", "-e"] + command),
    ("gnome-terminal", lambda name, title, command: ["gnome-terminal", "--title", title, "--"] + command),
    ("xterm", lambda name, title, command: ["xterm", "-class", name, "-T", title, "-e"] + command),
]
# Runs the program, then keeps the window open until Enter, so its last words can be read.
# Then asks about any lines brick had to guess (brick review --ask), if it knows the program's .txt.
STAY_OPEN = '"$0"; [ -n "$3" ] && "$1" "$2" review --ask "$3"; ' \
            'printf "\\n(Finished. Press Enter to close this window.)"; read _'


def find_source(name):
    """game.txt, or game -> game.txt. None if there's no such file."""
    for path in (name, name + ".txt"):
        if os.path.isfile(path):
            return path
    return None


def build(source, output):
    """Returns the compiler if it built, else None."""
    with open(source, encoding="utf-8", errors="replace") as f:
        text = f.read()
    compiler = Compiler()
    import factory
    try:
        program = compiler.compile(text)
    except Problem as problem:
        print(f"Not built. Fix these first:\n{problem}")
        print("\n".join(compiler.notes), end="\n" if compiler.notes else "")
        factory.after_build(text, compiler, str(problem), os.path.basename(source))   # brick keeps working on it
        return None
    factory.after_build(text, compiler, where=os.path.basename(source))      # what it fixed, it learns to keep
    print("\n".join(compiler.notes), end="\n" if compiler.notes else "")     # likely typos: it still builds
    if os.path.isdir(output):
        print(f"Not built: there's already a folder called {output}. Rename the .txt file or the folder.")
        return None
    with open(output, "wb") as f:
        f.write(program)
    os.chmod(output, 0o755)
    again = output if "/" in output else "./" + output
    print(f"Built {output} ({len(program):,} bytes). Run it again any time with: {again}", flush=True)
    return compiler


def open_window(program, title, source=None):
    """Run the program in a new console window. Returns False if there's no way to open one.
    source: its .txt, so the window can ask afterwards about lines brick had to guess."""
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        return False
    for app, command in TERMINALS:
        if shutil.which(app):
            name = f"brick-{os.getpid()}"
            env = dict(os.environ, BRICK_WINDOW=f"class:^{name}$")     # tells the program which window is its own
            asks = [sys.executable, os.path.abspath(__file__), os.path.abspath(source) if source else ""]
            subprocess.Popen(command(name, title, ["sh", "-c", STAY_OPEN, program] + asks), env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            print(f"Opened {title} in its own {app} window.")
            return True
    return False


def run_here(program):
    try:
        return subprocess.run([program]).returncode
    except KeyboardInterrupt:
        return 130


SERVICE = "brick-factory.service"
UNIT = """[Unit]
Description=brick's factory: the dictionary and textual universe, learning all the time

[Service]
WorkingDirectory={here}
ExecStart={python} {here}/factory.py --quiet
Restart=on-failure

[Install]
WantedBy=default.target
"""


def factory_command(args):
    """brick factory: run it here; always / off: keep it running all the time, or stop that; status."""
    import factory
    here = os.path.dirname(os.path.abspath(__file__))
    if not args:
        return factory.main([])
    if args[0] == "learn":
        return factory.main(args)
    if args[0] in ("always", "off"):
        unit = os.path.expanduser(f"~/.config/systemd/user/{SERVICE}")
        if args[0] == "always":
            os.makedirs(os.path.dirname(unit), exist_ok=True)
            with open(unit, "w") as f:
                f.write(UNIT.format(here=here, python=sys.executable))
            subprocess.run(["systemctl", "--user", "daemon-reload"])
        done = subprocess.run(["systemctl", "--user", "enable" if args[0] == "always" else "disable", "--now", SERVICE],
                              capture_output=True, text=True)
        if done.returncode != 0 and args[0] == "always":
            print(f"Couldn't keep it running: {done.stderr.strip()}")
            sys.exit(1)
    elif args[0] != "status":
        print(__doc__)
        sys.exit(1)
    always = subprocess.run(["systemctl", "--user", "is-enabled", "--quiet", SERVICE]).returncode == 0
    print("The factory is " + ("ON all the time (brick factory off to stop that)." if always else
                               "on while brick runs (brick gui, or a program running here)."))
    print("Right now it's " + ("running." if factory.running() else "not running."))
    log = os.path.join(factory.FOLDER, "log.txt")
    if os.path.isfile(log):
        with open(log, encoding="utf-8") as f:
            learned = [line.split("learned: ", 1)[1] for line in f if "learned: " in line]
        print(f"It has learned {len(learned)} words" + (": " + "; ".join(learned[-5:]) if learned else "."))
    if os.path.isfile(factory.POOL):
        with open(factory.POOL, encoding="utf-8", errors="replace") as f:
            print(f"sentence pool: {sum(1 for _ in f):,} lines in {factory.POOL}")
    import outliers
    print(f"waiting for you to decide: {len(outliers.entries())} (the Decisions tab in brick gui)")


TOOLS = ["Read", "Edit", "Write", "Grep", "Glob"] + [f"Bash({c}:*)" for c in (
    "python3", "mkdir", "ls", "cat", "head", "tail", "grep", "shuf", "cmp", "printf", "echo", "cd", "timeout", "wc")]


def helper(name, focus):
    """brick director / brick feeder. brick does its own half first: the feeder learns a batch of words
    (the factory); the director scrambles a batch of directions and reports what brick gets wrong. Then, if
    Claude Code is installed, Claude does what takes judgement, following texts/<name>.txt: fixing brick's
    code (director), or words brick couldn't settle (feeder). Without it, brick's own half still runs."""
    here = os.path.dirname(os.path.abspath(__file__))
    title = {"director": "The English Director", "feeder": "The dictionary feeder"}[name]
    print(f"{title} is working...", flush=True)
    if name == "feeder":
        import factory
        if not factory.only_one():
            print("The factory is running alongside brick right now, and already does this all the time "
                  "(brick factory status).")
            own = "The factory was busy, so brick's own half ran in the background instead."
        else:
            own = factory.Factory(quiet=True).feed(int(focus[0]) if focus and focus[0].isdigit() else 20)
    else:
        import scrambler
        own = scrambler.findings(int(focus[0]) if focus and focus[0].isdigit() else 40)
    print(own, flush=True)
    report = own
    if shutil.which("claude"):
        with open(os.path.join(here, "texts", f"{name}.txt"), encoding="utf-8") as f:
            instructions = f.read()
        asked = instructions + (f"\n\nFocus this batch on: {' '.join(focus)}" if focus else "") + \
            f"\n\nbrick's own half just ran and found this:\n\n{own}\n\nRun one batch now, starting from those findings."
        print("\nClaude Code is installed, so Claude now takes it from there. That takes a while...", flush=True)
        done = subprocess.run(["claude", "-p", asked, "--permission-mode", "acceptEdits", "--allowedTools", *TOOLS],
                              cwd=here, capture_output=True, text=True)
        if done.returncode == 0 and done.stdout.strip():
            print(done.stdout.strip())
            report += "\n\nClaude's part:\n" + done.stdout.strip()
        else:
            print(f"Claude stopped early: {done.stderr.strip() or 'no report'}")
    else:
        print("\n(With Claude Code installed, Claude would also " +
              ("fix brick's code for these." if name == "director" else "settle the words that need judgement.") + ")")
    with open(os.path.join(here, "texts", f"{name}-report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")


def main():
    args = sys.argv[1:]
    if args[:1] == ["factory"]:
        return factory_command(args[1:])
    if args[:1] == ["neural"]:
        import neural
        return neural.command(args[1:])
    if args[:1] == ["scramble"]:
        import scrambler
        return scrambler.main(args[1:])
    if args[:1] == ["review"] and len(args) in (2, 3):
        import review
        source = find_source(args[-1])
        if source is None:
            print(f"I can't find {args[-1]} in {os.getcwd()}.")
            sys.exit(1)
        return review.ask(source) if args[1] == "--ask" else review.panel(source)
    if args[:1] in (["director"], ["feeder"]):
        return helper(args[0], args[1:])
    if args[:2] == ["help", "dictionary"] or args[:1] == ["dictionary"]:
        print(dictionary.listing(args[2:] if args[0] == "help" else args[1:]))
        return
    if args[:1] == ["gui"]:
        import factory
        import gui
        factory.start_alongside(os.getcwd())          # it learns while the window is open, and stops with it
        return gui.main(args[1:])
    if args[:1] == ["export"] and len(args) == 2:
        import gui
        source = find_source(args[1])
        if source is None:
            print(f"I can't find {args[1]} in {os.getcwd()}. Check the name, or cd to its folder first.")
            sys.exit(1)
        with open(source, encoding="utf-8", errors="replace") as f:
            text = f.read()
        where = gui.brick_path(os.path.abspath(source), os.getcwd())
        with open(where, "w", encoding="utf-8") as f:
            f.write(gui.export(text, os.path.abspath(source)))
        print(f"Wrote {where}. Give it to Claude and ask what the program is about.")
        return
    if args[:1] in (["bits"], ["sand"], ["clay"], ["shale"], ["cement"]) and len(args) == 2:
        import gui
        source = find_source(args[1])
        if source is None:
            print(f"I can't find {args[1]} in {os.getcwd()}. Check the name, or cd to its folder first.")
            sys.exit(1)
        with open(source, encoding="utf-8", errors="replace") as f:
            text = f.read()
        kinds = tuple(gui.MATERIALS) if args[0] == "bits" else (args[0],)
        written = gui.write_materials(text, os.path.abspath(source), os.getcwd(), kinds)
        if written is None:
            print(f"{args[1]} didn't build, so there are no bits to write. Try brick build {args[1]} to see why.")
            sys.exit(1)
        for where, kind in zip(written, kinds):
            print(f"Wrote {where}: {gui.MATERIALS[kind]}.")
        return
    if args[:1] in (["help"], ["words"], ["--help"], ["-h"]):
        print(help_text())
        return
    if len(args) == 1:
        args.insert(0, "run")
    if len(args) < 2 or args[0] not in ("build", "run", "window", "here"):
        print(__doc__)
        sys.exit(1)
    source = find_source(args[1])
    if source is None:
        print(f"I can't find {args[1]} in {os.getcwd()}. Check the name, or cd to its folder first.")
        sys.exit(1)
    output = args[2] if len(args) > 2 else os.path.splitext(source)[0]
    if output == source:
        output += ".program"
    compiler = build(source, output)
    if compiler is None:
        sys.exit(1)
    program = os.path.abspath(output)
    if args[0] == "window" or args[0] == "run" and compiler.uses_window:
        if open_window(program, os.path.basename(output), source):
            return
        print("(No graphical desktop here, so it runs in this terminal instead.)")
    if args[0] != "build":
        import factory
        factory.start_alongside(os.path.dirname(program))
        code = run_here(program)
        import review
        review.ask(source)                       # did brick's guesses mean what you meant?
        sys.exit(code)


if __name__ == "__main__":
    main()
