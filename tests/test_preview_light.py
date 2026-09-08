from types import SimpleNamespace
import numpy as np
import pytest
from ui.viewport import Viewport3D


def test_relighting_normalizes_copies_and_invalidates_history():
    events = []
    state = SimpleNamespace(_preview_light_direction=(0.6, 1., .8),
        _reset_temporal_history=lambda: events.append('reset'),
        _redraw=lambda: events.append('redraw'))
    supplied = np.array([0., 3., 4.])
    Viewport3D.set_preview_light_direction(state, supplied)
    supplied[:] = 0
    assert state._preview_light_direction == (0., .6, .8)
    assert events == ['reset', 'redraw']
    Viewport3D.set_preview_light_direction(state, [0., 3., 4.])
    assert events == ['reset', 'redraw']


@pytest.mark.parametrize('direction', [[0,0,0], [1,2], [1,2,float('nan')], [float('inf'),0,0]])
def test_invalid_direction_leaves_previous_light_intact(direction):
    state = SimpleNamespace(_preview_light_direction=(0., 1., 0.))
    with pytest.raises(ValueError):
        Viewport3D.set_preview_light_direction(state, direction)
    assert state._preview_light_direction == (0., 1., 0.)
