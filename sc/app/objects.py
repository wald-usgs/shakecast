"""
This program holds all the non-database objects used necessary for
ShakeCast to run. These objects are used in the functions.py program
"""

import urllib2
import ssl
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
import smtplib
import datetime
from email.mime.text import MIMEText
from email.MIMEImage import MIMEImage
from email.MIMEMultipart import MIMEMultipart
from util import *
from orm import Session, Event, ShakeMap, Product, User, DeclarativeMeta
modules_dir = os.path.join(sc_dir(), 'modules')
if modules_dir not in sys.path:
    sys.path += [modules_dir]

from jinja2 import Template
from shutil import copyfile
import socks

class ProductGrabber(object):
    
    """
    Able to access the USGS web, download products, and make entries
    in the database
    """
    
    def __init__(self,
                 req_products=None,
                 data_dir=''):
        
        sc = SC()
        
        self.req_products = req_products
        self.server_address = ''
        self.json_feed_url = sc.geo_json_web
        self.ignore_nets = sc.ignore_nets
        self.json_feed = ''
        self.earthquakes = {}
        self.data_dir = ''
        self.delim = ''
        self.log = ''
        self.query_period = 'day'
        
        if not self.req_products:
            self.req_products = sc.eq_req_products
        
        if data_dir == '':
            self.get_data_path()
    
    def get_data_path(self):
        """
        Gets the path to the data folder and sets the self.data_dir
        property
        """
        path = os.path.dirname(os.path.abspath(__file__))
        self.delim = os.sep
        path = path.split(self.delim)
        path[-1] = 'data'
        self.data_dir = os.path.normpath(self.delim.join(path))
        
    def get_json_feed(self, scenario=False):
        """
        Pulls json feed from USGS web and sets the self.json_feed
        variable. Also makes a list of the earthquakes' IDs
        """
        url_opener = URLOpener()
        if scenario is False:
            json_str = url_opener.open(self.json_feed_url.format(self.query_period))
        else:
            json_str = url_opener.open(self.json_feed_url)
        self.json_feed = json.loads(json_str)
        
        #self.earthquakes = self.json_feed['features']
        
        if self.json_feed.get('features', None) is None:
            eq = self.json_feed
            info = {'status': 'new'}
            eq.update(info)
            self.earthquakes[eq['id']] = eq
        
        else:

            for eq in self.json_feed['features']:
                # skip earthquakes without dictionaries... why does this
                # happen??
                try:
                    if eq['id'] not in self.earthquakes.keys():
                        info = {'status': 'new'}
                        eq.update(info)
                        self.earthquakes[eq['id']] = eq
                except:
                    continue
        
    def get_new_events(self, scenario=False):
        """
        Checks the json feed for new earthquakes
        """
        session = Session()
        sc = SC()
        
        event_str = ''
        new_events = []
        for eq_id in self.earthquakes.keys():
            eq = self.earthquakes[eq_id]
            
            # ignore info from unfavorable networks and low mag eqs
            if (eq['properties']['net'] in self.ignore_nets or
                    eq['properties']['mag'] < sc.new_eq_mag_cutoff):
                continue
            
            # get event id and all ids
            event = Event()
            event.all_event_ids = eq['properties']['ids']
            if scenario is False:
                event.event_id = eq_id
            else:
                event.event_id = eq_id + '_scenario'
                event.all_event_ids = event.event_id
            
            # use id and all ids to determine if the event is new and
            # query the old event if necessary
            old_shakemaps = []
            old_notifications = []
            if event.is_new() is False:
                event.status = 'processed'
                ids = event.all_event_ids.strip(',').split(',')
                old_events = [(session.query(Event)
                                .filter(Event.event_id == each_id)
                                .first())
                                    for each_id in ids]
                
                # remove older events
                for old_event in old_events:
                    if old_event is not None:
                        old_notifications += old_event.notifications
                        old_shakemaps += old_event.shakemaps
                        
                        # if one of these old events hasn't had
                        # notifications sent, this event should be sent
                        if old_event.status == 'new':
                            event.status = 'new'
                        session.delete(old_event)
            else:
                event.status = 'new'

            # over ride new status if scenario
            if scenario is True:
                event.status = 'scenario'
                        
            # Fill the rest of the event info
            event.directory_name = os.path.join(self.data_dir,
                                                event.event_id)
            event.title = self.earthquakes[eq_id]['properties']['title']
            event.place = self.earthquakes[eq_id]['properties']['place']
            event.time = self.earthquakes[eq_id]['properties']['time']/1000.0
            event.magnitude = eq['properties']['mag']
            event_coords = self.earthquakes[eq_id]['geometry']['coordinates']
            event.lon = event_coords[0]
            event.lat = event_coords[1]
            event.depth = event_coords[2]
            
            if old_shakemaps:
                event.shakemaps = old_shakemaps
            if old_notifications:
                event.notifications = old_notifications

            session.add(event)
            session.commit()
            
            self.get_event_map(event)
            
            # add the event to the return list and add info to the
            # return string
            new_events += [event]
            event_str += 'Event: %s\n' % event.event_id
        
        Session.remove()
        print event_str
        return new_events, event_str
    
    @staticmethod
    def get_event_map(event):
        if not os.path.exists(event.directory_name):
                os.makedirs(event.directory_name)
        sc=SC()
        # download the google maps image
        url_opener = URLOpener()
        gmap = url_opener.open("https://maps.googleapis.com/maps/api/staticmap?center=%s,%s&zoom=5&size=200x200&sensor=false&maptype=terrain&markers=icon:http://earthquake.usgs.gov/research/software/shakecast/icons/epicenter.png|%s,%s&key=%s" % (event.lat,
                                           event.lon,
                                           event.lat,
                                           event.lon,
                                           sc.gmap_key))
        
        # and save it
        image_loc = os.path.join(event.directory_name,
                                 'image.png')
        image = open(image_loc, 'wb')
        image.write(gmap)
        image.close()
            
    def get_new_shakemaps(self, scenario=False):
        """
        Checks the json feed for new earthquakes
        """
        session = Session()
        url_opener = URLOpener()
        
        shakemap_str = ''
        new_shakemaps = []
        for eq_id in self.earthquakes.keys():
            eq = self.earthquakes[eq_id]
            
            if scenario is False:
                eq_url = eq['properties']['detail']
                try:
                    eq_str = url_opener.open(eq_url)
                except:
                    self.log += 'Bad EQ URL: {0}'.format(eq_id)
                try:
                    eq_info = json.loads(eq_str)
                except Exception as e:
                    eq_info = e.partial
            else:
                eq_info = eq
            
            # check if the event has a shakemap
            if 'shakemap' not in eq_info['properties']['products'].keys():
                continue
            
            # pulls the first shakemap associated with the event
            shakemap = ShakeMap()

            if scenario is False:
                shakemap.shakemap_id = eq_id
            else:
                shakemap.shakemap_id = eq_id + '_scenario'
            shakemap.shakemap_version = eq_info['properties']['products']['shakemap'][0]['properties']['version']
            
            # check if we already have the shakemap
            if shakemap.is_new() is False:
                shakemap = (
                  session.query(ShakeMap)
                    .filter(ShakeMap.shakemap_id == shakemap.shakemap_id)
                    .filter(ShakeMap.shakemap_version == shakemap.shakemap_version)
                    .first()
                )
            
            shakemap.json = eq_info['properties']['products']['shakemap'][0]
            
            # check if the shakemap has required products. If it does,
            # it is not a new map, and can be skipped
            if (shakemap.has_products(self.req_products)) and scenario is False:
                continue
            
            # depricate previous unprocessed versions of the ShakeMap
            dep_shakemaps = (
                session.query(ShakeMap)
                    .filter(ShakeMap.shakemap_id == shakemap.shakemap_id)
                    .filter(ShakeMap.status == 'new')
            )
            for dep_shakemap in dep_shakemaps:
                dep_shakemap.status = 'depricated'
            
            # assign relevent information to shakemap
            shakemap.map_status = shakemap.json['properties']['map-status']
            shakemap.region = shakemap.json['properties']['eventsource']
            shakemap.lat_max = shakemap.json['properties']['maximum-latitude']
            shakemap.lat_min = shakemap.json['properties']['minimum-latitude']
            shakemap.lon_max = shakemap.json['properties']['maximum-longitude']
            shakemap.lon_min = shakemap.json['properties']['minimum-longitude']
            shakemap.generation_timestamp = shakemap.json['properties']['process-timestamp']
            shakemap.recieve_timestamp = time.time()

            if scenario is False:
                shakemap.status = 'new'
            else:
                shakemap.status = 'scenario'
            
            # make a directory for the new event
            shakemap.directory_name = os.path.join(self.data_dir,
                                                   shakemap.shakemap_id,
                                                   shakemap.shakemap_id + '-' + str(shakemap.shakemap_version))
            if not os.path.exists(shakemap.directory_name):
                os.makedirs(shakemap.directory_name)
        
            # download products
            for product_name in self.req_products:
                product = Product(shakemap = shakemap,
                                  product_type = product_name)
                
                try:
                    product.json = shakemap.json['contents']['download/%s' % product_name]
                    product.url = product.json['url']
                    
                    # download and allow partial products
                    try:
                        product.str_ = url_opener.open(product.url)
                        eq['status'] = 'downloaded'
                    except httplib.IncompleteRead as e:
                        product.web = e.partial
                        eq['status'] = 'incomplete'
                    
                    if product_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                        mode = 'wb'
                    else:
                        mode = 'wt'
                    product.file_ = open('%s%s%s' % (shakemap.directory_name,
                                                      self.delim,
                                                      product_name), mode)
                    product.file_.write(product.str_)
                    product.file_.close()
                except:
                    self.log += 'Failed to download: %s %s' % (eq_id, product_name)
            
            # check for event whose id or one of its old ids matches the shakemap id
            if scenario is False:
                event = session.query(Event).filter(Event.all_event_ids.contains(shakemap.shakemap_id)).all()
            else:
                event = session.query(Event).filter(Event.event_id == shakemap.shakemap_id).all()

            if event:
                event = event[0]
                event.shakemaps.append(shakemap)
                
            session.commit()
            
            new_shakemaps += [shakemap]
            shakemap_str += 'Wrote %s to disk.\n' % shakemap.shakemap_id
        
        self.log += shakemap_str
        Session.remove()
        print shakemap_str
        return new_shakemaps, shakemap_str

    def make_heartbeat(self):
        '''
        Make an Event row that will only trigger a notification for
        groups with a heartbeat group_specification
        '''
        session = Session()
        last_hb = session.query(Event).filter(Event.event_id == 'heartbeat').all()
        make_hb = False
        if last_hb:
            if time.time() > (last_hb[-1].time) + 24*60*60:
                make_hb = True
        else:
            make_hb = True
                
        if make_hb is True:
            e = Event()
            e.time = time.time()
            e.event_id = 'heartbeat'
            e.magnitude = 10
            e.lat = 1000
            e.lon = 1000
            e.title = 'ShakeCast Heartbeat'
            e.place = 'ShakeCast is running'
            e.status = 'new'
            e.directory_name = os.path.join(self.data_dir,
                                               e.event_id)
            session.add(e)
            session.commit()
            
            self.get_event_map(e)
            
        Session.remove()
        
    def get_scenario(self, shakemap_id=''):
        '''
        Grab a shakemap from the USGS web and stick it in the db so
        it can be run as a scenario
        '''
        scenario_ready = True
        try:
            self.json_feed_url = 'https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&eventid={0}'.format(shakemap_id)
            self.get_json_feed(scenario=True)
            self.get_new_events(scenario=True)
            self.get_new_shakemaps(scenario=True)
        except Exception:
            scenario_ready = False
        
        return scenario_ready

    
