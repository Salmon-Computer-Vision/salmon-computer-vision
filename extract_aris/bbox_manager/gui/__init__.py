import threading
import tkinter as tk
import time
from PIL import ImageTk, Image


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
        # Test
        self.add_image()

    def pack(self, side=tk.LEFT):
        self.root.pack(side=side)
        self.image_frame.pack(fill=tk.BOTH, expand=True)

    def add_image(self):
        # TODO: Remove the placeholder
        img = Image.open(
            "C:/Users/mrycc/Desktop/salmon project program/salmon-computer-vision/extract_aris/bbox_manager/gui/bbox_img_placeholder.png")

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
    def __init__(self):
        super().__init__()
        self.root = tk.Frame()
        self.__create_input_box_for_removing_label()
        self.__create_buttons()
        self.__create_console_text()

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
        prev_button = tk.Button(master=button_frame, text="Previous")
        next_button = tk.Button(master=button_frame, text="Next")
        remove_button.pack(side=tk.LEFT)
        prev_button.pack(side=tk.LEFT)
        next_button.pack(side=tk.LEFT)
        button_frame.pack()

    def __create_console_text(self):
        self.console_text = tk.Text(
            master=self.root, height=5, width=30)
        self.console_text.pack()


class GUI:
    def __init__(self):
        super().__init__()
        self.__create_ui()
        self.__pack_ui()

    def start(self):
        self.tk.mainloop()

    def __create_ui(self):
        self.tk = tk.Tk()
        self.left_frame = LeftFrame()
        self.right_frame = RightFrame()

    def __pack_ui(self):
        self.left_frame.pack(side=tk.LEFT)
        self.right_frame.pack(side=tk.LEFT)

    def __get_thread_task(self, task):
        return lambda: self.__start_thread_task(task)

    def __start_thread_task(self, task):
        thread = threading.Thread(target=task)
        thread.start()
