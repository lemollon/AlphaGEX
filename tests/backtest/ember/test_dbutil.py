from backtest.ember.dbutil import db_cursor


class _FakeCursor:
    def __init__(self): self.closed = False
    def close(self): self.closed = True


class _FakeConn:
    def __init__(self): self.cursor_made = None; self.closed = False
    def cursor(self, cursor_factory=None): self.cursor_made = _FakeCursor(); return self.cursor_made
    def close(self): self.closed = True


def test_db_cursor_reuses_conn_and_does_not_close_it():
    fake = _FakeConn()
    with db_cursor(conn=fake) as cur:
        assert cur is fake.cursor_made
    assert fake.cursor_made.closed is True   # cursor closed
    assert fake.closed is False              # connection NOT closed (caller owns it)
