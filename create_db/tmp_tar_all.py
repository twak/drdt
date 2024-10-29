

import os
import tarfile

root = "/home/twak/citnas2/08. Researchers/tom/a14/mesh_chunks"

for d in os.listdir(root):
    if os.path.isdir(f"{root}/{d}"):
        print (d)
        with tarfile.open(f"{root}/{d}/{d}.tar", "w") as tar:
            for f in os.listdir(f"{root}/{d}"):
                tar.add(f"{root}/{d}/{f}", arcname=f"{d}/{f}")