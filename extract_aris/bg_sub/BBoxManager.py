import threading
import tkinter as tk
from tkinter import filedialog
import time
from PIL import ImageTk, Image
import json
import os
import cv2
from numpy import asarray
from enum import Enum


class BBoxManager:
    def __init__(self):
        super().__init__()
        self.__state = {
            "base_path": "",
            "frames_data": {},
            "current_index": 0,
            "frame": None,
            "bbox_frame": None,
            "show_bbox": True,
        }
        self.__observers = set()

    def set_frames_data(self, frames_data, base_path):
        self.__state["frames_data"] = frames_data
        self.__set_base_path(base_path)
        self.__process_frame()
        self.__notify_observers()

    def __set_base_path(self, path):
        self.__state["base_path"] = path

    def next_frame(self):
        self.__state["current_index"] += 1
        if self.__state["current_index"] >= len(self.__state["frames_data"]["metadata"]):
            self.__state["current_index"] = 0
        self.__process_frame()
        self.__notify_observers()

    def prev_frame(self):
        self.__state["current_index"] -= 1
        if self.__state["current_index"] < 0:
            self.__state["current_index"] = len(
                self.__state["frames_data"]["metadata"]) - 1
        self.__process_frame()
        self.__notify_observers()

    def __process_frame(self):
        self.__open_img()
        self.__draw_bbox_for_interested_object()
        self.__draw_bbox_for_noise()

    def __open_img(self):
        data = self.__get_current_frame_data()
        path = self.__state["base_path"] + "/" + data["name"]
        img = Image.open(path)
        self.__state["frame"] = img
        self.__state["bbox_frame"] = img

    def __draw_bbox_for_interested_object(self):
        green = (0, 255, 0)
        data = self.__get_current_frame_data()
        img = self.__state["bbox_frame"]
        img_array = asarray(img)
        self.__draw_bounding_boxes(
            img_array.copy(), data["bounding_boxes"]["interested_objects"], color=green)

    def __draw_bbox_for_noise(self):
        red = (255, 0, 0)
        data = self.__get_current_frame_data()
        img = self.__state["bbox_frame"]
        img_array = asarray(img)
        self.__draw_bounding_boxes(
            img_array.copy(),
            data["bounding_boxes"]["noises"],
            color=red,
            label_start=self.__get_num_interested_objects()
        )

    def __get_num_interested_objects(self):
        data = self.__get_current_frame_data()
        return len(data["bounding_boxes"]["interested_objects"])

    def __draw_bounding_boxes(self, frame, bounding_boxes, color=(0, 255, 0), thickness=1, label_start=0):
        for i in range(len(bounding_boxes)):
            bbox = bounding_boxes[i]
            x = bbox['x']
            y = bbox['y']
            width = bbox['w']
            height = bbox['h']
            frame = cv2.rectangle(
                frame, (x, y), (x + width, y + height), color, thickness)
            frame = self.__draw_label(
                frame, str(label_start + i), bbox, color=color)
        self.__state["bbox_frame"] = Image.fromarray(frame)

    def __draw_label(self, frame, label, bbox, color=(0, 255, 0), thickness=1):
        frame = cv2.putText(
            frame, label, (bbox['x'], bbox['y'] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, thickness)
        return frame

    def toggle_bbox(self):
        self.__state["show_bbox"] = not self.__state["show_bbox"]
        self.__notify_observers()

    def remove_bounding_boxes(self, label):
        bounding_boxes = self.__get_bounding_boxes()
        bbox = self.__get_bbox_by_label(label)
        if label < len(bounding_boxes["interested_objects"]):
            bounding_boxes["interested_objects"].remove(bbox)
        else:
            bounding_boxes["noises"].remove(bbox)
        self.__process_frame()
        self.__notify_observers()

    def mark_bounding_boxes(self, label, type):
        bbox = self.__get_bbox_by_label(label)
        self.remove_bounding_boxes(label)
        frame_data = self.__get_current_frame_data()
        if type == BBoxType.NOISE:
            frame_data["bounding_boxes"]["noises"].append(bbox)
        elif type == BBoxType.INTERESTED_OBJECT:
            frame_data["bounding_boxes"]["interested_objects"].append(bbox)
        else:
            raise BoundingBoxTypeError()
        self.__process_frame()
        self.__notify_observers()

    def __get_bbox_by_label(self, label):
        bounding_boxes = self.__get_bounding_boxes()
        if label < len(bounding_boxes["interested_objects"]):
            return bounding_boxes["interested_objects"][label]
        else:
            index = label - len(bounding_boxes["interested_objects"])
            return bounding_boxes["noises"][index]

    def __get_bounding_boxes(self):
        current_index = self.__state["current_index"]
        bounding_boxes = self.__state["frames_data"]["metadata"][current_index]["bounding_boxes"]
        return bounding_boxes

    def __get_current_frame_data(self):
        current_index = self.__state["current_index"]
        return self.__state["frames_data"]["metadata"][current_index]

    def export_json(self):
        frames_data = self.__state["frames_data"]
        base_path = self.__state["base_path"]
        with open(base_path + "/BBoxManagerJson.txt", "w") as outfile:
            json.dump(frames_data, outfile)

    def attach_observer(self, observer):
        self.__observers.add(observer)

    def detach_observer(self, observer):
        self.__observers.discard(observer)

    def __notify_observers(self):
        for observer in self.__observers:
            observer.notify(self.__state)


class BBoxType(Enum):
    NOISE = 0
    INTERESTED_OBJECT = 1


class LeftFrame:
    def __init__(self):
        super().__init__()
        self.frame_scale = 0.6
        self.frame_height = int(1275 * self.frame_scale)
        self.frame_width = int(619 * self.frame_scale)
        self.root = tk.Frame()
        self.image_frame = tk.Frame(
            master=self.root)
        self.create_canvas()

    def pack(self, side=tk.LEFT):
        self.root.pack(side=side)
        self.image_frame.pack(fill=tk.BOTH, expand=True)

    def add_image(self, img):
        resize_img = img.resize((self.frame_width, self.frame_height))
        # Important: Keep PhotoImage as class instance to avoid being recycled by GC
        self.photo_image = ImageTk.PhotoImage(resize_img)
        self.canvas.create_image(
            20, 20, anchor=tk.NW, image=self.photo_image)

    def create_canvas(self):
        self.canvas = tk.Canvas(
            self.root, width=self.frame_width, height=self.frame_height)
        self.canvas.pack()


class RightFrame:
    def __init__(self, bbox_manager):
        super().__init__()
        self.button_width = 20
        self.button_height = 2
        self.__bbox_manager = bbox_manager
        self.root = tk.Frame(padx=10)
        self.__create_mark_bbox_frame()
        self.__create_navigation_frame()
        self.__create_json_load_export_frame()

    def pack(self, side=tk.RIGHT):
        self.root.pack(side=side)

    def __create_mark_bbox_frame(self):
        control_frame = tk.LabelFrame(
            master=self.root, text="Mark Bounding Boxes", padx=10, pady=10)
        self.__create_input_box_for_removing_label(master=control_frame)
        buttons_frame = tk.Frame(master=control_frame, pady=10)
        mark_interested_object_button = tk.Button(
            master=buttons_frame,
            text="Mark Interested Object",
            command=get_thread_task(self.__mark_interested_object_action),
            width=self.button_width,
            height=self.button_height,
            bg="#8feb34"
        )
        mark_noise_button = tk.Button(
            master=buttons_frame,
            text="Mark Noise",
            command=get_thread_task(self.__mark_noise_action),
            width=self.button_width,
            height=self.button_height,
            bg="#fa93a1"
        )
        remove_button = tk.Button(
            master=buttons_frame,
            text="Remove",
            command=get_thread_task(self.__remove_label_action),
            width=self.button_width,
            height=self.button_height
        )
        buttons_frame.pack()
        mark_interested_object_button.pack()
        mark_noise_button.pack()
        remove_button.pack()
        control_frame.pack()

    def __create_input_box_for_removing_label(self, master):
        label = tk.Label(master=master,
                         text="Enter label number to operate:")
        self.__remove_label_entry = tk.Entry(master=master)
        label.pack()
        self.__remove_label_entry.pack()

    def __create_navigation_frame(self):
        navigation_frame = tk.LabelFrame(
            master=self.root, text="Navigation", padx=10, pady=10)
        buttons_frame = tk.Frame(master=navigation_frame)
        prev_button = tk.Button(
            master=buttons_frame,
            text="Previous",
            command=get_thread_task(self.__bbox_manager.prev_frame),
            width=self.button_width,
            height=self.button_height
        )
        next_button = tk.Button(
            master=buttons_frame,
            text="Next",
            command=get_thread_task(self.__bbox_manager.next_frame),
            width=self.button_width,
            height=self.button_height
        )
        toggle_button = tk.Button(
            master=buttons_frame,
            text="Toggle Bounding Boxes",
            command=get_thread_task(self.__bbox_manager.toggle_bbox),
            width=self.button_width,
            height=self.button_height
        )
        prev_button.pack()
        next_button.pack()
        toggle_button.pack()
        buttons_frame.pack()
        navigation_frame.pack()

    def __create_json_load_export_frame(self):
        json_load_export_frame = tk.LabelFrame(
            master=self.root, text="JSON Load/Export", padx=10, pady=10)
        self.__create_load_json_button(json_load_export_frame)
        self.__create_export_json_button(json_load_export_frame)
        json_load_export_frame.pack()

    def __create_load_json_button(self, master):
        button_frame = tk.Frame(master=master)
        load_button = tk.Button(
            master=button_frame,
            text="Load JSON File",
            command=get_thread_task(self.__load_json_file_action),
            width=self.button_width,
            height=self.button_height,
            bg="#feffb3"
        )
        load_button.pack(side=tk.LEFT)
        button_frame.pack()

    def __create_export_json_button(self, master):
        button_frame = tk.Frame(master=master)
        load_button = tk.Button(
            master=button_frame,
            text="Export JSON File",
            command=get_thread_task(self.__export_json_file_action),
            width=self.button_width,
            height=self.button_height
        )
        load_button.pack(side=tk.LEFT)
        button_frame.pack()

    def __load_json_file_action(self):
        filename = filedialog.askopenfilename()
        with open(filename) as f:
            data = json.load(f)
        base_path = os.path.dirname(filename)
        self.__bbox_manager.set_frames_data(data, base_path)

    def __export_json_file_action(self):
        self.__bbox_manager.export_json()

    def __remove_label_action(self):
        label = self.__remove_label_entry.get()
        self.__bbox_manager.remove_bounding_boxes(int(label))

    def __mark_interested_object_action(self):
        label = self.__remove_label_entry.get()
        self.__bbox_manager.mark_bounding_boxes(
            int(label), type=BBoxType.INTERESTED_OBJECT)

    def __mark_noise_action(self):
        label = self.__remove_label_entry.get()
        self.__bbox_manager.mark_bounding_boxes(
            int(label), type=BBoxType.NOISE)


class GUI:
    def __init__(self):
        super().__init__()
        self.__bbox_manager = BBoxManager()
        self.__create_ui()
        self.__pack_ui()
        self.__register_observers()

    def start(self):
        self.tk.mainloop()

    def __create_ui(self):
        self.tk = tk.Tk()
        self.tk.title("BBox Manager")
        self.tk.iconbitmap(self.__get_window_icon_path())
        self.left_frame = LeftFrame()
        self.right_frame = RightFrame(self.__bbox_manager)

    def __get_window_icon_path(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        return current_dir + "/" + "BBoxManagerIcon.ico"

    def __pack_ui(self):
        self.left_frame.pack(side=tk.LEFT)
        self.right_frame.pack(side=tk.LEFT)

    def __register_observers(self):
        left_frame_observer = Observer(self.__update_left_frame)
        self.__bbox_manager.attach_observer(left_frame_observer)

    def __update_left_frame(self, state):
        if state["show_bbox"]:
            self.left_frame.add_image(state["bbox_frame"])
        else:
            self.left_frame.add_image(state["frame"])


class Observer:
    def __init__(self, action):
        super().__init__()
        self.action = action

    def notify(self, state):
        self.action(state)


class Error(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class BoundingBoxTypeError(Error):
    def __init__(self):
        super().__init__("Please specify a valid bounding box type.")


def get_thread_task(task):
    return lambda: start_thread_task(task)


def start_thread_task(task):
    thread = threading.Thread(target=task)
    thread.start()
