import os

# Service constructors instantiate an OpenAI client at __init__ time (no
# network call happens until a request is actually made), so tests need a
# non-empty key present before those modules are imported. Setting dummy
# values here — before pytest collects any test module — keeps the test
# suite independent of the developer's real .env contents.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-not-real")
os.environ.setdefault("SEARCH_API_KEY", "test-dummy-search-key")
