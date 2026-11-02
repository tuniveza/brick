"""The world: the console and everything in it. It is the referee."""


class World:
    def __init__(self):
        self.running = True
        self.colour = "normal"
        self.style = "plain"
        self.line = 1      # cursor line, counted from where the program starts (or the top after clear)
        self.saved = []    # names of the answers saved so far

    def check(self, brick):
        """Return None if the brick is allowed, or a friendly reason if not."""
        if not self.running:
            return "The program has already stopped. Move this line above 'stop', or remove 'stop'."
        return brick.find_problem(self)

    def add(self, brick):
        """Check the brick and, if it is allowed, update the world. Returns the refusal, if any."""
        problem = self.check(brick)
        if problem is None:
            brick.change_world(self)
        return problem

    def describe(self):
        state = "running" if self.running else "stopped"
        saved = ", ".join(self.saved) or "nothing"
        return (f"{state}; colour {self.colour}, style {self.style}; "
                f"cursor on line {self.line}; saved: {saved}")
