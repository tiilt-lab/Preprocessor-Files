import json
import collections
import sqlite3 as lite
import re
import os
import numpy
import websockets
import time
from .pyDiarization import speakerDiarization

from autobahn.twisted.websocket import connectWS

DATABASE_FILE = os.path.dirname(os.path.abspath(__file__)) + '/../../../../collector.db'

def getId(ip):

    pod_id = None
    conn = lite.connect(DATABASE_FILE)
    cur = conn.cursor()

    try:
        cur.execute('SELECT pod_id, ip_address FROM pods')
        info = cur.fetchall()

        for value in info:
            if (value[1] == ip):
                pod_id = value[0]

    except lite.Error as e:
        raise Exception('internal error: {}'.format(e.args[0]))

    conn.close()
    return pod_id

class SpeakerDiarizationService(websockets.RouteService):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def onOpen(self):
        self.protocol.sendMessage(json.dumps({
            'version': 1.0,
            'type': 'transcripts_extras'
        }).encode('utf-8'), False)

class SpeakerDiarizationProcessor():

    def __init__(self, ip):
        self.mt_size = 2.0
        self.mt_step = 0.2
        self.st_size = 0.05
        self.lda_dim = 0
        self.prev_mt_feats = numpy.array([])
        self.input_data = {
            'audio': numpy.array([]),
            'audio_initial_message': {},
            'transcripts_initial_message': {},
            'pod_id': None
        }
        self.ip = ip
        self.pod_id = None
        self.fs = 0
        self.timestr = time.strftime("%Y%m%d_%H%M%S")

    def process_transcript(self, input_data, transcript, pod_id):

        speakers, self.prev_mt_feats, class_names, centers  = speakerDiarization(input_data['audio'], self.fs, 0, self.mt_size, self.mt_step, self.st_size, self.lda_dim, False, self.prev_mt_feats )
        #input_data['audio'].clear()
        input_data['audio'] = numpy.array([])
        # NOTE: question detector logic should be implemented here
        output = open("diarization_results_%s.txt" % self.timestr, "w+")
        '''
        websockets.RoutingServerFactory.broadcast('/transcripts_extras/features', json.dumps({
            'transcript_id': transcript['transcript_id'],
            'pod_id': self.ip,
            'speakers': ' '.join(str(s) for s in speakers),
            'window': self.mt_size
        }).encode('utf-8'), False)
        '''
        output.write("----------------Output for pid: %s-----------------\n" % self.ip)
        output.write("Window size: %d\n" % self.mt_size)
        output.write(' '.join(str(s) for s in speakers) + '\n')
        '''
        for t in speakers:
            output.write(' '.join(str(s) for s in t) + '\n')
        #output.write(speakers)
        '''
        output.write("\n")



    def on_transcript(self, payload, is_binary):
        if not is_binary:

            if self.input_data['pod_id'] == None:
                self.input_data['pod_id'] = getId(self.ip)

            transcript = json.loads(payload.decode('utf-8'))
            if 'op' in transcript:
                # op not a transcript so ignore
                return

            if (transcript['pod_id'] == self.input_data['pod_id']):
                # NOTE: we are assuming that the audio data has already been received before processing transcript
                self.process_transcript(self.input_data, transcript, self.input_data['pod_id'])
        else:
            raise Exception('invalid transcript message, expected JSON formatted string')
    def on_transcript_initial_message(self, payload, is_binary):

        if self.input_data['pod_id'] == None:
            self.input_data['pod_id'] = getId(self.ip)

        if not is_binary:
            transcript = json.loads(payload.decode('utf-8'))
            self.input_data['transcripts_initial_message'] = transcript
        else:
            raise Exception('invalid initial message (transcripts), expected JSON formatted string got binary data')
    def on_audio(self, payload, is_binary):
        if is_binary:
            data = numpy.fromstring(payload, numpy.int64)
            x = []
            for chn in list(range(8)):
                x.append(data[chn::8])
            x =  numpy.array(x).T
            #print(x)
            self.input_data['audio'] = numpy.append(self.input_data['audio'], x)
        else:
            payload = payload.decode('utf-8')
            msg = json.loads(payload)
            if (msg['op'] == 'start_session'):
                self.input_data['audio'] = numpy.array([])
    def on_audio_initial_message(self, payload, is_binary):
        if self.input_data['pod_id'] == None:
            self.input_data['pod_id'] = getId(self.ip)

        if not is_binary:
            self.input_data['audio_initial_message'] = json.loads(payload.decode('utf-8'))
            #print(self.input_data['audio_initial_message'])
            sample_rate = self.input_data['audio_initial_message']['audio_format']['sample_rate']
            samples_per_frame = self.input_data['audio_initial_message']['audio_format']['samples_per_frame']
            channels = self.input_data['audio_initial_message']['audio_format']['channels']
            frames_per_second = sample_rate / channels
            self.fs = sample_rate
            max_audio_secs = 120
            self.input_data['audio'] = collections.deque(maxlen=int(max_audio_secs * frames_per_second))
        else:
            raise Exception('invalid initial message (audio), expected JSON formatted string got binary data')

def connect(ip):
    # Limit size of audio queue since it is only cleared when we receive a transcript
    speaker_diarization_proc = SpeakerDiarizationProcessor(ip)
    # Connect to input streams
    connectWS(websockets.RoutingClientFactory(speaker_diarization_proc.on_transcript, speaker_diarization_proc.on_transcript_initial_message, 'ws://127.0.0.1:9000/transcripts'))
    connectWS(websockets.RoutingClientFactory(speaker_diarization_proc.on_audio, speaker_diarization_proc.on_audio_initial_message, 'ws://127.0.0.1:9000/audio/' + ip))

def start_route():
    websockets.RoutingServerFactory.handler('/transcript_extras/features', SpeakerDiarizationService)
