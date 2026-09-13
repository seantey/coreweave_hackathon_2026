import json
import numpy as np
import trimesh
from PIL import Image
from backend import storage, surface_repair
from backend.models import Scene,Asset,Bounds,Camera,Revision


def test_planar_candidate_preserves_source_and_unselected_vertices(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);monkeypatch.setattr(surface_repair,'DATA',tmp_path)
    vertices=np.array([[x,-.2-.05*j,-1-.5*j] for j in range(3) for x in [-.4,0,.4]])
    faces=[]
    for j in range(2):
        for i in range(2):
            k=j*3+i;faces.extend([[k,k+1,k+3],[k+1,k+4,k+3]])
    source=tmp_path/'source.glb';trimesh.Trimesh(vertices=vertices,faces=faces,process=False).export(source)
    original=source.read_bytes()
    scene=Scene(id='office-test',title='Geometry unit test',description='Synthetic unit geometry',assets=[Asset(id='surface',label='Surface',kind='mesh',path='source.glb',collider_path='source.glb')],bounds=Bounds(minimum=(-2,-2,-3),maximum=(2,2,1)),cameras={'Forward':Camera(position=(0,0,0),target=(0,0,-1))},revisions=[Revision(id='original',label='Baseline',status='baseline',created_at='test')],current_revision='original')
    storage.save_scene(scene)
    matrix=np.array([[1,0,0,0],[0,1,0,0],[0,0,-1.02,-.202],[0,0,-1,0]])
    storage.write_json(tmp_path/'camera.json',{'scene_id':scene.id,'revision_id':'original','camera_matrix':np.eye(4).reshape(-1,order='F').tolist(),'projection_matrix':matrix.reshape(-1,order='F').tolist(),'viewport':[100,100]})
    mask=np.zeros((100,100),np.uint8);mask[:,:50]=255;Image.fromarray(mask).save(tmp_path/'mask.png')
    result=surface_repair.propose_planar_surface(scene.id,'surface','mask.png','camera.json','Forward',-.3,'Test a reviewed planar correction',['Synthetic test selection'])
    assert result['selected_vertices']==3
    assert result['unselected_vertices_unchanged']
    assert result['after_height_range']<1e-12
    assert source.read_bytes()==original
    saved=storage.read_scene(scene.id)
    assert saved.current_revision=='original'
    assert saved.revisions[-1].status=='candidate'


def test_splat_placement_rejects_nonuniform_root_scale():
    import pytest
    from backend.models import Edit,Transform,validate_edit
    scene=Scene(id='scale-test',title='Scale validation',description='Synthetic validation',assets=[Asset(id='splat',label='Splat',kind='splat',path='object.ply',initially_visible=False)],bounds=Bounds(minimum=(-2,-2,-2),maximum=(2,2,2)),cameras={'Front':Camera()},revisions=[Revision(id='original',label='Baseline',status='baseline',created_at='test')],current_revision='original')
    edit=Edit(id='placement',operation='place_asset',asset_id='splat',transform=Transform(scale=(1,2,1)),reason='Test paired transform correctness',evidence=['Synthetic test'])
    with pytest.raises(ValueError,match='uniform scale'):
        validate_edit(scene,edit)
