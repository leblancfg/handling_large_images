# coding: utf-8
# Author: leblancfg
# Date: 02/08/2017
import argparse
from bs4 import BeautifulSoup
import datetime
from glob import glob
import os
from PIL import Image, ImageFilter, ImageEnhance
import r2_tools as r2
import subprocess
import sys
import zipfile


def ISO_to_utc(string):
    """Given a string representing ISO 8601 time,
    returns datetime object.

    str -> datetime"""
    pattern = "%Y-%m-%dT%H:%M:%S.%fZ"
    return datetime.datetime.strptime(string, pattern)

def utc_to_ISO(dt):
    """Given a datetime object, formats it
    and returns ISO 8601 time string.

    datetime -> str"""
    pattern = "%Y-%m-%dT%H:%M:%S.%fZ"
    return dt.strftime(pattern)

def compare(start_time, end_time):
    """Compares the `rawDataStartTime` to the `processingTime`
    from a `product.xml` file, returns either 'ARCHIVED' or
    'PROGRAMMED'. Arbitrary cutoff date is 3 days.

    dt, dt -> str
    """
    days = 3
    duration = (end_time - start_time).seconds
    if duration > days * 86400:
        return 'ARCHIVED'
    return 'PROGRAMMED'

def create_xml(xml_soup, region):
    """Given R2 metadata XML BeautifulSoup object and region
    coordinates string, creates COS-2-specific metadata XML
    named `EOP.xml`.

    str -> str"""
    xml_filename = 'EOP.xml'

    # Translate MDA's beam mode names into the appropriate COS-2 names
    beam_modes = {
    'Fine' : 'FINE',
    'Standard' : 'STANDARD',
    'Wide' : 'WIDE',
    'ScanSAR Narrow' : 'SCANSAR_NARROW',
    'ScanSAR Wide' : 'SCANSAR_WIDE',
    'Wide Fine' : 'WIDE_FINE',
    'Multi-Look Fine' : 'MULTI_LOOK_FINE',
    'Wide Multi-Look Fine': 'WIDE_MULTI_LOOK_FINE',
    'Ultrafine' : 'ULTRA_FINE',
    'Wide Ultrafine' : 'WIDE_ULTRA_FINE',
    'Spotlight A' : 'SPOTLIGHT',
    # Map these to others as they're not part of the COS-2 list
    'Wide Fine Quad Polarization' : 'WIDE_FINE',
    'Fine Quad Polarization' : 'FINE',
    'Wide Standard Quad Polarization' : 'WIDE',
    'Standard Quad Polarization' : 'STANDARD',
    'Extra Fine' : 'WIDE_FINE',
    'High Incidence' : 'STANDARD',
    'Low Incidence' : 'WIDE',
    }

    image_id = xml_soup.imageId.string
    start_time = ISO_to_utc(xml_soup.rawDataStartTime.string)
    end_time = ISO_to_utc(xml_soup.zeroDopplerTimeLastLine.string)
    processing_time = ISO_to_utc(xml_soup.processingTime.string)
    status = compare(start_time, processing_time)
    beam_mode = beam_modes.get(xml_soup.acquisitionType.string)

    string = """<?xml version="1.0" encoding="utf-8"?>
<sar:EarthObservation xmlns:eop="http://earth.esa.int/eop" xmlns:gml="http://www.opengis.net/gml" xmlns:sar="http://earth.esa.int/sar" version="1.2.2">
  <gml:metaDataProperty>
    <eop:EarthObservationMetaData>
      <eop:identifier>{5}</eop:identifier>
      <eop:parentIdentifier>urn:ogc:def:EOP:CSA:RSAT2</eop:parentIdentifier>
      <eop:productType/>
      <eop:status>{0}</eop:status>
    </eop:EarthObservationMetaData>
  </gml:metaDataProperty>
  <gml:validTime>
    <gml:TimePeriod>
      <gml:beginPosition>{1}</gml:beginPosition>
      <gml:endPosition>{2}</gml:endPosition>
    </gml:TimePeriod>
  </gml:validTime>
  <gml:using>
    <eop:EarthObservationEquipment>
      <eop:platform>
        <eop:Platform>
          <eop:shortName>RADARSAT2</eop:shortName>
        </eop:Platform>
      </eop:platform>
      <eop:instrument>
        <eop:Instrument>
          <eop:shortName>SAR_RAD_2</eop:shortName>
        </eop:Instrument>
      </eop:instrument>
      <eop:sensor>
        <eop:Sensor>
          <eop:sensorType>RADAR</eop:sensorType>
          <eop:operationalMode>{3}</eop:operationalMode>
        </eop:Sensor>
      </eop:sensor>
    </eop:EarthObservationEquipment>
  </gml:using>
  <gml:target>
    <eop:Footprint>
      <gml:multiExtentOf>
        <gml:MultiSurface srsName="EPSG:4326">
          <gml:surfaceMembers>
            <gml:Polygon>
              <gml:exterior>
                <gml:LinearRing>
                  <gml:posList>{4}</gml:posList>
                </gml:LinearRing>
              </gml:exterior>
            </gml:Polygon>
          </gml:surfaceMembers>
        </gml:MultiSurface>
      </gml:multiExtentOf>
    </eop:Footprint>
  </gml:target>
  <eop:browse>
    <eop:BrowseInformation>
      <eop:type>THUMBNAIL</eop:type>
      <eop:referenceSystemIdentifier codeSpace="EPSG">EPSG:4326</eop:referenceSystemIdentifier>
      <eop:fileName>ICON.JPG</eop:fileName>
    </eop:BrowseInformation>
  </eop:browse>
  <eop:browse>
    <eop:BrowseInformation>
      <eop:type>QUICKLOOK</eop:type>
      <eop:referenceSystemIdentifier codeSpace="EPSG">EPSG:4326</eop:referenceSystemIdentifier>
      <eop:fileName>PREVIEW.JPG</eop:fileName>
    </eop:BrowseInformation>
  </eop:browse>
</sar:EarthObservation>""".format(status,
                                  utc_to_ISO(start_time),
                                  utc_to_ISO(end_time),
                                  beam_mode,
                                  region,
                                  image_id)

    with open(xml_filename, 'w') as f:
        f.write(string)

