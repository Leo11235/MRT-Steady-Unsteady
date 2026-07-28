"""Cross-cutting services used by more than one page.

Every module here is:
  - stateless-ish (any state is memoised / cached, not user-facing),
  - free of Tk / customtkinter widget code where possible,
  - imported by pages and widgets, not the other way around.
"""
