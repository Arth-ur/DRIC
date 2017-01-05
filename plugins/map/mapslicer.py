
from __future__ import division

import dric
import dric.support
from logging import getLogger
from os import listdir, mkdir, makedirs, path
from os.path import join, split, splitext, exists, abspath, basename
from shutil import rmtree
from builtins import range
from PIL import Image
from hashlib import sha1 as hashfunc
from multiprocessing import Pool
from timeit import default_timer
from json import load
from tempfile import mkstemp
import cairosvg



_logger = getLogger('dric.mapslicer')

@dric.support.Configurable('config.yml', 'config')
class MapSlicerPlugin(dric.Plugin):
    def setup(self, eventbus):
        if(self.config['invoke'] != 'NEVER'):
            for map_dir in listdir(self.get_source_dir()):

                # check that map_dir is a directory; if it's a file, skip
                if(not path.isdir(path.join(self.get_source_dir(), map_dir))):
                    _logger.warning('Skipping %s; images should be placed in separate folders', map_dir)
                    continue;

                # get destination dir
                dest_dir = self.get_dest_dir(map_dir)

                # if destination dir does not exists, creates it
                if (exists(dest_dir) is False):
                    _logger.debug('MKDIR %s', dest_dir)
                    makedirs(dest_dir)
                
                source_dir = join(self.get_source_dir(), map_dir)

                source_file, file_info = self.open_source_directory(source_dir);
                
                # check if we should slice this file. 
                if(self.config['invoke'] == 'ALWAYS'):
                    self.slice(source_file, file_info, dest_dir)
                elif(self.config['invoke'] == 'IF_CHANGED'):
                    if(self.source_has_changed(source_file, dest_dir)):
                        self.slice(source_file, file_info, dest_dir)
            
    def configure(self, configuration):
        slicer_config = configuration.configuration['map']['slicer']
        self.config = slicer_config

    def slice(self, source_file, file_info, dest_dir):
        """
        If the picture is a svg file (.svg), we first convert it to
        a big png file (.png). If the dpi is not specified, 96dpi is
        used. 

        If the ignore attribute is set to True in the file infos, 
        the file is ignore. 
        """

        if(file_info is not None and 'ignore' in file_info and file_info['ignore'] is True):
            _logger.info('Ignoring %s', source_file)
            return

        _logger.info('Slicing %s', source_file)
        
    
        image = None
        # open source file (convert svg files to png)
        if(splitext(source_file)[1] == '.svg'):
            _, temp_file = mkstemp(suffix='.png')
            cairosvg.svg2png(url=source_file, write_to=temp_file, dpi=file_info.get('dpi', 96))
            image = Image.open(temp_file)
        else:
            image = Image.open(source_file)
        
        self.slice_image(image, file_info, dest_dir)
        # add the hash for IF_CHANGED feature
        self.add_hash(source_file, dest_dir)
            
    def slice_image(self, image, file_info, dest_dir):
        # clear destination directory
        rmtree(dest_dir)
        mkdir(dest_dir)
        
        max_zoom = int(self.config['zoom']) + 1

        for zoom_level in range(0, max_zoom):
            start_time = default_timer()     
            self.slice_for_zoom_level(image, zoom_level, dest_dir, self.config['zoom'])
            elapsed = default_timer() - start_time     
            _logger.debug('Sliced zoom level %d/%d in %f ms', zoom_level, max_zoom, elapsed)

        image.close()
        

    def slice_for_zoom_level(self, image, zoom_level, dest_dir, max_zoom):
        zoom_dir = join(dest_dir, str(zoom_level))
        mkdir(zoom_dir)

        for col in range(0, 2**zoom_level):
            col_dir = join(zoom_dir, str(col))
            mkdir(col_dir)
            for row in range(0, 2**zoom_level):
                row_filename = str(row) + '.png'
                row_file = join(col_dir, row_filename)

                side = image.size[0] / (2**zoom_level)
                region = (side*col, side*row, side*(col+1), side*(row+1))

                self.create_tile (image, region, row_file) 

    def create_tile(self, image, region, row_file):
        small = image.crop(region)
        tile = small.resize((256,256))
        tile.save(row_file)
    
    def source_has_changed(self, source_file, dest_dir):
        hash_file = join(dest_dir, '.source_hash')
        if(exists(hash_file) is False):
            return True
        f = file(hash_file, 'r')
        old_hash = f.read()
        new_hash = self.calculate_hash(source_file)
        return old_hash != new_hash

    def add_hash(self, source_file, dest_dir):
        hash = self.calculate_hash(source_file)
        f = file(join(dest_dir, '.source_hash'), 'w')
        f.write(hash)
        f.close()

    def calculate_hash(self, source_file):
        _logger.debug('Calculating hash for source file %s', source_file)
        hash = hashfunc()
        chunck_size = 1024*8    # read by block of 8MB
        f = open(source_file)
        while True:
            chunck = f.read(chunck_size)
            if chunck == '':
                break
            hash.update(chunck)
        return hash.digest()

    def get_dest_dir(self, file):
        """
            Destination directory's name is the same as the source directory's name
        """
        # filename = split(file)[1]
        # dir_name = splitext(filename)[0]
        dir = join(self.config['destination'], file)
        return abspath(dir)

    def get_source_dir(self):
        return abspath(self.config['source'])

    def open_source_directory(self, source_dir):
        info = None
        source_file = None
        for f in listdir(source_dir):
            if(f == 'info.json'):
                info = load(file(join(source_dir, f)))
            else:
                source_file = join(source_dir, f)

        if source_file is None:
            raise NoMapSourceFileException(source_dir)
            
        return source_file, info



class NoMapSourceFileException(Exception):
    def __init__(self, source_dir):
        self.source_dir = source_dir

dric.register(__name__, MapSlicerPlugin())