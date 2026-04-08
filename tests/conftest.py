import pytest
from polyedge.db.schema import init_db

@pytest.fixture
def db():
    conn = init_db(":memory:")
    yield conn
    conn.close()