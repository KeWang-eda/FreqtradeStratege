"""Sparse history retains endpoints and never selects by labels."""
import numpy as np
import pytest

from tools.run_direction_sparse_history_control import sparse_positions

pytestmark=pytest.mark.unit_contract


def test_fixed_344_positions_cover_same_span():
    positions=sparse_positions(1042)
    assert len(positions)==len(np.unique(positions))==344
    assert positions[0]==0 and positions[-1]==1041
    assert set(np.diff(positions))=={3,4}
    np.testing.assert_array_equal(positions,np.rint(np.linspace(0,1041,344)).astype(int))


@pytest.mark.parametrize('n,size',[(343,344),(10,1)])
def test_invalid_sizes_fail(n,size):
    with pytest.raises(ValueError): sparse_positions(n,size)
