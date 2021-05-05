import cv2
from pycocotools.coco import COCO
from .BgUtility import BgUtility

# This file is to wrap COCO APIs. If there are changes in COCO APIs in the future,
# we can modify the code here instead of changing all places that use COCO APIs.


class CocoAPI:
    def __init__(self, annFile, dataDir):
        super().__init__()
        self.coco = COCO(annFile)
        self.dataDir = dataDir

    def get_categories(self):
        return self.coco.loadCats(self.coco.getCatIds())

    def get_category_id_by_names(self, names):
        return self.coco.getCatIds(catNms=names)

    def get_all_img_metadata(self):
        all_img_ids = self.coco.getImgIds()
        imgs = self.coco.loadImgs(all_img_ids)
        return imgs

    def get_all_annotations(self):
        all_annotation_ids = self.coco.getAnnIds()
        return self.coco.loadAnns(all_annotation_ids)

    def get_all_annotated_imgs(self, show_label=False, img_prefix=""):
        annotated_images = []
        img_metadata = self.get_all_img_metadata()
        for img in img_metadata:
            I = cv2.imread('{}/{}'.format(self.dataDir, img_prefix + img['file_name']))
            annIds = self.coco.getAnnIds(imgIds=img['id'])
            anns = self.coco.loadAnns(annIds)
            for ann in anns:
                bbox = ann["bbox"]
                x = bbox[0]
                y = bbox[1]
                w = bbox[2]
                h = bbox[3]
                I = cv2.rectangle(
                    I, (x, y), (x + w, y + h), (0, 255, 0), 1)
                if show_label:
                    I = cv2.putText(
                        I,
                        str(ann["object_id"]),
                        (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (0, 255, 0),
                        1
                    )
            annotated_images.append(I)
        return annotated_images

    def export_bbox_result(self):
        """
        Bbox file format follows this document:
        https://github.com/Cartucho/mAP#create-the-ground-truth-files
        """
        img_ids = self.coco.getImgIds()
        for img_id in img_ids:
            img = self.coco.loadImgs(img_id)[0]
            img_file_name_no_ext = img["file_name"][0:-4]
            BgUtility.create_dir_if_not_exist("{}/bbox_result".format(self.dataDir))
            with open("{}/{}/{}.txt".format(self.dataDir, "bbox_result", img_file_name_no_ext), 'w') as outfile:
                annIds = self.coco.getAnnIds(imgIds=img['id'])
                anns = self.coco.loadAnns(annIds)
                for ann in anns:
                    cat = self.coco.loadCats(ann["category_id"])[0]
                    bbox = ann["bbox"]
                    line_content = "{} {} {} {} {}\n".format(
                        cat["name"],
                        bbox[0],
                        bbox[1],
                        bbox[0] + bbox[2],
                        bbox[1] + bbox[3]
                    )
                    outfile.write(line_content)