def resize_and_contrast(file_in, file_out, resize=None):
    """Given input and output filenames, and `resize` in pixels,
    resizes and auto-contrasts the `file_in` image and saves
    it as `file_out`.

    Args:
        file_in: Filename of the image to be converted
        file_out: Output filename
        resize: Output size of the image (px), default=512 px
    Returns:
        None

    str, str, int -> None"""
    try:
        # Make a tuple out of the pixel size
        size = (resize, resize)
        
        image = Image.open(file_in)
        # Apply some blur to slightly smooth out pixels
        image = image.filter(ImageFilter.GaussianBlur(radius=0.2))
        # Apply some more contrast
        contrast = ImageEnhance.Contrast(image)
        image = contrast.enhance(1.5)

        if resize:
            # Resize the image to `size`
            image.thumbnail(size, resample=Image.BICUBIC)
        image.save(file_out, format=None)
    except IOError:
        print('Cannot resize', file_in, 'to', file_out)

def zip_count(f):
    """Given zip filename, returns number of files inside.

    str -> int"""
    from contextlib import closing
    with closing(zipfile.ZipFile(f)) as archive:
        num_files = len(archive.infolist())
    return num_files

def get_frame_coords(acp_files):
    """For a given set of ACP files, returns a dictionnary
    of sceneStartTimes: region coordinates for every frame
    in list of ACPs.
    
    Returns: a dictionary of mappings between sceneStartTimes
    and tuples of lat, lon for the four corners.
    
    [str] -> {str: [(float, float)]}"""
    acps = [r2.acp(f) for f in acp_files]

    swaths = []
    for acp in acps:
        for s in acp.swaths:
            swaths.append(s)

    frames = dict()
    for s in swaths:
        for frame in s.sceneSpecifications:
            for x in frame['sceneSpecification']:
                corners = []
                for v in x['cornerLists']:
                    for corner in v['cornerList']:
                        corners.append((corner['cornerLatitude'], corner['cornerLongitude']))
                coords = [str(coord) for t in corners for coord in t]
                # Duplicate first coordinates because LinearRing
                coords.append(coords[0])
                coords.append(coords[1])
                frames[ISO_to_utc(x['sceneStartTime'])] = ' '.join(coords)
    return frames

