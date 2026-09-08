import numpy as np
import pytest
from ui import viewport as vp

@pytest.fixture
def mesh(monkeypatch):
    monkeypatch.setattr(vp, 'glBindBuffer', lambda *a: None)
    monkeypatch.setattr(vp, 'glBufferSubData', lambda *a: None)
    m=vp.GpuSubMesh();m._pose_vertices=np.zeros((3,16),np.float32)
    m._pose_vertices[:,:3]=np.eye(3);m._pose_vertices[:,13:]=np.eye(3)
    return m

def pose(m, shift):
    return m._pose_vertices[:,:3]+shift,np.tile([0,1,0],(3,1)),np.tile([1,0,0,1],(3,1))

def test_pose_retains_last_rendered_positions_and_settles(mesh):
    old=mesh._pose_vertices[:,:3].copy();p,n,t=pose(mesh,.1)
    mesh.update_pose(p,n,t)
    np.testing.assert_array_equal(mesh._pose_vertices[:,13:],old)
    np.testing.assert_array_equal(mesh._pose_vertices[:,:3],p)
    mesh.settle_pose_history()
    np.testing.assert_array_equal(mesh._pose_vertices[:,13:],p)
    assert not mesh._pose_history_dirty
    p2,n,t=pose(mesh,.2);mesh.update_pose(p2,n,t)
    np.testing.assert_array_equal(mesh._pose_vertices[:,13:],p)

def test_captured_previous_pose_is_owned(mesh):
    p,n,t=pose(mesh,.2);prev=np.full((3,3),.7,np.float32)
    mesh.update_pose(p,n,t,previous_positions=prev);prev[:]=100
    np.testing.assert_allclose(mesh._pose_vertices[:,13:],.7)

@pytest.mark.parametrize('bad',[np.zeros((2,3)),np.full((3,3),np.nan)])
def test_invalid_pose_does_not_mutate_mesh(mesh,bad):
    old=mesh._pose_vertices.copy();_,n,t=pose(mesh,.2)
    with pytest.raises(ValueError):mesh.update_pose(bad,n,t)
    np.testing.assert_array_equal(mesh._pose_vertices,old)

def test_pose_queue_coalesces_without_touching_rendered_history(mesh):
    class View:
        _pending_model=None;_gpu_meshes=[mesh];_pending_poses={};_fur_scene_view=None
        def _trigger_repaint(self):pass
    view=View();first=pose(mesh,.1);last=pose(mesh,.2)
    vp.Viewport3D.set_deformed_pose(view,{0:first});vp.Viewport3D.set_deformed_pose(view,{0:last})
    np.testing.assert_array_equal(view._pending_poses[0][0],last[0])
    np.testing.assert_array_equal(mesh._pose_vertices[:,:3],np.eye(3))
