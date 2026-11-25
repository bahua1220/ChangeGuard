import pytest

from repolens.demo import create_demo
from repolens.mining import analysis_spec, inspect_repository, mine


@pytest.fixture(scope="session")
def demo_path(tmp_path_factory):
    return create_demo(tmp_path_factory.mktemp("git-fixtures") / "atlas")


@pytest.fixture(scope="session")
def snapshot(demo_path):
    info = inspect_repository(demo_path)
    return mine(analysis_spec(info, info["current"], 300, False))
