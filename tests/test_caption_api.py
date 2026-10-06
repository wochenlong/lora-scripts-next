from mikazuki.app.api import router


def test_caption_and_shared_llm_routes_are_registered():
    paths = {route.path for route in router.routes}
    assert "/llm/profiles" in paths
    assert "/llm/config" in paths
    assert "/llm/connection-test" in paths
    assert "/llm/local-vision/manifest" in paths
    assert "/tagger/jobs" in paths
    assert "/tagger/jobs/preview" in paths
    assert "/tagger/jobs/cancel" in paths
    assert "/tagger/jobs/retry-failed" in paths
