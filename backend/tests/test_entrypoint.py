from app.main import app as canonical_app
from main import app as compatibility_app


def test_render_entrypoints_resolve_to_the_same_application():
    assert compatibility_app is canonical_app
