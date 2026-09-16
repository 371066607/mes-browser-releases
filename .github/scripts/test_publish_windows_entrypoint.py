import os
from pathlib import Path
import subprocess
import sys
import unittest


class PublishEntrypointTests(unittest.TestCase):
    def test_non_main_ref_is_rejected_before_artifact_or_github_access(self):
        environment = dict(os.environ, GITHUB_REPOSITORY='fixture/releases', GITHUB_REF='refs/heads/feature')
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('publish-windows.py'))],
                                env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Publication requires the trusted release repository main branch', result.stderr)


if __name__ == '__main__':
    unittest.main()
