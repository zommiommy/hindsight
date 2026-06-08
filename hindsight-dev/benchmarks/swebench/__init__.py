"""SWE-bench memory study: does a coding agent do better *with* Hindsight than without?

See README.md for the methodology. The headline metric is *efficiency at equal quality*:
tokens, agent steps, and wall-clock should drop as a memory-backed agent works consecutive
tasks on the same codebase, at equal-or-better resolve rate.
"""
