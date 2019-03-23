import collections
import json
from . import features_coding
from . import question_detector
from . import speaker_diarization

def initialize(ip):
    features_coding.connect(ip)
    question_detector.connect(ip)
    speaker_diarization.connect(ip)

def start_routes():
    features_coding.start_route()
    question_detector.start_route()
    speaker_diarization.start_route()
