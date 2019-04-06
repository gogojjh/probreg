import abc
from collections import namedtuple
import itertools
import six
import numpy as np
import open3d as o3
from . import math_utils as mu

from .dq3d import op

@six.add_metaclass(abc.ABCMeta)
class Transformation():
    def __init__(self):
        pass

    def transform(self, points,
                  array_type=o3.Vector3dVector):
        if isinstance(points, array_type):
            return array_type(self._transform(np.asarray(points)))
        return self._transform(points)

    @abc.abstractmethod
    def _transform(self, points):
        return points


class RigidTransformation(Transformation):
    def __init__(self, rot=np.identity(3),
                 t=np.zeros(3), scale=1.0):
        super(RigidTransformation, self).__init__()
        self.rot = rot
        self.t = t
        self.scale = scale

    def _transform(self, points):
        return self.scale * np.dot(points, self.rot.T) + self.t

    def inverse(self):
        return RigidTransformation(self.rot.T, -np.dot(self.rot.T, self.t),
                                   1.0 / self.scale)


class AffineTransformation(Transformation):
    def __init__(self, b=np.identity(3),
                 t=np.zeros(3)):
        super(AffineTransformation, self).__init__()
        self.b = b
        self.t = t

    def _transform(self, points):
        return np.dot(points, self.b.T) + self.t


class NonRigidTransformation(Transformation):
    def __init__(self, w, points, beta=2.0):
        super(NonRigidTransformation, self).__init__()
        self.g = mu.rbf_kernel(points, points, beta)
        self.w = w

    def _transform(self, points):
        return points + np.dot(self.g, self.w)


class TPSTransformation(Transformation):
    """Thin Plate Spline transformaion.
    """
    def __init__(self, a, v, control_pts,
                 kernel=mu.tps_kernel):
        super(TPSTransformation, self).__init__()
        self.a = a
        self.v = v
        self.control_pts = control_pts
        self._kernel = kernel

    def prepare(self, landmarks):
        control_pts = self.control_pts
        m, d = landmarks.shape
        n, _ = control_pts.shape
        pm = np.c_[np.ones((m, 1)), landmarks]
        pn = np.c_[np.ones((n, 1)), control_pts]
        u, _, _ = np.linalg.svd(pn)
        pp = u[:, d + 1:]
        kk = self._kernel(control_pts, control_pts)
        uu = self._kernel(landmarks, control_pts)
        basis = np.c_[pm, np.dot(uu, pp)]
        kernel = np.dot(pp.T, np.dot(kk, pp))
        return basis, kernel

    def transform_basis(self, basis):
        return np.dot(basis, np.r_[self.a, self.v])

    def _transform(self, points):
        basis, _ = self.prepare(points)
        return self.transform_basis(basis)


class DeformableKinematicModel(Transformation):
    class SkinningWeight(np.ndarray):
        def __init__(self, n_points):
            super(DeformableKinematicModel.SkinningWeight, self).__init__(n_points,
                                                                          dtype=[('pair', 'i4', 2),
                                                                                 ('val', 'f4', 2)])

        @property
        def n_nodes(self):
            return self['pair'].max()

        def pairs_set(self):
            return itertools.permutations(range(self.n_nodes), 2)

        def in_pair(self, pair):
            return np.argwhere((self['pair']==pair).all(1)).flatten()

    @classmethod
    def make_weight(cls, pairs, vals):
        weights = cls.SkinningWeight(pairs.shape[0])
        weights['pair'] = pairs
        weights['val'] = vals
        return weights

    def __init__(self, dual_quats, weights):
        super(DeformableKinematicModel, self).__init__()
        self.weights = weights
        self.dual_quats = dual_quats
        self.trans = [op.dlb(w[1], self.dual_quats[w[0]]) for w in self.weights]

    def _transform(self, points):
        return np.array([t.transform_points(p) for t, p in zip(self.trans, points)])