class Point(object):
    
    '''
    Keeps track of shaking data associated with a location. A list of
    these is made in the ShakeMapGrid class and can be sorted by a metric
    using the ShakeMapGrid.sort_by method
    '''
    
    sort_by = ''
    def __init__(self):
        self.info = {}

    def __cmp__(self, other):
        #if hasattr(other, 'info'):
            #return (int(self.shaking[self.sort_by]).
            #            __cmp__(int(other.shaking[self.sort_by])))

            
        #return (int(self.info[self.sort_by] * 10000).
        #            __cmp__(int(other.info[self.sort_by] * 10000)))
        if int(self.info[self.sort_by] * 10000) > int(other.info[self.sort_by] * 10000):
            return 1
        elif int(self.info[self.sort_by] * 10000) < int(other.info[self.sort_by] * 10000):
            return -1
        else:
            return 0


class ShakeMapGrid(object):
    
    '''
    Object that reads a grid.xml file and compares shaking data with
    input from user data
    '''
    
    def __init__(self,
                 lon_min = 0,
                 lon_max = 0,
                 lat_min = 0,
                 lat_max = 0,
                 nom_lon_spacing = 0,
                 nom_lat_spacing = 0,
                 num_lon = 0,
                 num_lat = 0,
                 event_id = '',
                 magnitude = 0,
                 depth = 0,
                 lat = 0,
                 lon = 0,
                 description = '',
                 directory_name = '',
                 xml_file = ''):
        
        self.lon_min = lon_min
        self.lon_max = lon_max
        self.lat_min = lat_min
        self.lat_max = lat_max
        self.nom_lon_spacing = nom_lon_spacing
        self.nom_lat_spacing = nom_lat_spacing
        self.num_lon = num_lon
        self.num_lat = num_lat
        self.event_id = event_id
        self.magnitude = magnitude
        self.depth = depth
        self.lat = lat
        self.lon = lon
        self.description = description
        self.directory_name = directory_name
        self.xml_file = xml_file
        self.tree = None
        self.fields = []
        self.grid = []
        
        self.points = []
    
    def load(self, file_ = ''):
        """
        Loads data from a specified grid.xml file into the object
        """
        
        if file_ == '':
            file_ = self.xml_file
        else:
            self.xml_file = file_
        
        if file_ == '':
            return False
        
        try:
            self.tree = ET.parse(file_)
            root = self.tree.getroot()
            
            # set the ShakeMapGrid's attributes
            all_atts = {}
            [all_atts.update(child.attrib) for child in root]
            
            self.lat_min = float(all_atts.get('lat_min'))
            self.lat_max = float(all_atts.get('lat_max'))
            self.lon_min = float(all_atts.get('lon_min'))
            self.lon_max = float(all_atts.get('lon_max'))
            self.nom_lon_spacing = float(all_atts.get('nominal_lon_spacing'))
            self.nom_lat_spacing = float(all_atts.get('nominal_lat_spacing'))
            self.num_lon = int(all_atts.get('nlon'))
            self.num_lat = int(all_atts.get('nlat'))
            self.event_id = all_atts.get('event_id')
            self.magnitude = float(all_atts.get('magnitude'))
            self.depth = float(all_atts.get('depth'))
            self.lat = float(all_atts.get('lat'))
            self.lon = float(all_atts.get('lon'))
            self.description = all_atts.get('event_description')
            
            self.sorted_by = ''
            
            self.fields = [child.attrib['name']
                           for child in root
                           if 'grid_field' in child.tag]
            
            grid_str = [child.text
                        for child in root
                        if 'grid_data' in child.tag][0]
            
            #get rid of trailing and leading white space
            grid_str = grid_str.lstrip().rstrip()
            
            # break into point strings
            grid_lst = grid_str.split('\n')
            
            # split points and save them as Point objects
            for point_str in grid_lst:
                point_str = point_str.lstrip().rstrip()
                point_lst = point_str.split(' ')
            
                point = Point()
                for count, field in enumerate(self.fields):
                    point.info[field] = float(point_lst[count])
                        
                self.grid += [point]

        except:
            return False
        
    def sort_grid(self, metric= ''):
        """
        Sorts the grid by a specified metric
        """
        Point.sort_by = metric
        try:
            self.grid = sorted(self.grid)
            self.sorted_by = metric
            return True
        except:
            return False
    
    def in_grid(self, lon_min=0, lon_max=0, lat_min=0, lat_max=0):
        """
        Check if a point is within the boundaries of the grid
        """
        return ((lon_min > self.lon_min and
                    lon_min < self.lon_max and
                    lat_min > self.lat_min and
                    lat_min < self.lat_max) or
                (lon_min > self.lon_min and
                    lon_min < self.lon_max and
                    lat_max > self.lat_min and
                    lat_max < self.lat_max) or
                (lon_max > self.lon_min and
                    lon_max < self.lon_max and
                    lat_min > self.lat_min and
                    lat_min < self.lat_max) or
                (lon_max > self.lon_min and
                    lon_max < self.lon_max and
                    lat_max > self.lat_min and
                    lat_max < self.lat_max))
    
    def max_shaking(self,
                    lon_min=0,
                    lon_max=0,
                    lat_min=0,
                    lat_max=0,
                    metric=None,
                    facility=None):
        
        '''
        Will return a float with the largest shaking in a specified
        region. If no grid points are found within the region, the
        region is made larger until a point is present
        
        Returns:
            int: -1 if max shaking can't be determined, otherwise shaking level
        '''
    
        if facility is not None:
            try:
                lon_min = facility.lon_min
                lon_max = facility.lon_max
                lat_min = facility.lat_min
                lat_max = facility.lat_max
                metric = facility.metric
            except:
                return -1
            
        if not self.grid:
            return None

        # check if the facility lies in the grid
        if not facility.in_grid(self):
            return {facility.metric: 0}
        
        # check if the facility's metric exists in the grid
        if not self.grid[0].info.get(facility.metric, None):
            return {facility.metric: None}
        
        # sort the grid in an attempt to speed up processing on
        # many facilities
        if self.sorted_by != 'LON':
            self.sort_grid('LON')
        
        # figure out where in the point list we should look for shaking
        start = int((lon_min - self.grid[0].info['LON']) / self.nom_lon_spacing) - 1
        end = int((lon_max - self.grid[0].info['LON']) / self.nom_lon_spacing) + 1
        if start < 0:
            start = 0
        
        shaking = []
        while not shaking:
            shaking = [point for point in self.grid[start:end] if
                                        (point.info['LAT'] > lat_min and
                                         point.info['LAT'] < lat_max)]
            
            # make the rectangle we're searching in larger to encompass
            # more points
            lon_min -= .01
            lon_max += .01
            lat_min -= .01
            lat_max += .01
            start -= 1
        
        Point.sort_by = metric
        shaking = sorted(shaking)
        return shaking[-1].info

       
