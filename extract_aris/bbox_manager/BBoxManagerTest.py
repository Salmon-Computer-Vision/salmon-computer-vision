import unittest
import BBoxManager as bbm
import json
import os


class BBoxManagerTest(unittest.TestCase):

    def __init__(self, methodName):
        super().__init__(methodName)

    def __get_built_bbox_manager(self):
        bbox_manager = bbm.BBoxManager()
        bbox_manager = self.__set_frames_data(bbox_manager)
        return bbox_manager

    def __set_frames_data(self, bbox_manager):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        filename = current_dir + "/tests/test_json/json.txt"
        with open(filename) as f:
            data = json.load(f)
        self.base_path = os.path.dirname(filename)
        self.data = data
        bbox_manager.set_frames_data(data, self.base_path)
        return bbox_manager

    def test_set_frames_data(self):
        bbox_manager = self.__get_built_bbox_manager()
        self.assertEqual(
            bbox_manager._BBoxManager__state["base_path"], self.base_path)
        self.assertEqual(
            bbox_manager._BBoxManager__state["frames_data"], self.data)


if __name__ == '__main__':
    unittest.main()