def create_archives(path):
    """Given 'charter_call_###' folder name, gets image XML and
    quicklook images, creates a zip file containing the COS-2
    metadata products (thumbnail, quicklook and COS-2 metadata XML)
    and returns list of the `.zip` filenames ready to be uploaded.

    Args:
        - folder: Name of folder containing Charter metadata,
            a product XML and quicklook image for each product
            delivered for the activation.

    str -> [str,]"""
    xml_filename = 'EOP.xml'
    thumbnail_filename = 'ICON.JPG'
    quicklook_filename = 'PREVIEW.JPG'

    try:
        activation_num = path.split('-')[-1]
    except IOError:
        print('Folder name needs to contain activation number')

    try:
        acp_files = glob(path + '\*.acp', recursive=False)
        xml_files = glob(path + '\*.xml', recursive=False)  
        img_files = glob(path + '\*.jpg', recursive=False)
    except IOError:
        print('Folder must contain')

    # Map frame startTimes to region strings
    frames_dict = get_frame_coords(acp_files)

    # Map NEODF imageIDs to image filenames
    image_dict = {i.split('\\')[-1].split('_')[-2]: i for i in img_files}

    for file in xml_files:
        filename = file.split('\\')[-1]

        # Get XML details to match which ACP frame and JPG to use
        with open(file) as f:
            xml_soup = BeautifulSoup(f, 'xml')
        image_id = xml_soup.imageId.string

        # Choose the right image
        neodf_id = filename.split('_')[-1][:-4]  # Strip the extension
        img_file = image_dict[neodf_id]

        # Get the region coordinates from ACP frame with the closest StartTime
        xml_start_time = ISO_to_utc(xml_soup.rawDataStartTime.string)
        timestamp = min(frames_dict, key=lambda datetime : abs(xml_start_time - datetime))
        region = frames_dict.pop(timestamp)  # Remove entry so no duplicates

        # Finally ready to process and generate `EOP.xml`
        create_xml(xml_soup, region)

        # Process and generate images
        resize_and_contrast(img_file, quicklook_filename, resize=500)  # Only apply contrast
        resize_and_contrast(img_file, thumbnail_filename, resize=100)

        # Create zip file: XML, and the two JPGS
        zip_filename = activation_num + '_RADARSAT2_' + image_id + '.zip'
        data_products = [xml_filename, thumbnail_filename, quicklook_filename]

        with zipfile.ZipFile(path + '\\' + zip_filename, "w") as f:
            for name in data_products:
                f.write(name, os.path.basename(name), zipfile.ZIP_DEFLATED)

        # Delete intermediary files
        for f in data_products:
            os.remove(f)

def upload_zips(folder, username, password):
    """Given folder, username and password, uploads all the zip files in folder
    to the COS-2 website.

    str, str, str -> None"""
    url = 'disasterscharter.org/charter-portlets/service/data-product/CSA/RADARSAT2/'
    for zip_file in glob(folder + '\\' + '*.zip'):
        # Redundant activation _num check, but at least no mishaps
        activation_num = zip_file.split('\\')[-1].split('_')[0]
        invoke_str = 'curl -i -k -X POST --form product="@{0}" --form public-data=TRUE –basic https://{1}:{2}@{3}{4}'.format(zip_file, username, password, url, activation_num)

        try:
            subprocess.check_output(invoke_str)
        except subprocess.CalledProcessError as exc:                                                                                                   
            print('Error code', exc.returncode, exc.output)

def help():
    """Returns the help string"""
    string = """
    Utility to process and upload Charter metadata products
    to the COS-2 server.
    
    Requires being in in a directory that has direct subdirectories
    named 'charter-call-xxx', where xxx is the activation number.
    
    Each folder must contain:
    - ACP file(s) of all image products provided in the activation,
    - For each image product provided in the activation, a metadata
        XML and quicklook JPG downloaded from NEODF.
    
    Upload to COS-2 requires having curl installed locally."""
    return string

# Currently set up to be run as a command-line tool
if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description=help(),
                                     formatter_class=argparse.RawTextHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--credentials', nargs=2, dest='credential', help='MP username and password for COS-2')
    group.add_argument('-n', '--no_upload', help='Skip the upload to COS-2', action='store_true')
    parser.set_defaults(type='n')
    parser.add_argument('-f', '--folders', nargs='*', help='')
    
    args = parser.parse_args()
    
    if args.folders:
        folders = args.folders
    else:
        folders = [x[0] for x in os.walk(directory)]

    # Main
    for folder in folders:
        print('Processing folder:', folder, '...', end='')
        zipfiles = create_archives(folder)
        print(' successfully', end='')
        if not args.no_upload:
            print(' ...', end='')
            username = ''.join(args.credential[0])
            password = ''.join(args.credential[1])
            upload_zips(folder, username, password)
            print(' uploaded.')
        