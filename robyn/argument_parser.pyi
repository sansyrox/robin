import argparse


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self) -> None:
        ...

    def num_processes(self):
        ...

    def workers(self):
        ...

    def is_dev(self):
        ...
