#!/usr/bin/env python3

# Dumps modem statistics from a tgiinet1 modem.

# Thanks to Shannon Wynter for his https://github.com/freman/nbntest/ , some
# details were found there

# Matt Johnston (c) 2018 
# MIT license, see bottom of file.
# matt@ucc.asn.au

import argparse
import sys
import logging
import binascii
import re
import json
import csv
import datetime
import time
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup
import toml
import srp

D = logging.debug
L = logging.info
W = logging.warning
E = logging.error

def setup_logging(debug = False):
    level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(format='%(asctime)s %(message)s', 
            datefmt='%d/%m/%Y %I:%M:%S %p',
            level=level)
    #logging.getLogger("asyncio").setLevel(logging.DEBUG)

class Fetcher(object):
    REQUEST_TIMEOUT = 30

    def __init__(self, config):
        self.config = config
        self.top_url = 'http://%s' % self.config['address']
        self.session = None

    def connect(self):
        """ Authenticates with the modem. 
        Returns a session on success or throws an exception 
        """
        session = requests.Session()

        ### Fetch CSRF
        csrf_url = '%s/login.lp?action=getcsrf' % self.top_url
        csrf = session.get(csrf_url, timeout = self.REQUEST_TIMEOUT).text
        if len(csrf) != 64:
            D("csrf %s", csrf)
            raise Exception("Bad csrf response")
        D("csrf: %s" % csrf)

        ### Perform SRP
        srp_user = srp.User(self.config['username'], self.config['password'],
            hash_alg=srp.SHA256, ng_type=srp.NG_2048)
        # Bit of a bodge. Seems the router uses a custom k value? Thanks to nbntest
        if hasattr(srp._mod, 'BN_hex2bn'):
            # _mod == _ctsrp, openssl
            srp._mod.BN_hex2bn(srp_user.k, b'05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300')
        else:
            # _mod == _pysrp, pure python
            srp_user.k = int('05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300', 16)

        I, A = srp_user.start_authentication()
        A = binascii.hexlify(A)
        D("A: %d %s" % (len(A), A))

        auth_url = '%s/authenticate' % self.top_url
        req_data = {
            'I': I, 
            'A': A, 
            'CSRFtoken': csrf
        }
        ### Send the first SRP request
        auth1 = session.post(auth_url, data=req_data, timeout = self.REQUEST_TIMEOUT)
        if auth1.status_code != 200:
            D(auth1.text)
            raise Exception("Error authenticating %d" % auth1.status_code)
        j = auth1.json()
        s, B = j['s'], j['B']
        D("s: %d %s" % (len(s), s))
        D("B: %d %s" % (len(B), B))
        s = binascii.unhexlify(s)
        B = binascii.unhexlify(B)

        M = srp_user.process_challenge(s, B)
        M = binascii.hexlify(M)
        D("M: %d %s" % (len(M), M))
        req_data = {
            'M': M, 
            'CSRFtoken': csrf
        }
        ### Send our reponse to the SRP challenge
        auth2 = session.post(auth_url, data=req_data, timeout = self.REQUEST_TIMEOUT)

        if auth2.status_code != 200:
            D(auth2.text)
            raise Exception("Didn't connect, error %d" % auth2.status_code)

        j = auth2.json()
        if 'error' in j:
            D(j)
            raise Exception("Authentication error. Wrong password? (%s)" % j['error'])

        return session

    def get(self):
        if not self.session:
            self.session = self.connect()

        modem_url = '%s/modals/broadband-bridge-modal.lp' % self.top_url
        r = self.session.get(modem_url, timeout = self.REQUEST_TIMEOUT)

        gateway_url = '%s/modals/gateway-modal.lp' % self.top_url
        g = self.session.get(gateway_url, timeout = self.REQUEST_TIMEOUT)

        return r.text, g.text

# helpers to get things out of BeautifulSoup objects

