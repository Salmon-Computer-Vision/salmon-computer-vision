import BBoxManager as BBoxManager
import threading


def main():
    gui = BBoxManager.GUI()
    gui_trhead = threading.Thread(target=gui.start())
    gui_trhead.start()


main()
