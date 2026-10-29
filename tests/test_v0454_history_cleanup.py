"""A failed history initialization must release Windows' SQLite file handle."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kain_maple_translator.chat_history import ChatHistoryStore


class HistoryConnectionCleanupTests(unittest.TestCase):
    def test_corrupt_database_closes_even_while_failed_connection_is_retained(self):
        connect = sqlite3.connect
        retained = []

        def keep_connection(*args, **kwargs):
            connection = connect(*args, **kwargs)
            retained.append(connection)
            return connection

        with tempfile.TemporaryDirectory(prefix='history-open-failure-') as td:
            path = Path(td) / 'history.sqlite3'
            original = b'preserve-corrupt-history'
            path.write_bytes(original)
            try:
                with patch('kain_maple_translator.chat_history.sqlite3.connect', keep_connection):
                    with self.assertRaises(sqlite3.DatabaseError):
                        ChatHistoryStore(path)
                self.assertEqual(len(retained), 1)
                # Keep a strong reference: garbage collection cannot release
                # the handle on the implementation's behalf.
                with self.assertRaises(sqlite3.ProgrammingError):
                    retained[0].execute('SELECT 1')
                self.assertEqual(path.read_bytes(), original)
                # A Windows connection without explicit close fails here.
                moved = path.with_name('preserved-history.sqlite3')
                path.rename(moved)
                self.assertEqual(moved.read_bytes(), original)
            finally:
                for connection in retained:
                    connection.close()

    def test_each_setup_failure_closes_and_preserves_the_original_exception(self):
        for step in ('journal', 'busy_timeout', 'schema', 'index', 'commit'):
            with self.subTest(step=step), tempfile.TemporaryDirectory() as td:
                connection = Mock()
                failure = sqlite3.OperationalError('simulated ' + step + ' failure')
                execute_steps = ['journal', 'busy_timeout', 'schema', 'index']
                if step == 'commit':
                    connection.commit.side_effect = failure
                else:
                    connection.execute.side_effect = [
                        failure if candidate == step else None
                        for candidate in execute_steps
                    ]
                with patch('kain_maple_translator.chat_history.sqlite3.connect', return_value=connection):
                    with self.assertRaises(sqlite3.OperationalError) as raised:
                        ChatHistoryStore(Path(td) / 'history.sqlite3')
                self.assertIs(raised.exception, failure)
                connection.close.assert_called_once_with()

    def test_successful_store_stays_open_until_explicit_close(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'history.sqlite3'
            store = ChatHistoryStore(path)
            try:
                self.assertTrue(store.append({'id': 'retained-message', 'nickname': 'User',
                                              'original': 'hello', 'translated': '안녕하세요'}))
                self.assertEqual(store.count(), 1)
            finally:
                store.close()
            restored = ChatHistoryStore(path)
            try:
                self.assertEqual(restored.count(), 1)
            finally:
                restored.close()


if __name__ == '__main__':
    unittest.main()