class Mailer(object):
    """
    Keeps track of information used to send emails
    
    If a proxy is setup, Mailer will try to wrap the smtplib module
    to access the smtp through the proxy
    """
    
    def __init__(self):
        # get info from the config
        sc = SC()
        
        self.me = sc.smtp_from
        self.username = sc.smtp_username
        self.password = sc.smtp_password
        self.server_name = sc.smtp_server
        self.server_port = sc.smtp_port
        self.log = ''
        
        if sc.use_proxy is True:
            # try to wrap the smtplib library with the socks module
            if sc.proxy_username and sc.proxy_password:
                try:
                    socks.set_default_proxy('socks.PROXY_TYPE_SOCKS4',
                                            sc.proxy_server,
                                            sc.proxy_port,
                                            username=sc.proxy_username,
                                            password=sc.proxy_password)
                    socks.wrap_module(smtplib)
                except:
                    try:
                        socks.set_default_proxy('socks.PROXY_TYPE_SOCKS5',
                                            sc.proxy_server,
                                            sc.proxy_port,
                                            username=sc.proxy_username,
                                            password=sc.proxy_password)
                        socks.wrap_module(smtplib)
                    except:
                        try:
                            socks.set_default_proxy('socks.PROXY_TYPE_SOCKS4',
                                            sc.proxy_server,
                                            sc.proxy_port)
                            socks.wrap_module(smtplib)
                        except:
                            try:
                                socks.set_default_proxy('socks.PROXY_TYPE_SOCKS5',
                                                sc.proxy_server,
                                                sc.proxy_port)
                                socks.wrap_module(smtplib)
                            except:
                                self.log += 'Unable to access SMTP through proxy'
                                
            else:
                try:
                    socks.set_default_proxy('socks.PROXY_TYPE_SOCKS4',
                                    sc.proxy_server,
                                    sc.proxy_port)
                    socks.wrap_module(smtplib)
                except:
                    try:
                        socks.set_default_proxy('socks.PROXY_TYPE_SOCKS5',
                                        sc.proxy_server,
                                        sc.proxy_port)
                        socks.wrap_module(smtplib)
                    except:
                        self.log += 'Unable to access SMTP through proxy'
        
    def send(self, msg=None, you=None, debug=False):
        """
        Send an email (msg) to specified addresses (you) using SMTP
        server details associated with the object
        """
        server = smtplib.SMTP(self.server_name, self.server_port) #port 465 or 587
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(self.username, self.password)
        
        server.sendmail(self.me, you, msg.as_string())
        server.quit()


