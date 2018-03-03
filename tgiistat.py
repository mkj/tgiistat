#!/usr/bin/env python3

import argparse
import sys
import logging
import binascii

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
    def __init__(self, config):
        self.config = config
        self.top_url = 'http://%s' % self.config['address']
        self.session = None

    # succeeds or throws an exception
    def connect(self):
        self.session = requests.Session()
        csrf_url = '%s/login.lp?action=getcsrf' % self.top_url
        csrf = self.session.get(csrf_url).text
        if len(csrf) != 64:
            D("csrf %s", csrf)
            raise Exception("Bad csrf response")
        D("csrf: %s" % csrf)

        srp_user = srp.User(self.config['username'], self.config['password'],
            hash_alg=srp.SHA256, ng_type=srp.NG_2048)
        # XXX bodge: SRP-6 needs k=3 instead
        #srp._mod.BN_hex2bn(srp_user.k, b'03')
        srp._mod.BN_hex2bn(srp_user.k, b'05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300')

        I, A = srp_user.start_authentication()
        A = binascii.hexlify(A)
        D("A: %d %s" % (len(A), A))

        auth_url = '%s/authenticate' % self.top_url
        req_data = {
            'I': I, 
            'A': A, 
            'CSRFtoken': csrf
        }
        auth1 = self.session.post(auth_url, data=req_data)
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
        auth2 = self.session.post(auth_url, data=req_data)

        if auth2.status_code != 200:
            D(auth2.text)
            raise Exception("Didn't connect, error %d" % auth2.status_code)

        j = auth2.json()
        if 'error' in j:
            D(j)
            raise Exception("Error auth: %s" % j['error'])

    def fetch(self):
        if not self.session:
            self.connect()

        modem_url = '%s/modals/broadband-bridge-modal.lp' % self.top_url
        r = self.session.get(modem_url)
        print(r.text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', type=str, default='tgiistat.toml')
    parser.add_argument('--debug', '-d', action="store_true")

    args = parser.parse_args()

    setup_logging(args.debug)
    with open(args.config) as c:
        config_text = c.read()
    config = toml.loads(config_text)

    f = Fetcher(config)
    f.fetch()
    

if __name__ == '__main__':
    main()

