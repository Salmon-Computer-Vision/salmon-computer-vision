class BgObject:
    def __init__(self, id, xywh):
        super().__init__()
        self.id = id
        self.xywh = xywh

    def get_id(self):
        return self.id

    def get_xywh(self):
        return self.xywh


class BgFrame:
    def __init__(self):
        super().__init__()
        self.objects = dict()

    def get_all_objects(self):
        return list(self.objects.values())

    def create_and_add_object(self, id, xywh):
        self.objects[id] = BgObject(id, xywh)

    def get_object(self, id) -> BgObject:
        return self.objects[id]

    def remove_object(self, id):
        del self.objects[id]
