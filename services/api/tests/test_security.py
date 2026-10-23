from __future__ import annotations

from onestats.core import security


def test_hash_and_verify_password():
    h = security.hash_password("correct horse battery staple")
    assert security.verify_password(h, "correct horse battery staple")
    assert not security.verify_password(h, "wrong password")


def test_password_hash_is_salted_unique():
    assert security.hash_password("same") != security.hash_password("same")


def test_verify_bad_hash_is_false_not_error():
    assert security.verify_password("not-a-valid-hash", "x") is False


def test_tokens_unique_and_hash_stable():
    t1, t2 = security.generate_token(), security.generate_token()
    assert t1 != t2
    assert len(t1) >= 32
    assert security.hash_token("abc") == security.hash_token("abc")
    assert security.hash_token("abc") != security.hash_token("abd")


def test_constant_time_compare():
    assert security.tokens_equal(security.hash_token("a"), security.hash_token("a"))
    assert not security.tokens_equal(security.hash_token("a"), security.hash_token("b"))
