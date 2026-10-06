"""Compatibility entrypoint for older shortcuts."""

from .app import WorshipGuide, main

App = WorshipGuide
if __name__ == "__main__":
    main()
