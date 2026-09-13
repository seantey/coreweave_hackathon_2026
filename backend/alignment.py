"""Empirically compare SAM coordinate conventions before aligning mesh and splat.

This fits existing representations to each other; it does not recover physical scale
or validate unseen real geometry. Keep the residual and candidate scores as evidence.
"""
import itertools, json, struct
from pathlib import Path
import numpy as np


def splat_centers(path: Path, maximum=900):
    with path.open('rb') as f:
        fields=[];count=0
        while True:
            line=f.readline().decode('ascii').strip()
            if line.startswith('element vertex'):count=int(line.split()[-1])
            if line.startswith('property '):
                _,kind,name=line.split()
                if kind!='float':raise ValueError('Expected Gaussian float properties')
                fields.append((name,'<f4'))
            if line=='end_header':break
            if not line:raise ValueError('Incomplete PLY header')
        vertices=np.fromfile(f,dtype=fields,count=count)
    points=np.stack([vertices[name] for name in ('x','y','z')],axis=1)
    valid=np.isfinite(points).all(axis=1)
    if 'opacity' in vertices.dtype.names:valid &= vertices['opacity']>-2
    points=points[valid]
    return points[np.linspace(0,len(points)-1,min(maximum,len(points)),dtype=int)]


def mesh_points(path: Path, maximum=900):
    with path.open('rb') as f:
        magic,version,_=struct.unpack('<4sII',f.read(12))
        if magic!=b'glTF' or version!=2:raise ValueError('Expected GLB version 2')
        size,_=struct.unpack('<II',f.read(8));document=json.loads(f.read(size))
        size,_=struct.unpack('<II',f.read(8));binary=f.read(size)
    if any(any(k in n for k in ('matrix','translation','rotation','scale')) for n in document.get('nodes',[])):
        raise ValueError('This calibration tool expects an untransformed SAM mesh')
    index=document['meshes'][0]['primitives'][0]['attributes']['POSITION']
    accessor=document['accessors'][index];view=document['bufferViews'][accessor['bufferView']]
    if accessor['componentType']!=5126 or view.get('byteStride',12)!=12:
        raise ValueError('Expected packed float32 vertex positions')
    points=np.frombuffer(binary,dtype='<f4',count=accessor['count']*3,
                         offset=view.get('byteOffset',0)+accessor.get('byteOffset',0)).reshape(-1,3)
    return points[np.linspace(0,len(points)-1,min(maximum,len(points)),dtype=int)]


def rotation_xyzw(q):
    x,y,z,w=np.asarray(q)/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def fit(splat: Path, mesh: Path, metadata: dict):
    target=splat_centers(splat);source=mesh_points(mesh)
    q=np.array(metadata['rotation']).reshape(4)
    scale=np.array(metadata['scale']).reshape(3)
    translation=np.array(metadata['translation']).reshape(3)
    candidates=[]
    for convention,quaternion in [('xyzw',q),('wxyz',np.roll(q,-1))]:
        rotation=rotation_xyzw(quaternion)
        for permutation in itertools.permutations(range(3)):
            for signs in itertools.product((-1,1),repeat=3):
                axes=np.eye(3)[list(permutation)]@np.diag(signs)
                if np.linalg.det(axes)<0:continue
                linear=rotation@np.diag(scale)@axes
                points=source@linear.T+translation
                squared=np.sum((points[:,None]-target[None,:])**2,axis=2)
                loss=float((np.sqrt(squared.min(axis=0)).mean()+np.sqrt(squared.min(axis=1)).mean())/2)
                matrix=np.eye(4);matrix[:3,:3]=linear;matrix[:3,3]=translation
                candidates.append({'residual':loss,'quaternion_order':convention,'axes':axes.tolist(),
                                   'matrix':matrix.T.reshape(-1).tolist()})
    candidates.sort(key=lambda c:c['residual'])
    return {'method':'sampled bidirectional nearest-neighbor comparison of proper axis rotations',
            'metric_status':'unverified','sample_count':len(source),'best':candidates[0],
            'alternatives':candidates[1:4]}
