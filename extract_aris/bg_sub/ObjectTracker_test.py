import unittest
from .ObjectTracker import *
from .BgObjLabel import *
from .JSONFormatter import *
from .BgFrame import *


class TrackerTest(unittest.TestCase):

    def __init__(self, methodName):
        super().__init__(methodName)
        self.json_formatter = JSONFormatter()

    def __build_tracker(self):
        radius = 5
        return ObjectTracker(radius, self.__build_BgFrame(), self.json_formatter)

    def __build_BgFrame(self):
        return BgFrame()

    def test_calculate_centroid(self):
        xywh = {"x": 1230, "y": 448, "w": 174, "h": 53}
        tracker = self.__build_tracker()
        centroid = tracker._ObjectTracker__calculate_centroid(xywh)
        self.assertEqual(centroid, (87 + 1230, 26.5 + 448))

    def test_is_same_object_within_radius(self):
        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r / 2, "y": 448 + r / 2, "w": 174, "h": 53}
        tracker = self.__build_tracker()
        self.assertTrue(tracker._ObjectTracker__is_same(xywh1, xywh2, r))

    def test_is_same_object_outside_radius(self):
        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r / 2 + 2, "y": 448 + r / 2 + 2, "w": 174, "h": 53}
        tracker = self.__build_tracker()
        self.assertFalse(tracker._ObjectTracker__is_same(xywh1, xywh2, r))

    def test_init_id(self):
        tracker = self.__build_tracker()
        bgFrame = BgFrame()
        xywh = {"x": 1230, "y": 448, "w": 174, "h": 53}
        for i in range(10):
            bgFrame.create_and_add_object(i + 10, xywh)
        new_bgFrame = tracker._ObjectTracker__init_id(bgFrame)

        all_objects = new_bgFrame.get_all_objects()
        for i in range(len(all_objects)):
            bgObject = all_objects[i]
            self.assertEqual(bgObject.get_id(), i)
            self.assertEqual(bgObject.get_xywh(), xywh)

    def test_track_and_return_updated_frame_same_objects(self):
        tracker = self.__build_tracker()
        (base_frame, updating_frame) = self.__build_frames_with_same_objects()

        updated_frame = tracker._ObjectTracker__track_and_return_updated_frame(
            base_frame, updating_frame)

        self.assertEqual(updated_frame.get_object(1).get_id(),
                         base_frame.get_object(1).get_id())
        self.assertEqual(updated_frame.get_object(1).get_xywh(),
                         updating_frame.get_object(2).get_xywh())

    def __build_frames_with_same_objects(self):
        frame1 = self.__build_BgFrame()
        frame2 = self.__build_BgFrame()

        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r / 2, "y": 448 + r / 2, "w": 174, "h": 53}

        frame1.create_and_add_object(1, xywh1)
        frame2.create_and_add_object(2, xywh2)

        return (frame1, frame2)

    def test_track_and_return_updated_frame_different_objects(self):
        tracker = self.__build_tracker()
        (base_frame, updating_frame) = self.__build_frames_with_different_objects()

        updated_frame = tracker._ObjectTracker__track_and_return_updated_frame(
            base_frame, updating_frame)

        new_assigned_id = 0
        self.assertEqual(updated_frame.get_object(0).get_id(), new_assigned_id)
        self.assertEqual(updated_frame.get_object(0).get_xywh(),
                         updating_frame.get_object(2).get_xywh())

    def __build_frames_with_different_objects(self):
        frame1 = self.__build_BgFrame()
        frame2 = self.__build_BgFrame()

        r = 5
        xywh1 = {"x": 1230, "y": 448, "w": 174, "h": 53}
        xywh2 = {"x": 1230 + r, "y": 448 + r, "w": 174, "h": 53}

        frame1.create_and_add_object(1, xywh1)
        frame2.create_and_add_object(2, xywh2)

        return (frame1, frame2)


if __name__ == '__main__':
    unittest.main()