class SC(object):
    """
    Holds application custimization settings
    
    Attributes:
        timezone (int): How many hours to offset from UTC
        new_eq_mag_cutoff (float): Lowest magnitude earthquake app stores
        check_new_int (int): how often to check db for new eqs
        use_geo_json (bool): False if using PDL
        geo_json_web (str): The web address where app gets json feed
        geo_json_int (int): How many seconds between running geo_json
        archive_mag (float): Min mag that is auto-archived
        keep_eq_for (int): Days before eq is deleted
        eq_req_products (list): Which products should be downloaded from web
        log_rotate (int): Days between log rotations
        log_file (str): Name of the log file
        log_level (str): Low, Normal, or High
        db_type (str): sqlite, mysql, ... (only tested with sqlite)
        db_password (str): For access to database
        db_username (str): For access to database
        db_retry_count (int): Attempts to access db
        db_retry_interval (int): Wait time between attempts to access db
        smtp_server (str): Name of smtp (smtp.gmail.com)
        smtp_security (str): SSL, TLS
        smtp_port (int): Default 587 for SMTP
        smtp_password (str): for SMTP access
        smtp_username (str): for SMTP access
        smtp_envelope_from (str): Mail to be sent from
        smtp_from (str): Mail to be sent from
        default_template_new_event (str): New event notification template name
        default_template_inspection (str): Inspection notificaiton template name
        default_template_pdf (str): PDF template name
        use_proxy (bool): Whether or not to traffic through proxy
        proxy_username (str): For proxy access
        proxy_password (str): For proxy access
        proxy_server (str): Name of proxy server
        proxy_port (int): Which port to use for proxy
        server_name (str): What the admin chooses to call the instance
        server_dns (str): How the instance is accessed
        software_version (str): Implemented pyCast software
        gmap_key (str): Holds the google maps key, used for static maps
    """
    
    def __init__(self):
        self.timezone = 0
        self.new_eq_mag_cutoff = 0.0
        self.night_eq_mag_cutoff = 0.0
        self.nighttime = 0
        self.morning = 0
        self.check_new_int = 0
        self.use_geo_json = False
        self.geo_json_web = ''
        self.geo_json_int = 0
        self.archive_mag = 0.0
        self.keep_eq_for = 0
        self.eq_req_products = []
        self.ignore_nets = []
        self.log_rotate = 0
        self.log_file = ''
        self.log_level = 0
        self.db_type = ''
        self.db_password = ''
        self.db_username = ''
        self.db_retry_count = 0
        self.db_retry_interval = 0
        self.smtp_server = ''
        self.smtp_security = ''
        self.smtp_port = 0
        self.smtp_password = ''
        self.smtp_username = ''
        self.smtp_envelope_from = ''
        self.smtp_from = ''
        self.default_template_new_event = ''
        self.default_template_inspection = ''
        self.default_template_pdf = ''
        self.use_proxy = False
        self.proxy_username = ''
        self.proxy_password = ''
        self.proxy_server = ''
        self.proxy_port = 0
        self.server_name = ''
        self.server_dns = ''
        self.software_version = ''
        self.json = ''
        self.conf_file_location = ''
        self.gmap_key = ''
    
        self.load()
    
    def load(self):
        """
        Load information from database to the SC object
        
        Returns:
            None
        """
        
        conf_dir = self.get_conf_dir()
        self.conf_file_location = os.path.join(conf_dir, 'sc.json')
            
        conf_file = open(self.conf_file_location, 'r')
        conf_str = conf_file.read()
        self.json = conf_str
        conf_json = json.loads(conf_str)
        self.dict = conf_json

        # timezone
        self.timezone = conf_json['timezone']
        self.gmap_key = conf_json['gmap_key']
        
        # Services
        self.new_eq_mag_cutoff = conf_json['Services']['new_eq_mag_cutoff']
        self.night_eq_mag_cutoff = conf_json['Services']['night_eq_mag_cutoff']
        self.nighttime = conf_json['Services']['nighttime']
        self.morning = conf_json['Services']['morning']
        self.check_new_int = conf_json['Services']['check_new_int']
        self.use_geo_json = conf_json['Services']['use_geo_json']
        self.geo_json_int = conf_json['Services']['geo_json_int']
        self.archive_mag = conf_json['Services']['archive_mag']
        self.keep_eq_for = conf_json['Services']['keep_eq_for']
        self.geo_json_web = conf_json['Services']['geo_json_web']
        self.ignore_nets = conf_json['Services']['ignore_nets']
        self.eq_req_products = conf_json['Services']['eq_req_products']
        
        
        # Logging
        self.log_rotate = conf_json['Logging']['log_rotate']
        self.log_file = conf_json['Logging']['log_file']
        self.log_level = conf_json['Logging']['log_level']
        
        # DBConnection
        self.db_type = conf_json['DBConnection']['type']
        self.db_password = conf_json['DBConnection']['password']
        self.db_username = conf_json['DBConnection']['username']
        self.db_retry_count = conf_json['DBConnection']['retry_count']
        self.db_retry_interval = conf_json['DBConnection']['retry_interval']
        
        # SMTP
        self.smtp_server = conf_json['SMTP']['server']
        self.smtp_security = conf_json['SMTP']['security']
        self.smtp_port = conf_json['SMTP']['port']
        self.smtp_password = conf_json['SMTP']['password']
        self.smtp_username = conf_json['SMTP']['username']
        self.smtp_envelope_from = conf_json['SMTP']['envelope_from']
        self.smtp_from = conf_json['SMTP']['from']
        
        # Notification
        self.default_template_new_event = conf_json['Notification']['default_template_new_event']
        self.default_template_inspection = conf_json['Notification']['default_template_inspection']
        self.default_template_pdf = conf_json['Notification']['default_template_pdf']
        
        # Proxy
        self.use_proxy = conf_json['Proxy']['use']
        self.proxy_username = conf_json['Proxy']['username']
        self.proxy_password = conf_json['Proxy']['password']
        self.proxy_server = conf_json['Proxy']['server']
        self.proxy_port = conf_json['Proxy']['port']
        
        # Server
        self.server_name = conf_json['Server']['name']
        self.server_dns = conf_json['Server']['DNS']
        self.software_version = conf_json['Server']['update']['software_version']
    
    def validate(self):
        return True

    def save_dict(self):
        json_str = json.dumps(self.dict)
        self.save(json_str)
    
    def save(self, json_str=None):
        conf_file = open(self.conf_file_location, 'w')
        if json_str is None:
            conf_file.write(self.json)
        else:
            conf_file.write(json_str)
        conf_file.close()
    
    @staticmethod
    def get_conf_dir():
        """
        Determine where the conf directory is
        
        Returns:
            str: The absolute path the the conf directory
        """
        
        # Get directory location for database
        path = os.path.dirname(os.path.abspath(__file__))
        delim = get_delim()
        path = path.split(delim)
        path[-1] = 'conf'
        directory = os.path.normpath(delim.join(path))
        
        return directory
    
    def make_backup(self):
        conf_dir = self.get_conf_dir()
        # copy sc_config file
        copyfile(os.path.join(conf_dir, 'sc.json'),
                 os.path.join(conf_dir, 'sc_back.json'))
        
    def revert(self):
        conf_dir = self.get_conf_dir()
        # copy sc_config file
        copyfile(os.path.join(conf_dir, 'sc_back.json'),
                 os.path.join(conf_dir, 'sc.json'))
        self.load()


