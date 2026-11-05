"""Entry point for ``python -m gateway`` and for the packaged exe.

The PyInstaller build uses this file as its entry script, so the
resulting ``s7gateway`` executable runs exactly the same CLI as
``python -m gateway.cli`` (mock / browse / read-all / poll / write).
"""

from gateway.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
