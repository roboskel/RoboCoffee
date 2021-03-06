#!/usr/bin/env python
import sys
import freenect
import cv2
import numpy as np
import visual_frame_convert
import time
import os
import glob
import shutil
import mlpy
import scipy.spatial.distance as dist



HAAR_CASCADE_PATH = "haarcascade_frontalface_default.xml"




def plotCV(Fun, Width, Height, MAX):
	if len(Fun)>Width:
		hist_item = Height * (Fun[len(Fun)-Width-1:-1] / MAX)
	else:
		hist_item = Height * (Fun / MAX)
	h = np.zeros((Height, Width, 3))
	hist = np.int32(np.around(hist_item))

	for x,y in enumerate(hist):
		cv2.line(h,(x,Height),(x,Height-y),(255,0,255))
	return h





def getRGBHistograms(RGBimage):
	# compute histograms: 
	[histR, bin_edges] = np.histogram(RGBimage[:,:,0], bins=(range(-1,256, 16)))
	[histG, bin_edges] = np.histogram(RGBimage[:,:,1], bins=(range(-1,256, 16)))
	[histB, bin_edges] = np.histogram(RGBimage[:,:,2], bins=(range(-1,256, 16)))
	# normalize histograms:
	histR = histR.astype(float); histR = histR / np.sum(histR);
	histG = histG.astype(float); histG = histG / np.sum(histG);
	histB = histB.astype(float); histB = histB / np.sum(histB);
	return (histR, histG, histB)







def skin_detection(rgb):
	rgb = rgb.astype('float')
	normalizedR = rgb[:,:,0] / (rgb[:,:,0] + rgb[:,:,1] + rgb[:,:,2])
	normalizedG = rgb[:,:,1] / (rgb[:,:,0] + rgb[:,:,1] + rgb[:,:,2])
	normalizedB = rgb[:,:,2] / (rgb[:,:,0] + rgb[:,:,1] + rgb[:,:,2])

	#print "SKIN:", np.mean(normalizedR), np.mean(normalizedG), np.mean(normalizedB)
	return np.count_nonzero((normalizedR>=0.35) & (normalizedR <=0.55) & (normalizedG >=0.28) & (normalizedG <=0.35)) / float(rgb.shape[0]*rgb.shape[1])
	





def intersect_rectangles(r1, r2):
	x11 = r1[0]; y11 = r1[1]; x12 = r1[0]+r1[2]; y12 = r1[1]+r1[3];
	x21 = r2[0]; y21 = r2[1]; x22 = r2[0]+r2[2]; y22 = r2[1]+r2[3];
		
	X1 = max(x11, x21); X2 = min(x12, x22);
	Y1 = max(y11, y21); Y2 = min(y12, y22);

	W = X2 - X1
	H = Y2 - Y1
	if (H>0) and (W>0):
		E = W * H;
	else:
		E = 0.0;
	Eratio = 2.0*E / (r1[2]*r1[3] + r2[2]*r2[3])
	return Eratio








def resizeFrame(frame, targetWidth):	
	(Width, Height) = frame.shape[1], frame.shape[0]

	if targetWidth > 0: 							# Use FrameWidth = 0 for NO frame resizing
		ratio = float(Width) / targetWidth		
		newHeight = int(round(float(Height) / ratio))
		frameFinal = cv2.resize(frame, (targetWidth, newHeight))
	else:
		frameFinal = frame;

	return frameFinal




