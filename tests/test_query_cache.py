from app.services.query_cache import QueryCache


class TestNormalizeKey:
    def test_lowercases_and_collapses_whitespace(self):
        assert QueryCache.normalize_key("  Best   Pizza  ") == "best pizza"


class TestGetSet:
    def test_round_trips_a_value(self):
        cache = QueryCache()
        cache.set("some query", {"result": 42})
        assert cache.get("some query") == {"result": 42}

    def test_get_is_case_and_whitespace_insensitive(self):
        cache = QueryCache()
        cache.set("Best Pizza", "value")
        assert cache.get("  best   pizza  ") == "value"

    def test_missing_key_returns_none(self):
        cache = QueryCache()
        assert cache.get("never set") is None


class TestTtlExpiry:
    def test_expired_entry_is_evicted_on_read(self):
        cache = QueryCache(ttl_seconds=0)
        cache.set("query", "value")
        assert cache.get("query") is None


class TestEviction:
    def test_oldest_entry_is_evicted_when_over_capacity(self):
        cache = QueryCache(max_entries=2)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.get("a")  # touch "a" so "b" becomes the least-recently-used
        cache.set("c", "3")

        assert cache.get("a") == "1"
        assert cache.get("b") is None
        assert cache.get("c") == "3"


class TestClear:
    def test_clear_empties_the_cache(self):
        cache = QueryCache()
        cache.set("query", "value")
        cache.clear()
        assert cache.get("query") is None
