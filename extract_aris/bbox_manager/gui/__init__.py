import threading
import tkinter as tk
import time


class GUI:
    def __init__(self):
        super().__init__()
        self.__create_ui()
        self.__pack_ui()

    def start(self):
        self.tk.mainloop()

    def __create_ui(self):
        self.tk = tk.Tk()
        self.leftFrame = tk.Frame()
        self.rightFrame = tk.Frame()
        self.button = tk.Button(master=self.leftFrame,
                                text="Button",
                                command=self.__get_thread_task(self.__sleep))

    def __sleep(self):
        time.sleep(4)
        self.button.config(text="Button Clicked")

    def __pack_ui(self):
        self.leftFrame.pack(side=tk.LEFT)
        self.rightFrame.pack(side=tk.RIGHT)
        self.button.pack()

    def __get_thread_task(self, task):
        return lambda: self.__start_thread_task(task)

    def __start_thread_task(self, task):
        thread = threading.Thread(target=task)
        thread.start()
