"""Shared library for lz-feeds scripts.

Public modules:
    http         — fetch_url wrapper around curl
    parsing      — parse_date, strip_html, make_snippet (pure text helpers)
    models       — dataclasses describing the inter-script data contract
    feed_parser  — RSS/Atom parsing and blog-page link extraction
"""