class NotificationBuilder(object):
    """
    Uses Jinja to build notifications
    """
    def __init__(self):
        pass
    
    @staticmethod
    def build_new_event_html(events=None, notification=None, group=None, name=None, web=False, config=None):
        temp_manager = TemplateManager()
        if not config:
            config = temp_manager.get_configs('new_event', name=name)

        template = temp_manager.get_template('new_event', name=name)
        
        return template.render(events=events,
                               group=group,
                               notification=notification,
                               sc=SC(),
                               config=config,
                               web=web)
    
    @staticmethod
    def build_insp_html(shakemap, name=None, web=False, config=None):
        temp_manager = TemplateManager()
        if not config:
            config = temp_manager.get_configs('inspection', name=name)
        
        template = temp_manager.get_template('inspection', name=name)

        facility_shaking = shakemap.facility_shaking
        fac_details = {'all': 0, 'grey': 0, 'green': 0,
                       'yellow': 0, 'orange': 0, 'red': 0}
        
        for fs in facility_shaking:
            fac_details['all'] += 1
            fac_details[fs.alert_level] += 1
        
        return template.render(shakemap=shakemap,
                               facility_shaking=facility_shaking,
                               fac_details=fac_details,
                               sc=SC(),
                               config=config,
                               web=web)

    @staticmethod
    def build_update_html(update_info=None):
        '''
        Builds an update notification using a jinja2 template
        '''
        template_manager = TemplateManager()
        template = template_manager.get_template('system', name='update')

        return template.render(update_info=update_info)


