from .dataloader import DataLoader

import os
import logging
from pathlib import Path
import cv2
import time
from ultralytics import YOLO
from ultralytics.engine.results import Results
from ultralytics.engine.results import Boxes

from collections import defaultdict
import numpy as np
import pandas as pd

VOTE_METHOD_ALL = 'all'
VOTE_METHOD_IGN = 'ignore_thin'
VOTE_METHOD_CONF = 'confidence'

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
)

logger = logging.getLogger(__name__)

class SalmonCounter:
    LEFT_PRE = 'l_'
    RIGHT_PRE = 'r_'
    FILENAME = 'filename'
    TRACK_COUNT = 'track_count'
    CLASS_VOTE = 'class_vote'
    FONT = cv2.FONT_HERSHEY_SIMPLEX
    def __init__(self, model, dataloader: DataLoader, tracking_thresh = 10, save_dir="save_dir"):
        self.model = model
        self.dataloader = dataloader
        self.track_history = defaultdict(lambda: [])
        classes = dataloader.classes()
        cols = [self.FILENAME]
        for i in range(len(classes)):
            cols.append(self.LEFT_PRE + classes[i])
            cols.append(self.RIGHT_PRE + classes[i])
        self.full_salm_count = pd.DataFrame(columns=cols).set_index(self.FILENAME)
        self.salm_count = pd.DataFrame(columns=cols).set_index(self.FILENAME)
        self.vis_salm_count = {self.LEFT_PRE: 0, self.RIGHT_PRE: 0} # For visualization purposes
        self.prev_track_ids = {}
        self.tracking_thresh = tracking_thresh
        self.save_dir = save_dir
        
    def _vote_cond(self, w, h, vote_method='all'):
        if vote_method == VOTE_METHOD_ALL:
            return True
        elif vote_method == VOTE_METHOD_CONF:
            return True
        elif vote_method == VOTE_METHOD_IGN:
            return w > h # No thin boxes in the votes

    def _vote_weight(self, conf, vote_method='all'):
        if vote_method == VOTE_METHOD_ALL:
            return 1
        elif vote_method == VOTE_METHOD_CONF:
            return conf
        elif vote_method == VOTE_METHOD_IGN:
            return 1

    def count(self, tracker="botsort.yaml", use_gt=False, save_vid=False, save_txt=False, vote_method='all', device=0,
            stream_write=True, output_csv_dir='output_count'):
        if vote_method not in [VOTE_METHOD_ALL, VOTE_METHOD_IGN, VOTE_METHOD_CONF]:
            raise ValueError(f'{vote_method} is not a valid method')
            
        cur_clip = self.dataloader.next_clip()
        self.salm_count.loc[cur_clip.name] = 0
        logger.info(cur_clip.name)

        if save_txt:
            txt_dir = Path(self.save_dir) / Path(cur_clip.name).stem
            txt_dir.mkdir()
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
            if frame_count % 20 == 0:
                start_time = time.time()

            boxes = []
            track_ids = []
            cls_ids = []
            confs = []
            if not use_gt:
                # Run YOLOv8 tracking on the frame, persisting tracks between frames
                if frame_count % 20 == 0:
                    inf_start_time = time.time()
                results = self.model.track(item.frame, tracker=tracker,
                        project=self.save_dir, name=cur_clip.name,
                        persist=True, verbose=False, device=device)
                if frame_count % 20 == 0:
                    inf_end_time = time.time()
                    inf_elapsed = (inf_end_time - inf_start_time) * 1000
                    logger.info(f"Inference time: {inf_elapsed:.2f}")

                orig_shape = results[0].orig_shape
                # Get the boxes and track IDs
                boxes = results[0].boxes.xywh.cpu()
                id_items = results[0].boxes.id
                
                if id_items is not None:
                    track_ids = id_items.int().cpu().tolist()
                    cls_ids = results[0].boxes.cls.int().cpu().tolist()
                    confs = results[0].boxes.conf.cpu().tolist()
            else:
                img = cv2.imread(item.frame)
                h, w, _ = img.shape
                orig_shape = (h, w)
                input_boxes = None
                if item.boxes.any():
                    boxes_obj = Boxes(item.boxes, item.orig_shape)
                    boxes = boxes_obj.xywh
                    input_boxes = boxes_obj.data
                    track_ids = boxes_obj.id.tolist()
                    cls_ids = boxes_obj.cls.tolist()
                    confs = boxes_obj.conf.tolist()
                results = [Results(img, item.frame, self.dataloader.classes(), boxes=input_boxes)]

    
            # When any tracking ID is lost
            # Set difference prev track IDs - current track IDs
            not_tracking = set(self.prev_track_ids.keys()).difference(track_ids)
            if frame_count >= item.num_items - 1:
                not_tracking = set(self.prev_track_ids.keys()) # Finish up leftover tracks
            for track_id in not_tracking:
                if self.prev_track_ids[track_id][self.TRACK_COUNT] > 0 and item.num_items - frame_count > self.tracking_thresh:
                    # Each tracking ID has a counter
                    # Decrement counter for that tracking ID
                    self.prev_track_ids[track_id][self.TRACK_COUNT] -= 1
                else:
                    # After a track disappears for tracking_thresh frames
                    # Find max voted class
                    class_vote = self.prev_track_ids[track_id][self.CLASS_VOTE]
                    logger.info("Class vote:", class_vote)
                    if class_vote:
                        main_class_id = max(class_vote, key=class_vote.get)
                        # Run LOI on no longer tracking IDs
                        self._line_of_interest(orig_shape[1], cur_clip, track_id, self.track_history[track_id], main_class_id)
                        
                    del self.prev_track_ids[track_id]
                    del self.track_history[track_id]
            

            if save_vid:
                # Visualize the results on the frame
                annotated_frame = results[0].plot()
                # Draw counter
                text = f'Count - Right: {self.vis_salm_count[self.RIGHT_PRE]}, Left: {self.vis_salm_count[self.LEFT_PRE]}'
                textsize = cv2.getTextSize(text, self.FONT, 1, 2)[0]
                # get coords based on boundary
                textX = int((orig_shape[1] - textsize[0]) / 2)
                # add text centered on image
                cv2.putText(annotated_frame, text, (textX, textsize[1] + 5), self.FONT, 1, (255, 255, 255), 2)
            
            # Plot the tracks
            for box, track_id, cls_id, conf in zip(boxes, track_ids, cls_ids, confs):
                x, y, w, h = box
                track = self.track_history[track_id]
                track.append((float(x), float(y)))  # x, y center point

                if track_id not in self.prev_track_ids:
                    self.prev_track_ids[track_id] = {
                        self.TRACK_COUNT: self.tracking_thresh,
                        self.CLASS_VOTE: {}
                    }

                if track_id in self.prev_track_ids and self._vote_cond(w=w, h=h, vote_method=vote_method):
                    class_vote = self.prev_track_ids[track_id][self.CLASS_VOTE]
                    if cls_id not in class_vote:
                        class_vote[cls_id] = 0
                    class_vote[cls_id] += self._vote_weight(conf, vote_method=vote_method)

                if save_txt:
                    with open(str(txt_dir / f"frame_{frame_count:06d}.txt"), 'a') as f:
                        f.write(f"{cls_id} {x} {y} {w} {h} {conf} {track_id}\n")
                if save_vid:
                    # Draw the tracking lines
                    points = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))
                    cv2.polylines(annotated_frame, [points], isClosed=False, color=(230, 230, 230), thickness=10)

            if save_vid:
                out_vid.write(annotated_frame)

            if frame_count % 20 == 0:
                end_time = time.time()
                elapsed_time = (end_time - start_time) * 1000
                logger.info(f"Execution time: {elapsed_time:.2f} ms")
            frame_count += 1

        if stream_write:
            if not os.path.exists(output_csv_dir):
                os.makedirs(output_csv_dir)
            output_name_path = str(Path(output_csv_dir) / Path(cur_clip.name).stem)
            self.salm_count.to_csv(f"{output_csv_path}.csv")
                
        self.full_salm_count = pd.concat([self.full_salm_count, self.salm_count])
        self.salm_count = self.salm_count.iloc[0:0] # Clear salm count for streaming purposes
        if save_vid:
            out_vid.release()
        return self.salm_count

    def _increm_count(name, timestamp, class_direct):
        if (name, timestamp) not in df.index:
            df.loc[(name, timestamp)] = 0
        df.loc[(name, timestamp), class_direct] += 1

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
