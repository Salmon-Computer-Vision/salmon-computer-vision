import threading
import tkinter as tk
from tkinter import filedialog
import time
from PIL import ImageTk, Image
import json
import os
import cv2
from numpy import asarray


class BBoxManager:
    def __init__(self):
        super().__init__()
        self.__state = {
            "base_path": "",
            "frames_data": {},
            "current_index": 0,
            "frame": None,
            "bbox_frame": None
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
        base_path = self.__state["base_path"]
        current_index = self.__state["current_index"]
        data = self.__state["frames_data"]["metadata"][current_index]
        path = self.__state["base_path"] + "/" + data["name"]
        img = Image.open(path)
        img_array = asarray(img)
        self.__state["frame"] = img
        self.__draw_bounding_boxes(img_array.copy(), data["bounding_boxes"])

    def __draw_bounding_boxes(self, frame, bounding_boxes, color=(0, 255, 0), thickness=1):
        for i in range(len(bounding_boxes)):
            bbox = bounding_boxes[i]
            x = bbox['x']
            y = bbox['y']
            width = bbox['w']
            height = bbox['h']
            frame = cv2.rectangle(
                frame, (x, y), (x + width, y + height), color, thickness)
            frame = self.__draw_label(frame, str(i), bbox)
        self.__state["bbox_frame"] = Image.fromarray(frame)

    def __draw_label(self, frame, label, bbox, color=(0, 255, 0), thickness=1):
        frame = cv2.putText(
            frame, label, (bbox['x'], bbox['y'] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, thickness)
        return frame

    def attach_observer(self, observer):
        self.__observers.add(observer)

    def detach_observer(self, observer):
        self.__observers.discard(observer)

    def __notify_observers(self):
        for observer in self.__observers:
            observer.notify(self.__state)


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
        self.__bbox_manager = bbox_manager
        self.root = tk.Frame()
        self.__create_input_box_for_removing_label()
        self.__create_buttons()
        self.__create_console_text()
        self.__create_load_json_button()

    def pack(self, side=tk.RIGHT):
        self.root.pack(side=side)

    def __create_input_box_for_removing_label(self):
        label = tk.Label(master=self.root,
                         text="Enter label number to remove:")
        label_input_box = tk.Entry(master=self.root)
        label.pack()
        label_input_box.pack()

    def __create_buttons(self):
        button_frame = tk.Frame(master=self.root)
        remove_button = tk.Button(master=button_frame, text="Remove")
        prev_button = tk.Button(
            master=button_frame,
            text="Previous",
            command=get_thread_task(self.__bbox_manager.prev_frame)
        )
        next_button = tk.Button(
            master=button_frame,
            text="Next",
            command=get_thread_task(self.__bbox_manager.next_frame)
        )
        remove_button.pack(side=tk.LEFT)
        prev_button.pack(side=tk.LEFT)
        next_button.pack(side=tk.LEFT)
        button_frame.pack()

    def __create_console_text(self):
        self.console_text = tk.Text(
            master=self.root, height=5, width=30)
        self.console_text.pack()

    def __create_load_json_button(self):
        button_frame = tk.Frame(master=self.root)
        load_button = tk.Button(
            master=button_frame, text="Load JSON File", command=get_thread_task(self.__load_json_file_action))
        load_button.pack(side=tk.LEFT)
        button_frame.pack()

    def __load_json_file_action(self):
        filename = filedialog.askopenfilename()
        with open(filename) as f:
            data = json.load(f)
        base_path = os.path.dirname(filename)
        self.__bbox_manager.set_frames_data(data, base_path)


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
        self.left_frame = LeftFrame()
        self.right_frame = RightFrame(self.__bbox_manager)

    def __pack_ui(self):
        self.left_frame.pack(side=tk.LEFT)
        self.right_frame.pack(side=tk.LEFT)

    def __register_observers(self):
        left_frame_observer = Observer(self.__update_left_frame)
        self.__bbox_manager.attach_observer(left_frame_observer)

    def __update_left_frame(self, state):
        self.left_frame.add_image(state["bbox_frame"])


class Observer:
    def __init__(self, action):
        super().__init__()
        self.action = action

    def notify(self, state):
        self.action(state)


def get_thread_task(task):
    return lambda: start_thread_task(task)


def start_thread_task(task):
    thread = threading.Thread(target=task)
    thread.start()
