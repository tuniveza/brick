"""The shelf: every brick the system knows, and how to read one from a line of English."""
import re

from machine import end, read_answer, show, show_answer

COLOURS = {"red": 31, "green": 32, "yellow": 33, "blue": 34,
           "purple": 35, "cyan": 36, "white": 37, "grey": 90}
RESET = "\x1b[0m"


class Brick:
    def __init__(self, words, needs, changes, does, find_problem=None, change_world=None, parts=()):
        self.words = words            # the line as written
        self.needs = needs            # plain English: what must be true first
        self.changes = changes        # plain English: what it changes in the world
        self.does = does              # plain English: what it does on screen
        self.find_problem = find_problem or (lambda world: None)
        self.change_world = change_world or (lambda world: None)
        self.parts = list(parts)      # machine-byte pieces, in order


def next_line(world):
    world.line += 1


def say(text):
    names = re.findall(r"\[(\w+)\]", text)

    def find_problem(world):
        for name in names:
            if name not in world.saved:
                return f'Nothing called [{name}] is saved yet. Add  ask "..." as {name}  above this line.'

    # "Hi [name]!" splits into "Hi ", "name", "!" -- text and saved answers taking turns.
    parts = []
    for i, bit in enumerate(re.split(r"\[(\w+)\]", text)):
        if i % 2:
            parts.append(show_answer(bit))
        elif bit:
            parts.append(show(bit))
    parts.append(show("\n"))
    return Brick(f'say "{text}"', "running; any [name] saved", "cursor to next line",
                 f'shows "{text}"', find_problem, next_line, parts)


def blank_line():
    return Brick("blank line", "running", "cursor to next line", "prints an empty line",
                 change_world=next_line, parts=[show("\n")])


def ask(question, name):
    def change_world(world):
        if name not in world.saved:
            world.saved.append(name)
        world.line += 1

    return Brick(f'ask "{question}" as {name}', "running", f"saves {name}",
                 f'asks "{question}" and waits for an answer', change_world=change_world,
                 parts=[show(question + " "), read_answer(name)])


def colour(name):
    def find_problem(world):
        if name not in COLOURS:
            return f"I don't know the colour '{name}'. Try one of: {', '.join(COLOURS)}."

    def change_world(world):
        world.colour = name

    parts = [show(f"\x1b[{COLOURS[name]}m")] if name in COLOURS else []
    return Brick(f"colour {name}", "running; a known colour", "colour",
                 f"next text in {name}", find_problem, change_world, parts)


def bold():
    def change_world(world):
        world.style = "bold"

    return Brick("bold", "running", "style", "next text bold",
                 change_world=change_world, parts=[show("\x1b[1m")])


def plain():
    def change_world(world):
        world.colour, world.style = "normal", "plain"

    return Brick("plain", "running", "colour and style reset", "back to normal text",
                 change_world=change_world, parts=[show(RESET)])


def clear():
    def change_world(world):
        world.line = 1

    return Brick("clear", "running", "cursor to the top", "wipes the screen",
                 change_world=change_world, parts=[show("\x1b[2J\x1b[H")])


def beep():
    return Brick("beep", "running", "nothing", "terminal beep", parts=[show("\a")])


def wait():
    # The pressed keys go into a box no plain name can reach (names can't contain spaces).
    return Brick("wait", "running", "cursor to next line",
                 '"Press Enter to continue..." and pauses', change_world=next_line,
                 parts=[show("Press Enter to continue..."), read_answer("wait box")])


def stop():
    def change_world(world):
        world.colour, world.style = "normal", "plain"
        world.running = False

    return Brick("stop", "running", "stopped (colours reset first)", "ends the program",
                 change_world=change_world, parts=[show(RESET), end()])


# Each pattern is matched against a whole line; the bracketed parts are handed to the brick maker.
SHELF = [
    (r'say "(.*)"', say),
    (r"blank line", blank_line),
    (r'ask "(.*)" as (\w+)', ask),
    (r"colou?r (\w+)", colour),
    (r"bold", bold),
    (r"plain", plain),
    (r"clear", clear),
    (r"beep", beep),
    (r"wait", wait),
    (r"stop", stop),
]

KNOWN = 'say "text", blank line, ask "question" as name, colour red, bold, plain, clear, beep, wait, stop'


def brick_from_line(line):
    """Return the brick this line asks for, or None if no brick matches."""
    for pattern, make in SHELF:
        found = re.fullmatch(pattern, line.strip())
        if found:
            return make(*found.groups())
    return None
