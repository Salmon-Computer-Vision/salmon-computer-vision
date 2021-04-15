import unittest
from ObjectTracker import *
from BgObjLabel import *
from JSONFormatter import *
from BgFrame import *


class TrackerTest(unittest.TestCase):

    def __init__(self, methodName):
        super().__init__(methodName)
        self.json_formatter = JSONFormatter()

    def __build_tracker(self):
        return ObjectTracker(self.__build_BgFrame(), self.json_formatter)

    def __build_BgFrame(self):
        return BgFrame()

    def test_calculate_centroid(self):
        xywh = {"x": 1230, "y": 448, "w": 174, "h": 53}
        tracker = self.__build_tracker()
        centroid = tracker._ObjectTracker__calculate_centroid(xywh)
        self.assertEqual(centroid, (87+1230, 26.5+448))

    def test_is_same_object_within_radius(self):
        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r/2, "y": 448 + r/2, "w": 174, "h": 53}
        tracker = self.__build_tracker()
        self.assertTrue(tracker._ObjectTracker__is_same(xywh1, xywh2, r))

    def test_is_same_object_outside_radius(self):
        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r/2 + 2, "y": 448 + r/2 + 2, "w": 174, "h": 53}
        tracker = self.__build_tracker()
        self.assertFalse(tracker._ObjectTracker__is_same(xywh1, xywh2, r))

    def test_init_id(self):
        tracker = self.__build_tracker()
        bgFrame = BgFrame()
        xywh = {"x": 1230, "y": 448, "w": 174, "h": 53}
        for i in range(10):
            bgFrame.create_and_add_object(i+10, xywh)
        new_bgFrame = tracker._ObjectTracker__init_id(bgFrame)

        all_objects = new_bgFrame.get_all_objects()
        for i in range(len(all_objects)):
            bgObject = all_objects[i]
            self.assertEqual(bgObject.get_id(), i)
            self.assertEqual(bgObject.get_xywh(), xywh)


if __name__ == '__main__':
    unittest.main()
