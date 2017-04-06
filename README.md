# Handling Satellite Images
Short Jupyter Notebook exploring different options to handle large satellite images.

The goal of this notebook is to get image statistics for very large images, typically GeoTIFFs. The files are in the order of 1 - 4 GB. Anything bigger would actually need to be stored in another filetype (see [bigTIFF](http://www.simplesystems.org/libtiff/bigtiffpr.html)). We find a way to read the image in memory, and perform our analysis

It's a simple enough operation, but the size of the image is such that our standard approach must be modified.

See big_img.ipynb for the actual contents.