class TemplateManager(object):
    """
    Manages templates and configs for emails
    """

    @staticmethod
    def get_configs(not_type, name=None):
        if name is None:
            temp_name = 'default.json'
        else:
            temp_name = name.lower() + '.json'

        try:
            conf_file = os.path.join(sc_dir(),
                                    'templates',
                                    not_type,
                                    temp_name)
            conf_str = open(conf_file, 'r')
            config = json.loads(conf_str.read())
            conf_str.close()
            return config
        except Exception:
            return None

    @staticmethod
    def save_configs(not_type, name, config):
        if isinstance(config, dict):
            conf_file = os.path.join(sc_dir(),
                                    'templates',
                                    not_type,
                                    name + '.json')
            conf_str = open(conf_file, 'w')
            conf_str.write(json.dumps(config))
            conf_str.close()
            return config
        else:
            return None

    @staticmethod
    def get_template(not_type, name=None):
        if name is None:
            temp_name = 'default.html'
        else:
            temp_name = name + '.html'

        temp_file = os.path.join(sc_dir(),
                                    'templates',
                                    not_type,
                                    temp_name)
        try:
            temp_str = open(temp_file, 'r')
            template = Template(temp_str.read())
            temp_str.close()
            return template
        except Exception:
            return None

    @staticmethod
    def get_template_names():
        '''
        Get a list of the existing template names
        '''
        temp_folder = os.path.join(sc_dir(),
                                   'templates',
                                   'new_event')
        file_list = os.listdir(temp_folder)

        # get the names of the templates
        just_names = [f.split('.')[0] for f in file_list if f[-5:] == '.json']
        return just_names
    
