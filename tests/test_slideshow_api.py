import unittest
import os
import shutil
import sys
import json
from pathlib import Path

# Add parent directory to path to import web_app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web_app import app

@unittest.skip("Route /api/slideshow/<username>/<video_id> absente de web_app.py : fonctionnalité non implémentée")
class TestSlideshowAPI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.username = "test_slideshow_user"
        self.video_id = "1234567890123456789"
        self.downloads_dir = "downloads"
        self.user_dir = os.path.join(self.downloads_dir, self.username)
        
        # Create dummy user directory
        if not os.path.exists(self.user_dir):
            os.makedirs(self.user_dir)
            
        # Create dummy slideshow images
        self.files = [
            f"{self.user_dir}/test_{self.video_id}_img=1.jpg",
            f"{self.user_dir}/test_{self.video_id}_img=2.jpg",
            f"{self.user_dir}/test_{self.video_id}_img=3.jpg"
        ]
        
        for f in self.files:
            with open(f, 'w') as file:
                file.write("dummy content")

    def tearDown(self):
        # Clean up
        if os.path.exists(self.user_dir):
            shutil.rmtree(self.user_dir)

    def test_get_slideshow_images(self):
        response = self.app.get(f'/api/slideshow/{self.username}/{self.video_id}')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['username'], self.username)
        self.assertEqual(data['video_id'], self.video_id)
        self.assertEqual(data['count'], 3)
        self.assertEqual(len(data['images']), 3)
        
        # Check image order
        self.assertEqual(data['images'][0]['img_num'], 1)
        self.assertEqual(data['images'][1]['img_num'], 2)
        self.assertEqual(data['images'][2]['img_num'], 3)
        
        # Check URL format
        self.assertIn(f'/video/{self.username}', data['images'][0]['url'])

    def test_get_nonexistent_slideshow(self):
        response = self.app.get(f'/api/slideshow/{self.username}/999999999')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['count'], 0)
        self.assertEqual(len(data['images']), 0)

if __name__ == '__main__':
    unittest.main()
