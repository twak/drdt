import shapely

from numpy.linalg import norm
import numpy as np

class Polyline():

    def __init__(self, wkt):
        self.path = shapely.from_wkt(wkt)[0]

        self.lengths, self.l_accum = [], []

        sofa = 0
        for i in range (0, len(self.path )-2):
            self.lengths.append( norm ( self.path [i+1] - self.path [i] ) )
            sofa += self.lengths[-1]
            self.l_accum.append(sofa)

    def find_pt_at_dist(self, dist):
        # find a point at a distance along a path
        for i in range(0, len(self.l_accum)):
            if dist < self.l_accum[i]:
                extra = (dist - self.l_accum[i - 1]) if i > 0 else dist
                # interpolate between i and i+1
                # normal = (self.path[i + 1] - self.path[i])
                # normal = normal / np.linalg.norm(normal)
                # perp = np.array([-normal[1], normal[0], 0])

                return (self.path[i + 1] - self.path[i]) * extra / self.lengths[i] + self.path[i], i

        return self.path[-1]

    def split_to_lengths(self, dist):

        out = []
        n = int(self.l_accum[-1] / dist)
        nd = self.l_accum[-1] / n
        c = self.path[0]

        for seg_i in range(0, n):
            # split the path into n equal lengths
            seg = []
            out.append(seg)
            seg.append(c)

            pt, max_i = self.find_pt_at_dist(nd * (seg_i + 1))

            for j in range(c, max_i + 1):
                seg.append(self.path[j])

            seg.append(pt)
            c = pt

        return out