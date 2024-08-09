
import pdal


pipeline = pdal.Reader("/home/twak/chunks_a14/chunks/601508_261721_178.las") | pdal.Filter.sort(dimension="X")
