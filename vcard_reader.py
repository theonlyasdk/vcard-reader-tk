#!/usr/bin/env python
"""vcard-reader-tk - simple two-pane vCard (.vcf) reader."""

import sys
from pathlib import Path

if sys.platform.startswith('win'):
    try:
        if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from ui import MainWindow
from ui.dpi import enable_dpi_awareness
enable_dpi_awareness()


def main(argv=None):
    path = None
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        candidate = Path(args[0])
        if candidate.is_file():
            path = str(candidate)
    app = MainWindow(initial_file=path)
    app.run()


if __name__ == '__main__':
    main()