class URLOpener(object):
    """
    Either uses urllib2 standard opener to open a URL or returns an
    opener that can run through a proxy
    """
    
    @staticmethod
    def open(url):
        """
        Args:
            url (str): a string url that will be opened and read by urllib2
            
        Returns:
            str: the string read from the webpage
        """

        # create context to avoid certificate errors
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        except:
            ctx = None

        try:
            sc = SC()
            if sc.use_proxy is True:
                if sc.proxy_username and sc.proxy_password:
                    proxy = urllib2.ProxyHandler({
                                'http': "http://{0}:{1}@{2}:{3}".format(sc.proxy_username,
                                                                        sc.proxy_password,
                                                                        sc.proxy_server,
                                                                        sc.proxy_port),
                                'https': "http://{0}:{1}@{2}:{3}".format(sc.proxy_username,
                                                                         sc.proxy_password,
                                                                         sc.proxy_server,
                                                                         sc.proxy_port)})
                    auth = urllib2.HTTPBasicAuthHandler()
                    opener = urllib2.build_opener(proxy, auth, urllib2.HTTPHandler)
                    
                    if ctx is not None:
                        url_obj = opener.open(url, timeout=60, context=ctx)
                    else:
                        url_obj = opener.open(url, timeout=60)

                    url_read = url_obj.read()
                    url_obj.close()
                    return url_read
                    
                else:
                    proxy = urllib2.ProxyHandler({'http': 'http://{0}:{1}'.format(sc.proxy_server,sc.proxy_port),
                                                  'https': 'https://{0}:{1}'.format(sc.proxy_server,sc.proxy_port)})
                    opener = urllib2.build_opener(proxy)
                    
                    if ctx is not None:
                        url_obj = opener.open(url, timeout=60, context=ctx)
                    else:
                        url_obj = opener.open(url, timeout=60)
                        
                    url_read = url_obj.read()
                    url_obj.close()
                    return url_read
    
            else:
                if ctx is not None:
                    url_obj = urllib2.urlopen(url, timeout=60, context=ctx)
                else:
                    url_obj = urllib2.urlopen(url, timeout=60)
                    
                url_read = url_obj.read()
                url_obj.close()
                return url_read
        except Exception as e:
            raise Exception('URLOpener Error({}: {}, url: {})'.format(type(e),
                                                             e,
                                                             url))
        

class Clock(object):
    '''
    Keeps track of utc and application time as well as night and day
    
    Attributes:
        utc_time (str): current utc_time
        app_time (str): current time for application users
    '''
    def __init__(self):
        self.utc_time = ''
        self.app_time = ''
        
    def nighttime(self):
        '''
        Determine if it's nighttime
        
        Returns:
            bool: True if nighttime
        '''
        sc = SC()
        
        # get app time
        self.get_time()
        # compare to night time setting
        hour = int(self.app_time.strftime('%H'))        
        return bool(((hour >= sc.nighttime)
                        or hour < sc.morning))
        
    def get_time(self):
        sc = SC()
        self.utc_time = datetime.datetime.utcfromtimestamp(time.time())
        self.app_time = self.utc_time + datetime.timedelta(hours=sc.timezone)
        
    def from_time(self, time):
        sc = SC()
        utc_time = datetime.datetime.utcfromtimestamp(time)
        app_time = utc_time + datetime.timedelta(hours=sc.timezone)
        
        return app_time
  
  
class AlchemyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj.__class__, DeclarativeMeta):
            # an SQLAlchemy class
            fields = {}
            for field in [x for x in dir(obj) if not x.startswith('_') and x != 'metadata']:
                data = obj.__getattribute__(field)
                try:
                    json.dumps(data) # this will fail on non-encodable values, like other classes
                    fields[field] = data
                except TypeError:
                    try:
                        fields[field] = [str(d) for d in data]
                    except:
                        fields[field] = None
            # a json-encodable dict
            return fields
    
        return json.JSONEncoder.default(self, obj)


