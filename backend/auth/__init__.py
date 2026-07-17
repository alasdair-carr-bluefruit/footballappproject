"""Auth core for multi-user (v1.1): one-time tokens, signed session cookies, and
the magic-link email sender. No passwords/PINs — an AccountDB row is the identity
and every credential path issues the same signed session (see V1_MULTIUSER_PLAN.md §2).
"""
