import gui as bboxUI
import threading


def main():
    gui = bboxUI.GUI()
    gui_trhead = threading.Thread(target=gui.start())
    gui_trhead.start()


main()
