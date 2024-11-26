import os
import PIL.Image
from api import utils

if __name__ == '__main__':

    dirr = "/home/twak/citnas/06. Data/4. Roads/Cambridge University - National Highways Data/Original Data (from KOREC)/Images_Point_Clouds/A14 EB-WB J47A (Woolpit) to Haugley Bridge/Panoramic_Imagery/panorama-geotagged"
    with open(f"{utils.scratch}/coords.txt", "w") as fp:
        for file in os.listdir(dirr):
            if file.endswith(".jpg"):
                print (f"\n\n{file}")
                img = PIL.Image.open(os.path.join(dirr, file))
                exif_data = img._getexif()
                print (f"{exif_data[34853][2]}  {exif_data[34853][4]}")

                a, b = exif_data[34853][2], exif_data[34853][4]
                lat = float(a[0]) + float(a[1])/60 + float ( a[2]) / 3600
                lon = float(b[0]) + float(b[1])/60 + float ( b[2]) / 3600

                out = f"{lat}, {lon}, {file}, \"<a href='data/panos/a14/{file}'>link</a>\",\n"
                print(out)
                fp.write(out)