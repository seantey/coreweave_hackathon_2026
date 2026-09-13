"""Bake positive axis scaling into Gaussian centers and full covariances.

Use paired collider transforms for the same deformation. Appearance colors stay
unchanged; this operation does not establish physical dimensions or correctness.
"""
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation


def stretch_splat(source: Path, destination: Path, scales, anchor):
    scales = np.asarray(scales, dtype=float)
    anchor = np.asarray(anchor, dtype=float)
    if scales.shape != (3,) or anchor.shape != (3,) or not np.isfinite([scales, anchor]).all() or np.any(scales <= 0):
        raise ValueError('Expected three positive finite scales and a finite anchor')
    header = []
    fields = []
    count = None
    with source.open('rb') as stream:
        for _ in range(200):
            raw = stream.readline(); header.append(raw)
            line = raw.decode('ascii').strip()
            if line.startswith('format ') and line != 'format binary_little_endian 1.0':
                raise ValueError('Requires binary little-endian Gaussian PLY')
            if line.startswith('element vertex '): count = int(line.split()[-1])
            elif line.startswith('element '): raise ValueError('Only vertex elements are supported')
            if line.startswith('property '):
                _, kind, name = line.split()
                if kind != 'float': raise ValueError('Requires float32 Gaussian fields')
                fields.append((name, '<f4'))
            if line == 'end_header': break
        else: raise ValueError('Missing PLY header terminator')
        if not count: raise ValueError('No Gaussian vertices')
        data = np.fromfile(stream, dtype=np.dtype(fields), count=count)
        if len(data) != count or stream.read(1): raise ValueError('Unexpected PLY payload size')
    required = ['x','y','z',*[f'scale_{i}' for i in range(3)],*[f'rot_{i}' for i in range(4)]]
    if any(name not in data.dtype.names for name in required): raise ValueError('Missing Gaussian covariance fields')
    centers = np.column_stack([data[key] for key in ['x','y','z']])
    transformed = anchor + (centers-anchor)*scales
    for i,key in enumerate(['x','y','z']): data[key] = transformed[:,i]
    for start in range(0,count,20000):
        chunk=data[start:start+20000]
        # Gaussian PLY stores quaternion components in w,x,y,z order.
        quaternion=np.column_stack([chunk[f'rot_{i}'] for i in [1,2,3,0]])
        rotations=Rotation.from_quat(quaternion).as_matrix()
        std=np.exp(np.column_stack([chunk[f'scale_{i}'] for i in range(3)]).astype(float))
        basis=scales[None,:,None]*rotations*std[:,None,:]
        covariance=basis@basis.transpose(0,2,1)
        values,vectors=np.linalg.eigh(covariance)
        vectors[:,:,0] *= np.where(np.linalg.det(vectors)<0,-1.,1.)[:,None]
        quaternion=Rotation.from_matrix(vectors).as_quat()
        for i in range(3): chunk[f'scale_{i}']=np.log(np.maximum(values[:,i],1e-30))*.5
        for i,index in enumerate([3,0,1,2]): chunk[f'rot_{i}']=quaternion[:,index]
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('wb') as stream:
        stream.write(b''.join(header));data.tofile(stream)
    matrix=np.eye(4);matrix[:3,:3]=np.diag(scales);matrix[:3,3]=anchor*(1-scales)
    return {'gaussians':count,'matrix':matrix.reshape(-1,order='F').tolist(),'scales':scales.tolist(),'anchor':anchor.tolist()}
