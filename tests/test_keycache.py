"""
Test the keycache
"""

import os, stat
import sys
import tempfile
import shutil
import unittest
from unittest import mock
from scitokens.utils.keycache import KeyCache
from scitokens.utils.errors import UnableToCreateCache
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

# Python 3 vs. Python 2
try:
    from urllib.error import URLError
except ImportError:
    from urllib2 import URLError

import create_webserver


class TestKeyCache(unittest.TestCase):
    """
    Test the creation of a simple SciToken
    """

    def setUp(self):


        # Force the keycache to create a cache in a new directory
        self.tmp_dir = tempfile.mkdtemp()
        self.old_xdg = os.environ.get('XDG_CACHE_HOME', None)
        os.environ['XDG_CACHE_HOME'] = self.tmp_dir
        # Clear the cache
        self.keycache = KeyCache()

        # make sure it made the directory where I wanted it
        self.assertTrue(self.keycache.cache_location.startswith(self.tmp_dir))
        self.assertTrue(os.path.exists(self.keycache.cache_location))


    def tearDown(self):
        shutil.rmtree(self.tmp_dir)
        if self.old_xdg:
            os.environ['XDG_CACHE_HOME'] = self.old_xdg
        # Clean up, delete everything

    @mock.patch("os.makedirs", side_effect=OSError)
    @mock.patch.dict("os.environ")
    def test_cannot_make_cache(self, _):
        """
        Test when the keycache shouldn't be able to make the cache
        """
        os.environ['XDG_CACHE_HOME'] = "/does/not/exists"

        # Make sure it raises an unable to create cache exception
        with self.assertRaises(UnableToCreateCache):
            keycache = KeyCache()
            del keycache

    @unittest.skipIf(sys.platform.startswith("win"), "Test doesn't work on Windows")
    @unittest.skipIf(not sys.platform.startswith("win") and os.getuid() == 0, "Test doesn't work when root")
    def test_cannot_make_cache_permission_denied(self):
        """
        Test when the keycache shouldn't be able to make the cache due to access privilege
        """
        os.environ['XDG_CACHE_HOME'] = self.tmp_dir

        # Limiting access privilege to read-only for the $XDG_CACHE_HOME
        os.chmod(
            self.tmp_dir,
            stat.S_IRUSR |  # Read for user
            stat.S_IRGRP |  # Read for group
            stat.S_IROTH    # Read for other
        )

        # Make sure it raises an unable to create cache exception
        with self.assertRaises(UnableToCreateCache):
            keycache = KeyCache()
            del keycache

        # Revert the access privilege alteration for the $XDG_CACHE_HOME
        os.chmod(
            self.tmp_dir,
            stat.S_IRWXU |  # Read, write, and execute for user
            stat.S_IRWXG |  # Read, write, and execute for group
            stat.S_IRWXO    # Read, write, and execute for other
        )

    def test_empty(self):
        """
        Test when the keycache should be empty
        """
        # Stand up an HTTP server
        private_key = generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_numbers = private_key.public_key().public_numbers()
        test_id = "thisisatestid"
        server_address = create_webserver.start_server(public_numbers.n, public_numbers.e, test_id)
        print(server_address)
        # Now try to get the public key from the server
        pubkey_from_keycache = self.keycache.getkeyinfo("http://localhost:{}/".format(server_address[1]),
                                 test_id,
                                 insecure=True)

        # Now compare the 2 public keys
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        pubkey_pem_from_keycache = pubkey_from_keycache.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.assertEqual(public_pem, pubkey_pem_from_keycache)

        create_webserver.shutdown_server()

    def test_populated(self):
        """
        Test when there should be some entries populated in the sqllite DB
        """
        # Create a pem encoded public key
        private_key = generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.keycache.addkeyinfo("https://doesnotexists.edu/", "blahstuff", public_key, cache_timer=60)

        # Now extract the just inserted key
        pubkey = self.keycache.getkeyinfo("https://doesnotexists.edu/", "blahstuff")

        public_pem2 = pubkey.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.assertEqual(public_pem, public_pem2)

        # Make sure it errors with urlerror when it should not exist
        with self.assertRaises(URLError):
            self.keycache.getkeyinfo("https://doesnotexists.edu/", "asdf")


    def test_cache_timer(self):
        """
        Test if the cache max-age is retrieved from the HTTPS resource
        """
        private_key = generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_numbers = private_key.public_key().public_numbers()
        test_id = "thisisatestid"
        server_address = create_webserver.start_server(public_numbers.n, public_numbers.e, test_id)
        print(server_address)

        _, cache_timer = self.keycache._get_issuer_publickey("http://localhost:{}/".format(server_address[1]),
                                            key_id=test_id,
                                            insecure=True)

        self.assertEqual(cache_timer, 345600)
        create_webserver.shutdown_server()

    def test_cache_update_time(self):
        """
        Test if the cache next_update works
        """
        # Create a pem encoded public key
        private_key = generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.keycache.addkeyinfo("https://doesnotexists.edu/", "blahstuff", public_key, cache_timer=60, next_update=-1)

        # Even though the cache is still valid, the next update is triggered
        # We should still get the key, even though the next update fails
        # (invalid url)
        pubkey = self.keycache.getkeyinfo("https://doesnotexists.edu/", "blahstuff")

        public_pem2 = pubkey.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.assertEqual(public_pem, public_pem2)

    def test_cache_update_trigger(self):
        """
        Test when the next_update triggers and goes to the webserver
        """
        # Stand up an HTTP server
        private_key = generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_numbers = private_key.public_key().public_numbers()
        test_id = "thisisatestid"
        server_address = create_webserver.start_server(public_numbers.n, public_numbers.e, test_id)
        print(server_address)

        # Create a pem encoded public key, just to insert, want to make sure
        # it downloads from the server
        tmp_private_key = generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = tmp_private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # Now try to get the public key from the server
        self.keycache.addkeyinfo("http://localhost:{}/".format(server_address[1]),
                                 test_id,
                                 public_key,
                                 cache_timer=60,
                                 next_update=-1)

        # Next update should trigger now
        pubkey_from_keycache = self.keycache.getkeyinfo("http://localhost:{}/".format(server_address[1]),
                                 test_id,
                                 insecure=True)

        # Now compare the 2 public keys
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        pubkey_pem_from_keycache = pubkey_from_keycache.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.assertEqual(public_pem, pubkey_pem_from_keycache)

        create_webserver.shutdown_server()


if __name__ == '__main__':
    unittest.main()
