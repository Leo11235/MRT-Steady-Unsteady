"""Single-source-of-truth for the app version string.

Bump this every time you cut a new release.  Two other places also need
to match by hand:
  - installer.iss   #define AppVersion "..."
  - README.md badges/text (if any explicit version there)

We keep them separate so a version bump can go through code review the
same way a normal edit does.
"""

VERSION = "1.4"