class SoftwareUpdater(object):
    '''
    Check against USGS web to determine 
    '''
    def __init__(self):
        sc = SC()
        self.json_url = sc.dict['Server']['update']['json_url']
        self.current_version = sc.dict['Server']['update']['software_version']
        self.current_update = sc.dict['Server']['update']['update_version']
        self.admin_notified = sc.dict['Server']['update']['admin_notified']
        self.sc_root_dir = root_dir()

    def get_update_info(self):
        """
        Pulls json feed from USGS web with update information
        """
        url_opener = URLOpener()
        json_str = url_opener.open(self.json_url)
        update_list = json.loads(json_str)

        return update_list

    def check_update(self, testing=False):
        '''
        Check the list of updates to see if any of them require 
        attention
        '''
        sc = SC()
        self.current_version = sc.dict['Server']['update']['software_version']

        update_list = self.get_update_info()
        update_required = False
        notify = False
        update_info = set()
        for update in update_list['updates']:
            if self.check_new_update(update['version'], self.current_version) is True:
                update_required = True
                update_info.add(update['info'])

                if self.check_new_update(update['version'], self.current_update) is True:
                    # update current update version in sc.conf json
                    sc = SC()
                    sc.dict['Server']['update']['update_version'] = update['version']

                    if testing is not True:
                        sc.save_dict()
                    notify = True
    
        return update_required, notify, update_info


    @staticmethod
    def check_new_update(new, existing):
        new_split = new.split('.')
        existing_split = existing.split('.')

        for i in range(3):
            new_split[i] = int(new_split[i])
            existing_split[i] = int(existing_split[i])

        return ((new_split[0] > existing_split[0]) or 
                    (new_split[0] == existing_split[0] and 
                        new_split[1] > existing_split[1]) or
                    (new_split[0] == existing_split[0] and 
                        new_split[1] == existing_split[1] and
                        new_split[2] > existing_split[2]))

    def notify_admin(self, update_info=None, testing=False):
        # notify admin
        admin_notified = False
        admin_notified = self.send_update_notification(update_info=update_info)

        if admin_notified is True:
            # record admin Notification
            sc = SC()
            sc.dict['Server']['update']['admin_notified'] = True
            if testing is not True:
                sc.save_dict()

    def update(self, testing=False):
        update_list = self.get_update_info()
        version = self.current_version
        sc = SC()
        delim = get_delim()
        failed = []
        success = []
        # concatinate files if user is multiple updates behind
        files = self.condense_files(update_list['updates'])
        for file_ in files:
            try:
                # download file
                url_opener = URLOpener()
                text_file = url_opener.open(file_['url'])

                # get the full path to the file
                file_path = delim.join([root_dir()] +
                                    file_['path'].split('/'))
                norm_file_path = os.path.normpath(file_path)

                # open the file
                file_to_update = open(norm_file_path, 'w')
                file_to_update.write(text_file)
                file_to_update.close()

                if self.check_new_update(file_['version'], version):
                    version = file_['version']
                success += [file_]
            except Exception:
                failed += [file_]
        # change software version
        if len(success) > 0:
            print 'SUCCESS: {}'.format(success)
        if len(failed) > 0:    
            print 'FAILED: {}'.format(failed)

        
        sc.dict['Server']['update']['software_version'] = version
        if testing is not True:
            sc.save_dict()

        return success, failed

    def condense_files(self, update_list):
        files = {}
        for update in update_list:
            for file_ in update['files']:
                file_['version'] = update['version']
                if files.get(file_['path'], False) is False:
                    files[file_['path']] = file_
                else:
                    # check if this update is newer
                    if self.check_new_update(file_['version'],
                                                files[file_['path']]['version']):
                        files[file_['path']] = file_
        
        # convert back to list
        file_list = []
        for key in files.keys():
            file_list.append(files[key])

        return file_list

    @staticmethod
    def send_update_notification(update_info=None):
        '''
        Create notification to alert admin of software updates
        '''
        try:
            not_builder = NotificationBuilder()
            html = not_builder.build_update_html(update_info=update_info)

            #initiate message
            msg = MIMEMultipart()
            msg_html = MIMEText(html, 'html')
            msg.attach(msg_html)

            # find the ShakeCast logo
            logo_str = os.path.join(sc_dir(),'view','static','sc_logo.png')
            
            # open logo and attach it to the message
            logo_file = open(logo_str, 'rb')
            msg_image = MIMEImage(logo_file.read())
            logo_file.close()
            msg_image.add_header('Content-ID', '<sc_logo>')
            msg_image.add_header('Content-Disposition', 'inline')
            msg.attach(msg_image)
            
            mailer = Mailer()
            me = mailer.me

            # get admin with emails
            session = Session()
            admin = session.query(User).filter(User.user_type.like('admin')).filter(User.email != '').all()
            emails = [a.email for a in admin]

            msg['Subject'] = 'ShakeCast Software Update'
            msg['To'] = ', '.join(emails)
            msg['From'] = me
            
            if len(emails) > 0:
                mailer.send(msg=msg, you=emails)
        
        except:
            return False

        return True