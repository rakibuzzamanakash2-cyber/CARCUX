"""CARCUX-J24: building a multi-source claim dataset from Bangladesh's July–August 2024
uprising (protocol: research/j24/PROTOCOL.md).

This package does the first, mechanical step: it indexes the fact-checks that
recognised fact-checking organisations published in the study window, records which
outlets each one cites, and prepares a sheet in which a person restates each claim
and confirms its verdict. It never decides whether a claim is true: the verdict is the
fact-checker's, and a person confirms it from the article.

What it stores, by design:

- for each fact-check: its link, dates, title (at most 300 characters), category names,
  the verdict words found in it (a hint for the person, not a label), and the domains
  it links to, grouped by kind (news outlet, official site, social platform, archive);
- links to social media posts only in a separate `restricted/` folder, because they
  can lead to private individuals; the public files hold a salted hash instead;
- never the article body, never post text, never a person's name or handle.
"""

WINDOW = ("2024-07-01", "2024-08-15")  # the OHCHR report's period, 1 July–15 August 2024
