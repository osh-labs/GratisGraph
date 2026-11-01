"""One module per CLI subcommand; each exposes add_arguments(parser) and run(args) -> int.

cli.py only parses arguments and dispatches, so each slice owns its command
module and no two slices edit the same file.
"""
