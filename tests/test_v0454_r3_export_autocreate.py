"""The requested export name must be created without recording user chat text."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kain_maple_translator.stage_trace import StageTraceWriter, profile_path
from scripts.summarize_ocr_trace import summarize


class AutoExportTests(unittest.TestCase):
    def test_windows_localappdata_uses_requested_export_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'LOCALAPPDATA':folder}):
                path=profile_path()
                self.assertEqual(path.name, 'OCR-STAGE-TRACE-EXPORT.jsonl')
                self.assertEqual(path.parent.name, 'diagnostics')
                writer=StageTraceWriter()
                self.assertTrue(path.exists(), 'default trace must exist immediately after writer starts')
                self.assertIsNone(writer.open_error)
                writer.record({'schema':2,'event':'session_start','utc_unix_ms':1000})
                writer.record({'schema':1,'stage_total_ms':12.4,'pre_ms':1.2,'ocr_model_path_ms':9.2,
                               'post_ms':2,'queue_wait_ms':3,'new_rows':1,'input_width_px':800,'input_height_px':160})
                writer.close()
                data=[json.loads(row) for row in path.read_text('utf-8').splitlines()]
                self.assertEqual(len(data),2)
                self.assertEqual(data[1]['stage_total_ms'],12.4)
                self.assertNotIn('text',data[1])
                report=summarize(path)
                self.assertIn('Frames: 1',report)
                self.assertIn('Top 10 slowest OCR frames',report)
                self.assertIn('stage_total_ms=12.4',report)

    def test_empty_session_does_not_fabricate_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trace.jsonl'
            writer=StageTraceWriter(path)
            writer.record({'schema':2,'event':'session_start'})
            writer.close()
            self.assertIn('Frames: 0 (NO MEASUREMENTS)',summarize(path))

    def test_new_session_summary_excludes_prior_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trace.jsonl'
            with path.open('w',encoding='utf-8') as f:
                for row in [
                    {'schema':2,'event':'session_start'},
                    {'schema':1,'stage_total_ms':9999},
                    {'schema':2,'event':'session_start'},
                    {'schema':1,'stage_total_ms':15.5,'queue_wait_ms':2.5},
                ]: f.write(json.dumps(row)+'\n')
            report=summarize(path)
            self.assertIn('Frames: 1',report)
            self.assertNotIn('9999',report)
            self.assertIn('15.5',report)


if __name__=='__main__':
    unittest.main()
