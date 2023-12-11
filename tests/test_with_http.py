"""
Test the full HTTP to SciToken serialize and deserialize
"""

import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

# Allow unittests to be run from within the project base.
if os.path.exists("src"):
    sys.path.append("src")
if os.path.exists("../src"):
    sys.path.append("../src")

import scitokens
import scitokens.scitokens

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from create_webserver import start_server

TESTS_DIR = Path(__file__).parent


class TestDeserialization(unittest.TestCase):
    """
    Test the deserialization of a SciToken
    """

    def setUp(self):
        # Force the keycache to create a cache in a new directory
        self.tmp_dir = tempfile.mkdtemp()
        self.old_xdg = os.environ.get('XDG_CACHE_HOME', None)
        os.environ['XDG_CACHE_HOME'] = self.tmp_dir
             
        with open(TESTS_DIR / 'simple_private_key.pem', 'rb') as key_file:
            self.private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
                )
        self.test_id = "stuffblah"
        self.public_numbers = self.private_key.public_key().public_numbers()

        with open(TESTS_DIR / 'simple_ec_private_key.pem', 'rb') as key_file:
            self.ec_private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
                )
        self.ec_test_id = "ec_test_id"

        self.ec_public_numbers = self.ec_private_key.public_key().public_numbers()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)
        if self.old_xdg:
            os.environ['XDG_CACHE_HOME'] = self.old_xdg
        # Clean up, delete everything

    def test_deserialization(self):
        """
        Perform the deserialization test
        """

        server_address = start_server(self.public_numbers.n, self.public_numbers.e, self.test_id)
        print(server_address)
        issuer = "http://localhost:{}/".format(server_address[1])
        token = scitokens.SciToken(key=self.private_key, key_id=self.test_id)
        token.update_claims({"test": "true"})
        serialized_token = token.serialize(issuer=issuer)

        self.assertEqual(len(serialized_token.decode('utf8').split(".")), 3)

        scitoken = scitokens.SciToken.deserialize(serialized_token, insecure=True)

        self.assertIsInstance(scitoken, scitokens.SciToken)

        token = scitokens.SciToken(key=self.private_key, key_id="doesnotexist")
        serialized_token = token.serialize(issuer=issuer)
        with self.assertRaises(scitokens.utils.errors.MissingKeyException):
            scitoken = scitokens.SciToken.deserialize(serialized_token, insecure=True)


    def test_ec_deserialization(self):
        """
        Perform the EC deserialization test
        """

        server_address = start_server(self.public_numbers.n, self.public_numbers.e,
                                      self.test_id,
                                      test_ec={'x': self.ec_public_numbers.x,
                                               'y': self.ec_public_numbers.y,
                                               'kid': self.ec_test_id})
        print(server_address)
        issuer = "http://localhost:{}/".format(server_address[1])
        token = scitokens.SciToken(key=self.ec_private_key, key_id=self.ec_test_id,
                                   algorithm="ES256")
        token.update_claims({"test": "true"})
        serialized_token = token.serialize(issuer=issuer)

        self.assertEqual(len(serialized_token.decode('utf8').split(".")), 3)

        scitoken = scitokens.SciToken.deserialize(serialized_token, insecure=True)

        self.assertIsInstance(scitoken, scitokens.SciToken)

        token = scitokens.SciToken(key=self.private_key, key_id="doesnotexist")
        serialized_token = token.serialize(issuer=issuer)
        with self.assertRaises(scitokens.utils.errors.MissingKeyException):
            scitoken = scitokens.SciToken.deserialize(serialized_token, insecure=True)



if __name__ == '__main__':
    unittest.main()
