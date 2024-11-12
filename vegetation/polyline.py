import shapely

from numpy.linalg import norm
import numpy as np

class Polyline():

    def __init__(self, wkt):
        self.path = np.array ( shapely.from_wkt(wkt).geoms[0].coords )

        self.lengths, self.l_accum = [], []

        sofa = 0
        for i in range (0, len(self.path )-1):
            self.lengths.append( norm ( self.path [i+1] - self.path [i] ) )
            sofa += self.lengths[-1]
            self.l_accum.append(sofa)

    def find_pt_at_dist(self, dist):
        # find a point at a distance along a path
        for i in range(0, len(self.l_accum)):
            if dist < self.l_accum[i]:
                extra = (dist - self.l_accum[i - 1]) if i > 0 else dist
                return (self.path[i + 1] - self.path[i]) * extra / self.lengths[i] + self.path[i], i

        return self.path[-1], len (self.path) - 1

    def to_lengths(self, dist, tol=5):

        out = []
        n = max ( 1, int(round(self.l_accum[-1] / dist)) )
        nd = self.l_accum[-1] / n
        c = self.path[0]

        out.append(c)

        for seg_i in range(0, n):
            # split the path into n equal lengths

            pt, max_i = self.find_pt_at_dist(nd * (seg_i + 1)) # find the split
            out.append(pt)

        return out

    def split_to_lengths(self, dist, tol=5):

        out = []
        n = max ( 1, int(round(self.l_accum[-1] / dist)) )
        nd = self.l_accum[-1] / n
        c = self.path[0]
        ci = 1

        for seg_i in range(0, n):
            # split the path into n equal lengths
            seg = []
            out.append(seg)
            seg.append(c)

            pt, max_i = self.find_pt_at_dist(nd * (seg_i + 1)) # find the split

            for j in range(ci, max_i + 1): # copy all the points to the split
                if norm (self.path[j] - seg[-1]) < 1:
                    print ("here boss")
                seg.append(self.path[j])

            if np.linalg.norm(seg[-1] - pt) > tol: # split is not close to the start

                if max_i + 2 < len(self.path) and np.linalg.norm(self.path[max_i+1] - pt) < tol: # but is split is close to the end?
                    seg.append(self.path[max_i+1])
                    c = self.path[max_i+1]
                    ci = max_i + 2
                else:
                    seg.append(pt)
                    c = pt # start of the next segment is the new point
                    ci = max_i + 1

            else: # split is close to the start
                c = seg[-1] # start of next segment is the end of this one
                ci = max_i + 1

        return out