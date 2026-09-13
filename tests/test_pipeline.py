from backend import pipeline


def test_unapproved_source_stops_before_reconstruction(monkeypatch):
    monkeypatch.setattr(pipeline, 'completion_loop', lambda *args: {'accepted': False})
    def forbidden(*args):
        raise AssertionError('Unapproved source must not start reconstruction')
    monkeypatch.setattr(pipeline, 'reconstruct_completion', forbidden)
    result = pipeline.restore_room('source', 'run', 'scene', 'reference')
    assert result['status'] == 'needs_evidence'
