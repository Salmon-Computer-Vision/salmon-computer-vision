from .dataloader import DataLoader

import datumaro as dm
import os
from pathlib import Path
import cv2
from ultralytics import YOLO

from collections import defaultdict
import numpy as np
import pandas as pd

class SalmonCounter:
    LEFT_PRE = 'l_'
    RIGHT_PRE = 'r_'
    FILENAME = 'filename'
    TRACK_COUNT = 'track_count'
    CLASS_VOTE = 'class_vote'
    FONT = cv2.FONT_HERSHEY_SIMPLEX
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
        self.vis_salm_count = {self.LEFT_PRE: 0, self.RIGHT_PRE: 0} # For visualization purposes
        self.prev_track_ids = {}
        self.tracking_thresh = tracking_thresh
        

    def count(self, use_gt=False, save_vid=False):
        cur_clip = self.dataloader.next_clip()
        self.salm_count.loc[cur_clip.name] = 0

        if save_vid:
            OUTPUT_PATH = Path('output_vids')
            OUTPUT_PATH.mkdir(exist_ok=True)
            # Reset vis salmon count
            self.vis_salm_count[self.LEFT_PRE] = 0
            self.vis_salm_count[self.RIGHT_PRE] = 0
            fourcc = cv2.VideoWriter_fourcc(*'MP4V')
            out_vid = cv2.VideoWriter(str(OUTPUT_PATH / f'{cur_clip.name}.mp4'), fourcc, 25.0, (1920, 1080))

        frame_count = 0
        for item in self.dataloader.items():
            # Run YOLOv8 tracking on the frame, persisting tracks between frames
            results = self.model.track(item.frame, persist=True)
    
            # Get the boxes and track IDs
            boxes = results[0].boxes.xywh.cpu()
            id_items = results[0].boxes.id
            
            track_ids = []
            cls_ids = []
            if id_items is not None:
                track_ids = id_items.int().cpu().tolist()
                cls_ids = results[0].boxes.cls.int().cpu().tolist()

    
            # When any tracking ID is lost
            # Set difference prev track IDs - current track IDs
            not_tracking = set(self.prev_track_ids.keys()).difference(track_ids)
            for track_id in not_tracking:
                if self.prev_track_ids[track_id][self.TRACK_COUNT] > 0 and item.num_items - frame_count > self.tracking_thresh:
                    # Each tracking ID has a counter
                    # Decrement counter for that tracking ID
                    self.prev_track_ids[track_id][self.TRACK_COUNT] -= 1
                else:
                    # After a track disappears for tracking_thresh frames
                    # Find max voted class
                    class_vote = self.prev_track_ids[track_id][self.CLASS_VOTE]
                    if class_vote:
                        main_class_id = max(class_vote, key=class_vote.get)
                        # Run LOI on no longer tracking IDs
                        self._line_of_interest(results[0].orig_shape[1], cur_clip, track_id, self.track_history[track_id], main_class_id)
                        
                    del self.prev_track_ids[track_id]
                    del self.track_history[track_id]
            

            if save_vid:
                # Visualize the results on the frame
                annotated_frame = results[0].plot()
                # Draw counter
                text = f'Count - Right: {self.vis_salm_count[self.RIGHT_PRE]}, Left: {self.vis_salm_count[self.LEFT_PRE]}'
                img_shape = results[0].orig_shape
                textsize = cv2.getTextSize(text, self.FONT, 1, 2)[0]
                # get coords based on boundary
                textX = int((img_shape[1] - textsize[0]) / 2)
                # add text centered on image
                cv2.putText(annotated_frame, text, (textX, textsize[1] + 5), self.FONT, 1, (255, 255, 255), 2)
            
            # Plot the tracks
            for box, track_id, cls_id in zip(boxes, track_ids, cls_ids):
                x, y, w, h = box
                track = self.track_history[track_id]
                track.append((float(x), float(y)))  # x, y center point
                
                if track_id not in self.prev_track_ids:
                    self.prev_track_ids[track_id] = {
                        self.TRACK_COUNT: self.tracking_thresh,
                        self.CLASS_VOTE: {}
                    }
                else:
                    class_vote = self.prev_track_ids[track_id][self.CLASS_VOTE]
                    if cls_id not in class_vote:
                        class_vote[cls_id] = 0
                    class_vote[cls_id] += 1

                if save_vid:
                    # Draw the tracking lines
                    points = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))
                    cv2.polylines(annotated_frame, [points], isClosed=False, color=(230, 230, 230), thickness=10)

            if save_vid:
                out_vid.write(annotated_frame)

            frame_count += 1

        if save_vid:
            out_vid.release()
        return self.salm_count

    def _line_of_interest(self, f_width, cur_clip, track_id, track, main_class_id):
        # Check start and end of track ID
        # Count if start and end are on either sides of the LOI
        half_width = f_width / 2
        first_track_x = track[0][0]
        last_track_x = track[-1][0]
        classes = self.dataloader.classes()
        if first_track_x < half_width and last_track_x >= half_width:
            # Counted going to the right
            self.vis_salm_count[self.RIGHT_PRE] += 1
            self.salm_count.loc[cur_clip.name, self.RIGHT_PRE + classes[main_class_id]] += 1
        elif first_track_x > half_width and last_track_x <= half_width:
            # Counted going to the left
            self.vis_salm_count[self.LEFT_PRE] += 1
            self.salm_count.loc[cur_clip.name, self.LEFT_PRE + classes[main_class_id]] += 1