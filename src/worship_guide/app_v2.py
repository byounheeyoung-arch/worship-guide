"""Compatibility entrypoint; all launchers use the canonical application."""

from .app import WorshipGuide, main

WorshipGuide2 = WorshipGuide
if __name__ == "__main__":
    main()
