# -*- coding: utf-8 -*-
"""Model_to_green_value

"""

# Base libraries
import os
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import random
import cv2
import pycocotools
import warnings
import sys
import pandas as pd
import warnings
import re
from git import Repo
from pathlib import Path

## Torch libraries
import torch
import torch.utils.data
import torchvision
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
from torchvision.io import read_image
from torchvision.transforms.functional import convert_image_dtype
import torchvision.transforms.functional as F

# Check if directory for additional Torch libraries exists
torchlibs = Path('vision')

if torchlibs.exists == "False":
  Repo.clone_from('https://github.com/John-Polo/vision.git', './vision')

# Torch libraries from further out on the path
from vision.references.detection import utils
from vision.references.detection import transforms
from vision.references.detection import coco_eval
from vision.references.detection import engine
from vision.references.detection import coco_utils
#
#from google.colab import drive
#drive.mount('/content/drive', force_remount=True)
##

"""
John forked the Torch repo to keep the functions as the were at the time this code was originally written. Will periodically check the functions for updates.
"""

# This list is here because of the model. These are all the classes the pre-
# trained model uses. It's possible that the whole list isn't necessary, but I'm
# not sure. It doesn't hurt anything to keep. Definitely need at least the first 
# two items. As the model is refined and more classes are added, may have to 
# change the classes. The first class in the original list is "person", not well,
# so I would change the object directly until I know better.
coco_names = [
    '__background__', 'well', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus',
    'train', 'truck', 'boat', 'traffic light', 'fire hydrant', 'N/A', 'stop sign',
    'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
    'elephant', 'bear', 'zebra', 'giraffe', 'N/A', 'backpack', 'umbrella', 'N/A', 'N/A',
    'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'N/A', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl',
    'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza',
    'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed', 'N/A', 'dining table',
    'N/A', 'N/A', 'toilet', 'N/A', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'N/A', 'book',
    'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]

# Necssary for a later code section. Since it uses "coco_names" directly, just
# thought I'd put it here.
color_n = np.random.uniform(0, 255, size=(len(coco_names), 3))

# This lets model and other settings choose between a CPU and GPU. If there is a
# GPU available for true Torch abilities, it will use CUDA, the protocol for GPU.
device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

warnings.filterwarnings("ignore")#, message="UserWarning: Named tensors and all their associated")

# Load the model from the saved file:
model = torch.load('https://drive.google.com/file/d/1lwm_By5aCyLnSnmUxMnPEhMEnmu9Ryl_/view?usp=sharing', map_location=device)
model.load_state_dict(torch.load('https://drive.google.com/file/d/1nzSMfm3QNqhyLQ5HHD5QEiNuCUyw6Hfx/view?usp=sharing', map_location=device))
#model.to(device)

#The output from this can be cleared from the screen. Don't know how to do that.
model.eval()

"""The model returns a **Dict[Tensor]** during training, containing the classification and regression losses for both the RPN and the R-CNN, and the mask loss.

During inference, the model requires only the input tensors, and returns the post-processed predictions as a **List[Dict[Tensor]]**, one for each input image. The fields of the Dict are as follows, where N is the number of detected instances:

        boxes (FloatTensor[N, 4]): the predicted boxes in [x1, y1, x2, y2]
         format, with 0 <= x1 < x2 <= W and 0 <= y1 < y2 <= H.

        labels (Int64Tensor[N]): the predicted labels for each instance

        # This is actually the 4th item in the list of outputs
        scores (Tensor[N]): the scores or each instance

        # This is actually the 3rd item in the list of outputs from model.
        masks (UInt8Tensor[N, 1, H, W]): the predicted masks for each
         instance, in 0-1 range. In order to obtain the final segmentation
         masks, the soft masks can be thresholded, generally with a value
         of 0.5 (mask >= 0.5)


"""

# Where are the new images that will need to be analyzed going to be stored?
img_dir = input("Please provide a directory path that has the images awaiting\
 analysis.\n")

if os.path.exists(img_dir) == "False":
    raise TypeError("The path provided does not exist. Do you need to provide a\
    leading '/' (on Windows, you need to provide 'C:\' instead).")

# Just base name of file for possibly using as short name in later functions.
waiting_images = list()
# Complete path of files
w_im_dir_read = list()

for file in os.listdir(img_dir):
    if file.endswith(".png"):
        waiting_images.append( file)
        w_im_dir_read.append(os.path.join(img_dir, file))
    
waiting_images = sorted(waiting_images)
w_im_dir_read = sorted(w_im_dir_read)
        
# Check for even number of images. Otherwise, a 00 or 61 is probably missing.
if len(waiting_images) % 2 == 1:
  raise IndexError("Error: odd number of images. Is there a 0 min. image and a 61\
  min. image for each assay?")

print("The following images will be analyzed:{}\n".format(waiting_images))

img_count = 0
#/content/drive/MyDrive/APHIS Farm Bill (2020Milestones)/Protocols/For John/images/New set for John/collection/four_chambers/imgs_centercropped

# Need a way to check if image have been processed or not. Have to set up a 
# tracking table.

im_start_lis = list()
im_perm_lis = list()

for i in range(len(waiting_images)):
    # "read_image" is the Torchvision version of image ingestion.
    im_start_lis.append(read_image(w_im_dir_read[i]).to(device))
    # Change Torch-based image read to shape that plt can render. (4,1600,1600) 
    # to (1600,1600,4) 
    im_perm_lis.append(im_start_lis[i].permute(1,2,0))

batch_int = list()

for i,j in zip(range(0,len(im_start_lis),2),range(1,len(im_start_lis),2)):
    # Gather inputs for batches. The model is run on each batch for the 
    # comparison.
    batch_int.append(torch.stack([im_start_lis[i], im_start_lis[j]]))
    #batch_lis.append(batch(convert_image_dtype(batch_int[i], dtype=torch.float)))

batch = list()

for i in range(len(batch_int)):
    batch.append(convert_image_dtype(batch_int[i], dtype=torch.float))

# Creates outputs from the model that can be used with other functions and 
# classes created later on. 
# This will grab the first of the pair of images to be compared.
def get_first_outputs(image, model, threshold):
    with torch.no_grad():
        # forward pass of the image through the modle
        outputs = model(image)
    
    # get all the scores
    scores = list(outputs[0]['scores'].detach().cpu().numpy())
    # index of those scores which are above a certain threshold
    thresholded_preds_indices = [scores.index(i) for i in scores if i > threshold]
    thresholded_preds_count = len(thresholded_preds_indices)
    # get the masks
    masks = (outputs[0]['masks']>0.5).squeeze().detach().cpu().numpy()
    # discard masks for objects which are below threshold
    masks = masks[:thresholded_preds_count]
    # get the bounding boxes, in (x1, y1), (x2, y2) format
    boxes = [[(int(i[0]), int(i[1])), (int(i[2]), int(i[3]))]  for i in outputs[0]['boxes'].detach().cpu()]
    # discard bounding boxes below threshold value
    boxes = boxes[:thresholded_preds_count]
    # get the classes labels
    labels = [coco_names[i] for i in outputs[0]['labels']]
    return masks, boxes, labels

# Creates outputs from the model that can be used with other functions and 
# classes created later on. 
# This will provide the second of the pair of images to be compared.
def get_second_outputs(image, model, threshold):
    with torch.no_grad():
        # forward pass of the image through the modle
        outputs = model(image)
    
    # get all the scores
    scores = list(outputs[1]['scores'].detach().cpu().numpy())
    # index of those scores which are above a certain threshold
    thresholded_preds_indices = [scores.index(i) for i in scores if i > threshold]
    thresholded_preds_count = len(thresholded_preds_indices)
    # get the masks
    masks = (outputs[1]['masks']>0.5).squeeze().detach().cpu().numpy()
    # discard masks for objects which are below threshold
    masks = masks[:thresholded_preds_count]
    # get the bounding boxes, in (x1, y1), (x2, y2) format
    boxes = [[(int(i[0]), int(i[1])), (int(i[2]), int(i[3]))]  for i in outputs[1]['boxes'].detach().cpu()]
    # discard bounding boxes below threshold value
    boxes = boxes[:thresholded_preds_count]
    # get the classes labels
    labels = [coco_names[i] for i in outputs[1]['labels']]
    return masks, boxes, labels

mod_res_all = list()
for b in range(len(batch)):
    mod_res_all.append(get_first_outputs(batch[b], model, 0.9))
    mod_res_all.append(get_second_outputs(batch[b], model, 0.9))

mask_composite_num = list()
mask_mult = list()
img_mask_comp = list()


for i in range(len(mod_res_all)):
    # This is a logical operation to get the multiple arrays of the masks 
    # flattened down to a single array (layer or channel in an imagery sense) 
    # and to change the mask from T/F to 1/0.
    mask_composite_num.append((mod_res_all[i][0].sum(axis=0) > 0)*1)
    # To run the next function, the mask needs to have 3 channels/layers/arrays.
    mask_mult.append(np.stack((mask_composite_num[i], mask_composite_num[i], mask_composite_num[i]), axis=-1))
    # Multiple image and mask. 
    img_mask_comp.append(im_perm_lis[i]*mask_mult[i])

# Get values of green channels, after dividing the np.ndarrays into sections
def green_cn(x):
    if type(x) == torch.Tensor:
        #print(f"{x} is a Tensor. Changed to np.array")
        x = x.detach().cpu().numpy()
    #elif type(x) == PIL.Image.Image:
        #print(f"{x} is a PIL.Image. Changed to np.array")
    #    x = np.array(x)
    # x is an np.ndarray!
    width, height = x.shape[0:2]
    # set halves
    v_half = height//2
    h_half = width//2
    #split the halves into the quarters
    up_l_gr = x[:v_half,:h_half,1]
    up_r_gr = x[:v_half,h_half+1:,1]
    lw_l_gr = x[v_half+1:,:h_half,1]
    lw_r_gr = x[v_half+1:,h_half+1:,1]
    uplg_mean = up_l_gr[np.nonzero(up_l_gr)].mean()
    uprg_mean = up_r_gr[np.nonzero(up_r_gr)].mean()
    lwlg_mean = lw_l_gr[np.nonzero(lw_l_gr)].mean()
    lwrg_mean = lw_r_gr[np.nonzero(lw_r_gr)].mean()
    return lwlg_mean,uplg_mean,uprg_mean,lwrg_mean

green_val = list()

for i in range(len(img_mask_comp)):
    green_val.append(green_cn(img_mask_comp[i]))

def threshold_test(z,s):
    z_threshold = np.mean(z)+3*np.std(z)
    if s[1] <= z_threshold:
        Pi_status = "negative"
    else:
        Pi_status = "positive"
    if s[2] <= z_threshold:
        TSWV_status = "negative"
    else:
        TSWV_status = "positive"
    if s[3] <= z_threshold:
        NC_status = "negative"
    else:
        NC_status = "positive"
    status_list=list([dict(Assay_level=z_threshold), 
                      dict(P_infestans_status_and_score=[Pi_status, s[1]]), 
                      dict(TSWV_status_and_score=[TSWV_status,s[2]]), 
                      dict(NC_status_and_score=[NC_status,s[3]])])

    return status_list

pair_idx = list()

for i in range(0,len(green_val),2):
    j = i+1
    pair_idx.append((i, j))

pair_idx

threshold_list = list()

for i in range(len(pair_idx)):
    threshold_list.append(threshold_test(green_val[pair_idx[i][0]],green_val[pair_idx[i][1]]))

for i in range(len(threshold_list)):
    print("Result for {} is {}.\n".format(waiting_images[pair_idx[i][0]],threshold_list[i]))

# Add something like "image {}" later
#print('Results after modeling {} and {} are:\n{} \n{} \n{} \n{}'.format(waiting_images[0],
#                                                                        waiting_images[2],
#                                                                        threshold_result[0], 
#                                                              threshold_result[1], 
#                                                              threshold_result[2], 
#                                                              threshold_result[3]))

# Optional plotting. Good for a sanity check.
def draw_segmentation_map(image, masks, boxes, labels):
    alpha = 1 
    beta = 0.4 # transparency for the segmentation map
    gamma = 0 # scalar added to each sum
    for i in range(len(masks)):
        red_map = np.zeros_like(masks[i]).astype(np.uint8)
        green_map = np.zeros_like(masks[i]).astype(np.uint8)
        blue_map = np.zeros_like(masks[i]).astype(np.uint8)
        # apply a randon color mask to each object
        color = color_n[random.randrange(0, len(color_n))]
        red_map[masks[i] == 1], green_map[masks[i] == 1], blue_map[masks[i] == 1]  = color
        # combine all the masks into a single image
        segmentation_map = np.stack([red_map, green_map, blue_map], axis=2)
        #convert the original PIL image into NumPy format
        image = np.array(image)
        # convert from RGN to OpenCV BGR format
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        # apply mask on the image
        cv2.addWeighted(image, alpha, segmentation_map, beta, gamma, image)
        # draw the bounding boxes around the objects
        cv2.rectangle(image, boxes[i][0], boxes[i][1], color=color, 
                      thickness=2)
        # put the label text above the objects
        cv2.putText(image , labels[i], (boxes[i][0][0], boxes[i][0][1]-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, color, 
                    thickness=2, lineType=cv2.LINE_AA)
    
    return image

# Example drawing. Need to fix the inputs.
#results = draw_segmentation_map(z_im_perm, mask_zero, boxes_zero, labels_zero)

# Optional plotting. Good for a sanity check
def segmentation_plotting(original_image, segmentation_result):
    plt.figure(figsize=(12,6))
    plt.subplot(1,2,1)
    plt.imshow(original_image)
    plt.subplot(1,2,2)
    plt.imshow(segmentation_result)

# Optional plotting. Good for a sanity check.
#segmentation_plotting(z_im_perm, results)

# More optional plotting II. 

# Break images up into four sections for plotting.
def four_cn(x):
    if type(x) == torch.Tensor:
        x = x.detach().cpu().numpy()
    elif type(x) == PIL.Image.Image:
        #print(f"{x} is a PIL.Image")
        exit
    # x is an np.ndarray!
    width, height = x.shape[0:2]
    # set halves
    v_half = height//2
    h_half = width//2
    #split the halves into the quarters
    up_lf = x[:v_half,:h_half,:]
    up_rt = x[:v_half,h_half+1:,:]
    lw_lf = x[v_half+1:,:h_half,:]
    lw_rt = x[v_half+1:,h_half+1:,:]
    return lw_lf,up_lf,up_rt,lw_rt

def four_cn_image(x):
    if type(x) == torch.Tensor:
        x = x.detach().cpu().numpy()
        x = Image.fromarray(np.uint8(x))
    elif type(x) == np.ndarray:
        x = Image.fromarray(np.uint8(x))
    image = x
    width, height = image.size
    #set dividers and bottom halves
    v_half = height//2
    h_half = width//2
    #split the halves into the quarters
    up_lf = image.crop((0,0,h_half,v_half))
    up_rt = image.crop((h_half+1,0,width,v_half))
    lw_lf = image.crop((0,v_half+1,h_half,height))
    lw_rt = image.crop((h_half+1,v_half+1,width,height))
    return lw_lf,up_lf,up_rt,lw_rt
