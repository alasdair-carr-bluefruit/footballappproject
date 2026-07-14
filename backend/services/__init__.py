"""Service layer — orchestration extracted from the API routers (Phase C.5).

Routers stay thin HTTP adapters (parse body, translate errors to status codes,
shape responses); repositories keep the raw queries; these services own the
multi-step orchestration that sits between them — building the right game
config, running and persisting a rotation, and reconstructing a stored plan for
in-match edits. Keeping it here means the logic is exercised once and can be
tested without spinning up the full HTTP stack.
"""
