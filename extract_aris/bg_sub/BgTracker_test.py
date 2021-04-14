import unittest
from ObjectTracker import *
from BgObjLabel import *


class TrackerTest(unittest.TestCase):

    def __init__(self, methodName):
        super().__init__(methodName)

    def __build_stats(self):
        return []

    def test_calculate_centroid(self):
        xywh = {"x": 1230, "y": 448, "w": 174, "h": 53}
        tracker = ObjectTracker(self.__build_stats())
        centroid = tracker._ObjectTracker__calculate_centroid(xywh)
        self.assertEqual(centroid, (87+1230, 26.5+448))

    def test_is_same_object_within_radius(self):
        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r/2, "y": 448 + r/2, "w": 174, "h": 53}
        tracker = ObjectTracker(self.__build_stats())
        self.assertTrue(tracker._ObjectTracker__is_same(xywh1, xywh2, r))

    def test_is_same_object_outside_radius(self):
        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r/2 + 2, "y": 448 + r/2 + 2, "w": 174, "h": 53}
        tracker = ObjectTracker(self.__build_stats())
        self.assertFalse(tracker._ObjectTracker__is_same(xywh1, xywh2, r))


if __name__ == '__main__':
    unittest.main()
