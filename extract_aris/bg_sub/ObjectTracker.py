import math


class ObjectTracker:
    def __init__(self, stats):
        super().__init__()

    def __is_same(self, xywh1, xywh2, radius):
        centroid1 = self.__calculate_centroid(xywh1)
        centroid2 = self.__calculate_centroid(xywh2)
        diff_x = centroid1[0] - centroid2[0]
        diff_y = centroid1[1] - centroid2[1]
        diff = (diff_x, diff_y)
        distance = math.sqrt(diff[0] ** 2 + diff[1] ** 2)
        return distance <= radius

    def __calculate_centroid(self, xywh):
        (x, y, w, h) = self.__unpack_xywh(xywh)
        centroid_x = w / 2 + x
        centroid_y = h / 2 + y
        return (centroid_x, centroid_y)

    def __unpack_xywh(self, xywh):
        x = xywh["x"]
        y = xywh["y"]
        w = xywh["w"]
        h = xywh["h"]
        return (x, y, w, h)
