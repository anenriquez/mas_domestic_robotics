import numpy as np
import cv2
import tensorflow as tf
from keras.models import load_model
from cv_bridge import CvBridge

import rospy
from sensor_msgs.msg import Image

from pyftsm.ftsm import FTSMTransitions
from mas_execution.action_sm_base import ActionSMBase
from mdr_gender_recognition.msg import GenderRecognitionResult

class RecognizeGenderSM(ActionSMBase):
    def __init__(self, timeout=120.0, image_topic='/cam3d/rgb/image_raw',
                 gender_model_path=None, labels=None, image_size=(0, 0, 0),
                 max_recovery_attempts=1):
        super(RecognizeGenderSM, self).__init__('RecognizeGender', [], max_recovery_attempts)
        self.timeout = timeout
        self.gender_model_path = gender_model_path
        self.labels = labels
        self.image_size = image_size
        self.image_publisher = rospy.Publisher(image_topic, Image, queue_size=1)
        self.bridge = CvBridge()
        self.gender_model = None
        self.computation_graph = None

    def init(self):
        try:
            rospy.loginfo('[recognize_gender] Loading model %s', self.gender_model_path)
            self.gender_model = load_model(gender_model_path)

            # the following two lines are necessary for avoiding https://github.com/keras-team/keras/issues/2397
            self.gender_model._make_predict_function()
            self.computation_graph = tf.get_default_graph()
        except:
            rospy.logerr('[recognize_gender] Failed to load model %s', self.gender_model_path)
        return FTSMTransitions.INITIALISED

    def running(self):
        bounding_boxes = self.goal.bounding_boxes
        genders = []

        rospy.loginfo('[recognize_gender] Recognizing genders')
        rgb_image = self.__ros2cv(self.goal.image)
        gray_image = self.__rgb2gray(rgb_image)
        for face in bounding_boxes:
            x, y, w, h = face.bounding_box_coordinates
            face = gray_image[y: (y + h), x: (x + w)]  # check if it is not rgb
            face = cv2.resize(face, self.image_size[0:2])
            face = np.expand_dims(face, 0)
            face = np.expand_dims(face, -1)
            face = self.__preprocess_image(face)
            recognized_gender = self.__recognize_gender(face)
            genders.append(recognized_gender)
            cv2.putText(rgb_image, recognized_gender, (x, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0),
                        1, cv2.LINE_AA)
        output_ros_image = self.bridge.cv2_to_imgmsg(rgb_image, 'bgr8')
        self.image_publisher.publish(output_ros_image)

        self.result = self.set_result(True, genders)
        return FTSMTransitions.DONE

    def set_result(self, success, genders):
        result = GenderRecognitionResult()
        result.success = success
        result.genders = genders
        return result

    def __preprocess_image(self, image):
        image = image / 255.0
        return image

    def __recognize_gender(self, face):
        label = -1
        with self.computation_graph.as_default():
            class_predictions = self.gender_model.predict(face)
            label = self.labels[np.argmax(class_predictions)]
        return label

    def __ros2cv(self, ros_image):
        cv_image = self.bridge.imgmsg_to_cv2(ros_image, 'bgr8')
        return np.array(cv_image, dtype=np.uint8)

    def __rgb2gray(self, image):
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return gray_image
