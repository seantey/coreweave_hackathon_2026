from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from backend.splat_deformation import stretch_splat


def test_stretch_preserves_covariance_and_appearance(tmp_path):
    names=['x','y','z','opacity','f_dc_0','f_dc_1','f_dc_2',*[f'scale_{i}' for i in range(3)],*[f'rot_{i}' for i in range(4)]]
    data=np.zeros(1,dtype=[(n,'<f4') for n in names])
    data['x']=2;data['y']=3;data['z']=4;data['opacity']=.7;data['f_dc_0']=.2
    std=np.array([.1,.3,.2]);rotation=Rotation.from_euler('xyz',[.4,.6,.8]);q=rotation.as_quat()
    for i in range(3):data[f'scale_{i}']=np.log(std[i])
    for i,index in enumerate([3,0,1,2]):data[f'rot_{i}']=q[index]
    header=('ply\nformat binary_little_endian 1.0\nelement vertex 1\n'+''.join(f'property float {n}\n' for n in names)+'end_header\n').encode()
    source=tmp_path/'source.ply';source.write_bytes(header+data.tobytes());original=source.read_bytes()
    output=tmp_path/'result.ply';stretch_splat(source,output,[1,2,1],[0,1,0])
    result=np.frombuffer(output.read_bytes()[len(header):],dtype=data.dtype)
    assert source.read_bytes()==original
    assert [result[n][0] for n in ['x','y','z']]==[2,5,4]
    assert result['opacity'][0]==data['opacity'][0]
    assert result['f_dc_0'][0]==data['f_dc_0'][0]
    qr=np.array([result[f'rot_{i}'][0] for i in [1,2,3,0]])
    rr=Rotation.from_quat(qr).as_matrix();sr=np.exp([result[f'scale_{i}'][0] for i in range(3)])
    actual=rr@np.diag(sr**2)@rr.T
    affine=np.diag([1,2,1]);expected=affine@rotation.as_matrix()@np.diag(std**2)@rotation.as_matrix().T@affine
    np.testing.assert_allclose(actual,expected,rtol=1e-5,atol=1e-7)
