import hashlib
import hmac
import tempfile
import unittest
from pathlib import Path

from wechat_emoji_cli.engines.key_status import cached_key_valid


class KeyStatusTests(unittest.TestCase):
    def test_raw_cached_key_matches_database_without_exposing_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = bytes.fromhex('ab' * 32)
            page = bytearray(b'\x13' * 4096)
            salt = bytes(value ^ 0x3A for value in page[:16])
            mac_key = hashlib.pbkdf2_hmac('sha512', key, salt, 2, 32)
            page[4032:] = hmac.new(mac_key, page[16:4032] + b'\x01\0\0\0', 'sha512').digest()
            database = root / 'emoticon.db'
            database.write_bytes(page)
            (root / 'emoticon_dbkey_test.txt').write_text(key.hex())
            self.assertIs(cached_key_valid(database, 'test', root), True)
            (root / 'emoticon_dbkey_test.txt').write_text('cd' * 32)
            self.assertIs(cached_key_valid(database, 'test', root), False)

    def test_missing_or_truncated_database_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(cached_key_valid(root / 'missing', 'test', root))
            (root / 'short.db').write_bytes(b'123')
            self.assertFalse(cached_key_valid(root / 'short.db', 'test', root))
