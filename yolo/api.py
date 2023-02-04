import random
from typing import Tuple

import numpy as np
import torch

from .experimental import attempt_load
from .utils.datasets import letterbox
from .utils.general import check_img_size, non_max_suppression, scale_coords
from .utils.plots import plot_one_box


class YoloDetector:
    def __init__(self, classes: list, conf_th: float = 0.25, iou_th: float = 0.45):
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.classes = classes
        self.conf_th = conf_th
        self.iou_th = iou_th

    def load(self, weights: str, img_size: int = 640):
        self.half = self.device.type != "cpu"
        self.model = attempt_load(weights, map_location=self.device)
        self.stride = int(self.model.stride.max())
        self.img_size = check_img_size(img_size, self.stride)

        if self.half:
            self.model.half()

        if self.device.type != "cpu":  # run once
            self.model(
                torch.zeros(1, 3, self.imgsz, self.imgsz)
                .to(self.device)
                .type_as(next(self.model.parameters()))
            )

        # names and bbox colors of each object class
        self.classes = (
            self.model.module.names
            if hasattr(self.model, "module")
            else self.model.names
        )
        self.classes = dict(zip(range(len(self.classes)), self.classes))
        self.colors = [random.sample(range(256), 3) for _ in self.classes]

    @torch.no_grad()
    def detect(self, img: np.ndarray, draw_bbox: bool = False):
        # prepare the input image
        img, orig = self.preprocess(img)
        if img.ndimension == 3:
            img = img.unsqueeze(0)

        # inference and non-maximum suppression
        pred = self.model(img, augment=False)[0]
        pred = non_max_suppression(pred, self.conf_th, self.iou_th, self.classes)

        dets = pred[0]
        if not len(dets):
            return orig if draw_bbox else None
        dets[:, :4] = scale_coords(img.shape[2:], dets[:, :4], orig.shape).round()
        if draw_bbox:
            for *xyxy, conf, cls in reversed(dets):
                label = f"{self.classes[int(cls)]} {conf:.2f}"
                plot_one_box(xyxy, orig, self.colors[int(cls)], label, line_thickness=1)
        return orig if draw_bbox else dets.detach().cpu().numpy()

    def preprocess(self, img: np.ndarray) -> Tuple[torch.Tensor, np.ndarray]:
        new = letterbox(img, self.img_size, stride=self.stride, scaleup=False)
        new = new[..., ::-1].transpose(2, 0, 1)
        new = np.ascontiguousarray(new)
        new = torch.from_numpy(new).to(self.device)
        new = new.half() if self.half else new.float()
        return new / 255, img