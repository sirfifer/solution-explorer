# March UnaMentis sample fixture

This directory contains the tracked March 2026 sample for
`https://github.com/UnaMentis/unamentis`. It is historical GUI test data, not
an active demo projection and not the UnaMentis iOS repository.

It was moved out of `viewer/public` so Vite cannot bake it into production
builds or silently serve it when a requested projection is unavailable.
Production and review bundles must be assembled with an explicit projection
using `scripts/assemble-serve.py`.
