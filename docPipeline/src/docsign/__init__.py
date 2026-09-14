"""docsign — internal document signing and verification.

Answers exactly two questions about a document received from a colleague:
authenticity (did this person send it?) and integrity (has it changed since
they signed it?). This is *signing*, not encryption — the document stays
readable.
"""

__version__ = "0.1.0"