def fetch_string(soup, title):
    lr = soup.find_all(string=title)
    if not lr:
        W("Failed to fetch %s" % title)
        return ""
    D(title)
    D(lr[0].parent.parent)
    return lr[0].parent.parent.find_next('span').text

def fetch_pair(soup, title, unit):
    # Find the label
    lr = soup.find_all(string=title)
    if not lr:
        # failed. Perhaps the modem is unsynced
        W("Failed to fetch pair %s" % title)
        return 0.0,0.0
    # Traverse up to the parent div that also includes the values.
    # Search that div for text with the units (Mbps, dB etc)
    updown = lr[0].parent.parent.find_all(string=re.compile(unit))
    # Extract the float out of eg "4.85 Mbps"
    return (float(t.replace(unit,'').strip()) for t in updown)

def fetch_line_attenuation(soup, r):
    """ Special case since VDSL has 3 values each for up/down 
        eg "22.5, 64.9, 89.4 dB"
        (measuring attenuation in 3 different frequency bands?)
        we construct {up,down}_attenuation{1,2,3}
    """
    title = "Line Attenuation"
    unit = "dB"
    lr = soup.find_all(string=title)
    if not lr:
        W("Failed to fetch attenuation")
        return
    updown = lr[0].parent.parent.find_all(string=re.compile(unit))
    for dirn, triple in zip(("up", "down"), updown):
        # [:3] to get rid of N/A from the strange "2.8, 12.8, 18.9,N/A,N/A dB 7.8, 16.7, 24.3 dB"
        vals = (v.strip() for v in triple.replace(unit, '').split(',')[:3])
        for n, t in enumerate(vals, 1):
            r['%s_attenuation%d' % (dirn, n)] = float(t)

def fetch_uptime(soup, name):
    """ Returns uptime in seconds """
    uptime = fetch_string(soup, name)
    mat = re.match(r'(?:(\d+)days)? *(?:(\d+)hours)? *(?:(\d+)min)? *(?:(\d+)sec)?', uptime)
    d,h,m,s = (int(x) for x in mat.groups(0))
    return int(datetime.timedelta(days=d, hours=h, minutes=m, seconds=s).total_seconds())

def parse_broadband(res, html):
    """
    Parses the contents of http://10.1.1.1/modals/broadband-bridge-modal.lp
    to extract link values. 

    The tg-1 doesn't have id attributes so we have to find text labels.
    """
    soup = BeautifulSoup(html, 'html.parser')

    res['datetime'] = str(datetime.datetime.now())
    res['up_rate'], res['down_rate'] = fetch_pair(soup, "Line Rate", 'Mbps')
    res['up_maxrate'], res['down_maxrate'] = fetch_pair(soup, "Maximum Line rate", 'Mbps')
    res['up_power'], res['down_power'] = fetch_pair(soup, "Output Power", 'dBm')
    res['up_noisemargin'], res['down_noisemargin'] = fetch_pair(soup, "Noise Margin", 'dB')
    res['up_transferred'], res['down_transferred'] = fetch_pair(soup, "Data Transferred", "MBytes")
    fetch_line_attenuation(soup, res)
    res['dsl_uptime'] = fetch_uptime(soup ,'DSL Uptime')
    res['dsl_mode'] = fetch_string(soup, 'DSL Mode')
    res['dsl_type'] = fetch_string(soup, 'DSL Type')
    res['dsl_status'] = fetch_string(soup, 'DSL Status')

    # integer kbps are easier to work with in scripts
    for n in 'down_rate', 'up_rate', 'down_maxrate', 'up_maxrate':
        res[n] = int(res[n] * 1000)

    return res

def parse_gateway(res, html):
    """ Parses the contents of http://10.1.1.1/modals/gateway-modal.lp """
    soup = BeautifulSoup(html, 'html.parser')
    names = [
        'Product Vendor',
        'Product Name',
        'Software Version',
        'Firmware Version',
        'Hardware Version',
        'Serial Number',
        'MAC Address',
    ]
    for n in names:
        res[n.lower().replace(' ', '_')] = fetch_string(soup, n)

    res['uptime'] = fetch_uptime(soup, 'Uptime')

