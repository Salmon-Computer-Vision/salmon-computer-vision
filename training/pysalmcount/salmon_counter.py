from .dataloader import DataLoader

import datumaro as dm
import os
from os import path as osp
import cv2
from ultralytics import YOLO

from collections import defaultdict
import numpy as np
import pandas as pd

class SalmonCounter:
    LEFT_PRE = 'l_'
    RIGHT_PRE = 'r_'
    FILENAME = 'filename'
    def __init__(self, model_path: str, dataloader: DataLoader, tracking_thresh = 10):
        self.model = YOLO(model_path)
        self.dataloader = dataloader
        self.track_history = defaultdict(lambda: [])
        classes = dataloader.classes()
        cols = [self.FILENAME]
        for i in range(len(classes)):
            cols.append(self.LEFT_PRE + classes[i])
            cols.append(self.RIGHT_PRE + classes[i])
        self.salm_count = pd.DataFrame(columns=cols).set_index(self.FILENAME)
        self.prev_track_ids = {}
        self.tracking_thresh = tracking_thresh
        

    def count(self, use_gt=False):
        cur_clip = self.dataloader.next_clip()
        self.salm_count.loc[cur_clip.name] = 0
        #fourcc = cv2.VideoWriter_fourcc(*'MP4V')
        #out_vid = cv2.VideoWriter('output.mp4', fourcc, 25.0, (1920, 1080))
        for item in self.dataloader.items():
            # Run YOLOv8 tracking on the frame, persisting tracks between frames
            results = self.model.track(item.frame, persist=True)
    
            # Get the boxes and track IDs
            boxes = results[0].boxes.xywh.cpu()
            id_items = results[0].boxes.id
            track_ids = []
            if id_items:
                track_ids = id_items.int().cpu().tolist()
    
            # Visualize the results on the frame
            #annotated_frame = results[0].plot()
    
            # When any tracking ID is lost
            # Set difference prev track IDs - current track IDs
            not_tracking = set(self.prev_track_ids.keys()).difference(track_ids)
            for track_id in not_tracking:
                if self.prev_track_ids[track_id] > 0:
                    # Each tracking ID has a counter
                    # Decrement counter for that tracking ID
                    self.prev_track_ids[track_id] -= 1
                else:
                    # After a track disappears for tracking_thresh frames
                    # Run LOI on no longer tracking IDs
                    
                    self._line_of_interest(results[0].orig_shape[1], cur_clip, track_id, self.track_history[track_id])
                    del self.prev_track_ids[track_id]
                    del self.track_history[track_id]
            
            # Plot the tracks
            for box, track_id in zip(boxes, track_ids):
                x, y, w, h = box
                track = self.track_history[track_id]
                track.append((float(x), float(y)))  # x, y center point
                
                if track_id not in self.prev_track_ids:
                    self.prev_track_ids[track_id] = self.tracking_thresh
                
                #if len(track) > 30:  # retain 90 tracks for 90 frames
                #    track.pop(0)
    
                # Draw the tracking lines
                #points = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))
                #cv2.polylines(annotated_frame, [points], isClosed=False, color=(230, 230, 230), thickness=10)
            
            #out_vid.write(annotated_frame)

        #out_vid.release()
        return self.salm_count

    def _line_of_interest(self, f_width, cur_clip, track_id, track):
        # Check start and end of track ID
        # Count if start and end are on either sides of the LOI
        half_width = f_width / 2
        first_track_x = track[0][0]
        last_track_x = track[-1][0]
        classes = self.dataloader.classes()
        if first_track_x < half_width and last_track_x >= half_width:
            # Counted going to the right
            # TODO: Figure out classes
            self.salm_count.loc[cur_clip.name, self.RIGHT_PRE + classes[0]] += 1
        elif first_track_x > half_width and last_track_x <= half_width:
            # Counted going to the left
            self.salm_count.loc[cur_clip.name, self.LEFT_PRE + classes[0]] += 1