def detect_faces(rgb, cascadeFrontal, cascadeProfile, storage, newWidth, minWidthRange):
	facesFrontal = []; facesProfile = []
	image = cv2.cv.fromarray(rgb)
	detectedFrontal = cv2.cv.HaarDetectObjects(image, cascadeFrontal, storage, 1.3, 2, cv2.cv.CV_HAAR_DO_CANNY_PRUNING, (newWidth/minWidthRange, newWidth/minWidthRange))

	for (x,y,w,h),n in detectedFrontal:
		facesFrontal.append((x,y,w,h))

	# remove overlaps:
	while (1):
		Found = False
		for i in range(len(facesFrontal)):
			for j in range(len(facesFrontal)):
				if i != j:
					interRatio = intersect_rectangles(facesFrontal[i], facesFrontal[j])
					if interRatio>0.3:
						Found = True;
						del facesFrontal[i]
						break;
			if Found:
				break;
		if not Found:	# not a single overlap has been detected -> exit loop
			break;

	# remove non-skin
	countFaces = 0; facesFinal = []
	for (x,y,w,h) in facesFrontal:
		countFaces+=1
		window = 3
		#print h, y+2*h, rgb.shape[0]
		if y+int(h*window) < rgb.shape[0]:
			h = int(window*h)
		else:
			h = rgb.shape[0] - y - 1
		curFace = rgb[y:y+h, x:x+w, :]
		skinPercent = skin_detection(curFace) 
		if skinPercent > 0.1:
			curFace = resizeFrame(curFace, 100)
			curFace = curFace.astype(float);
			maxR = curFace[:,:,0].max()
			maxG = curFace[:,:,1].max()
			maxB = curFace[:,:,2].max()
			curFace[:,:,0] = 255*curFace[:,:,0] / float(maxR)
			curFace[:,:,1] = 255*curFace[:,:,1] / float(maxG)
			curFace[:,:,2] = 255*curFace[:,:,2] / float(maxB)
			[histR, histG, histB] = getRGBHistograms(curFace)
			Features = np.concatenate([histR, histG, histB])
			facesFinal.append((x,y,w,h,Features))
	
	return (facesFinal)







def analyzeKinect(modelName):

	#FeatureMatrix = np.load(modelName+".npy")
	HAAR_CASCADE_PATH_FRONTAL = "haarcascade_frontalface_default.xml"
	HAAR_CASCADE_PATH_PROFILE = "haarcascade_frontalface_default.xml"
	cascadeFrontal = cv2.cv.Load(HAAR_CASCADE_PATH_FRONTAL);
	cascadeProfile = cv2.cv.Load(HAAR_CASCADE_PATH_PROFILE);
	storage = cv2.cv.CreateMemStorage()
		
	count = 0	

	start = time.time()
	prevTime = start


	dirName1 = "Real_Scenario"
	if os.path.exists(dirName1):
    		shutil.rmtree(dirName1)
	os.makedirs(dirName1)
	


	while 1:
		rgb   = freenect.sync_get_video()[0]
		depth = freenect.sync_get_depth()[0]
		bgr = cv2.cvtColor(rgb, cv2.cv.CV_RGB2BGR)	
		# elapsedTime = "%08.3f" % (time.time() - start)
		elapsedTime = "%08.3f" % (time.time())

		# process depth:
		depth >> 5
		meter = 1.0 / (depth * (-0.0030711016) + 3.3309495161)

		faces = detect_faces(rgb, cascadeFrontal, cascadeProfile, storage, rgb.shape[1], 30)
		countFaces = 0
		bgr_plot = bgr.copy()
		print len(faces)
		if len(faces)>-1:	

			

			strFile =dirName1 + os.sep + "image{0:04d}".format(count)
			cv2.imwrite(strFile+'.jpg',bgr) 



		cv2.cv.ShowImage("depth",  visual_frame_convert.pretty_depth_cv(np.uint16(depth) )); 			cv2.moveWindow('depth', 720, 0)
		cv2.imshow("bgr",bgr); cv2.moveWindow('rgb', 0, 0)

		count += 1

		curTime = time.time()	
		#print (curTime - prevTime)
		prevTime = curTime

	    	if cv2.cv.WaitKey(10) == 27:
			break






def main(argv):
	# REAL TIME PROCESSING (OR FROM RECORDED DIRECTORY)
	analyzeKinect(argv[1])
	
if __name__ == "__main__":
	main(sys.argv)