def fix_wrap(stats, config):
    # (when polling) handle up/down transferred wrap around
    if 'last_uptime' not in config or stats['uptime'] < config['last_uptime']:
        # reboot or first time
        config.update({
            'last_up_transferred': 0,
            'last_down_transferred': 0,
            'up_wraps': 0,
            'down_wraps': 0,
            'last_uptime': 0
        })
    else:
        if stats['up_transferred'] < config['last_up_transferred']:
            config['up_wraps'] += 1
        if stats['down_transferred'] < config['last_down_transferred']:
            config['down_wraps'] += 1
    # save last values
    config.update({
        'last_up_transferred': stats['up_transferred'],
        'last_down_transferred': stats['down_transferred'],
        'last_uptime': stats['uptime']
    });
    # update tally to include wraps
    stats['up_transferred'] += 4096 * config['up_wraps']
    stats['down_transferred'] += 4096 * config['down_wraps']

def print_plain(stats):
    print('\n'.join('%s %s' % (str(k), str(v)) for k, v in stats.items()))

def print_json(stats):
    print(json.dumps(stats, indent=4))

def print_csv(stats):
    csv.writer(sys.stdout).writerow(stats.values())

def print_csv_headers(stats):
    csv.writer(sys.stdout).writerow(stats.keys())

def fetch_and_output(config, from_broadband = None, from_gateway = None, json = False, csv = False, csv_headers = False):
    stats_page = None
    gateway_page = None

    if from_broadband:
        from_broadband.seek(0)
        stats_page = from_broadband.read()
    if from_gateway:
        from_gateway.seek(0)
        gateway_page = from_gateway.read()

    if not from_gateway and not from_broadband:
        f = Fetcher(config)
        stats_page, gateway_page = f.get()
        D(stats_page)

    stats = OrderedDict()
    if stats_page:
        parse_broadband(stats, stats_page)
    if gateway_page:
        parse_gateway(stats, gateway_page)

    fix_wrap(stats, config)

    if json:
        print_json(stats)
    elif csv:
        if csv_headers:
            print_csv_headers(stats)
        print_csv(stats)
    else:
        print_plain(stats)

def main():
    parser = argparse.ArgumentParser(description=
"""Retrieves speed and other statistics from a Technicolor/iinet TG-1 or TG-789 modem.\n
Configure your details in tgiistat.toml\n 
"""
)
    parser.add_argument('--config', '-c', type=str, default='tgiistat.toml', help='Default is tgiistat.toml')
    parser.add_argument('--debug', '-d', action="store_true")
    parser.add_argument('--json', action="store_true", help="JSON output")
    parser.add_argument('--csv', action="store_true", help="CSV output")
    parser.add_argument('--csv-headers', action="store_true", help="CSV-style headers")
    parser.add_argument('--poll', '-p', type=int, default=0, help='interval (in seconds) between polls')
    # --parse is useful for debugging parse() from a saved broadband-bridge-modal.lp html file
    parser.add_argument('--parse', type=argparse.FileType('r'), help="Parse html from a file", metavar='broadband-bridge-modal.lp')
    parser.add_argument('--gwparse', type=argparse.FileType('r'), help="Parse gateway html from a file", metavar='gateway-modal.lp')

    args = parser.parse_args()

    setup_logging(args.debug)
    with open(args.config) as c:
        config_text = c.read()
    config = toml.loads(config_text)

    if args.poll:
        csv_headers = args.csv_headers
        while True:
            try:
                fetch_and_output(config, args.parse, args.gwparse, args.json, args.csv, csv_headers)
                sys.stdout.flush()
                csv_headers = False # first time only
            except Exception as e:
                E(e)
            time.sleep(args.poll)
    else:
        fetch_and_output(config, args.parse, args.gwparse, args.json, args.csv, args.csv_headers)


if __name__ == '__main__':
    main()

# Copyright (c) 2018 Matt Johnston
# All rights reserved.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
