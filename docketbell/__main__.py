"""Command-line entry point.

``docketbell <command>`` runs any Django management command, so a pip-installed
Docketbell can be operated without a ``manage.py`` file::

    docketbell migrate
    docketbell run_worker
    docketbell --version
"""

import os
import sys


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv if argv is None else argv)
    if len(argv) > 1 and argv[1] in {"--version", "-V"}:
        from docketbell.version import build_info

        print(build_info().label)
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "docketbell.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(argv)


if __name__ == "__main__":  # pragma: no cover
    main()
