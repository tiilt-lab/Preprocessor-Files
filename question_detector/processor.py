import json
import collections
import sqlite3 as lite
import re
import os
import websockets

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


class QuestionDetectorService(websockets.RouteService):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def onOpen(self):
        self.protocol.sendMessage(json.dumps({
            'version': 1.0,
            'type': 'transcripts_extras'
        }).encode('utf-8'), False)

def process_transcript(input_data, transcript, pod_id):
    if (input_data['transcripts_initial_message']['asr'] == "google-cloud-speech"):
        question = None
        try:
            question = re.search(r'\w[?]$', transcript['words'][-1]['word'])
        except:
            # there are no words in the transcript
            question = None
        websockets.RoutingServerFactory.broadcast('/transcripts_extras/question', json.dumps({
            'transcript_id': transcript['transcript_id'],
            'pod_id': pod_id,
            'question': (question is not None)
        }).encode('utf-8'), False)
    else:
        # NOTE: question detector logic should be implemented here
        websockets.RoutingServerFactory.broadcast('/transcripts_extras/question', json.dumps({
            'transcript_id': transcript['transcript_id'],
            'pod_id': pod_id,
            'question': False
        }).encode('utf-8'), False)
    input_data['audio'].clear()

def connect(ip):
    # Limit size of audio queue since it is only cleared when we receive a transcript
    input_data = {
        'audio': None,
        'audio_initial_message': {},
        'transcripts_initial_message': {},
        'pod_id': None
    }

    def on_transcript(payload, is_binary):
        if not is_binary:

            if input_data['pod_id'] == None:
                input_data['pod_id'] = getId(ip)

            transcript = json.loads(payload.decode('utf-8'))
            if 'op' in transcript:
                # op not a transcript so ignore
                return

            if (transcript['pod_id'] == input_data['pod_id']):
                # NOTE: we are assuming that the audio data has already been received before processing transcript
                process_transcript(input_data, transcript, input_data['pod_id'])
        else:
            raise Exception('invalid transcript message, expected JSON formatted string')
    def on_transcript_initial_message(payload, is_binary):

        if input_data['pod_id'] == None:
            input_data['pod_id'] = getId(ip)

        if not is_binary:
            transcript = json.loads(payload.decode('utf-8'))
            input_data['transcripts_initial_message'] = transcript
        else:
            raise Exception('invalid initial message (transcripts), expected JSON formatted string got binary data')
    def on_audio(payload, is_binary):
        if is_binary:
            input_data['audio'].append(payload)
        else:
            payload = payload.decode('utf-8')
            msg = json.loads(payload)
            if (msg['op'] == 'start_session'):
                input_data['audio'].clear()
    def on_audio_initial_message(payload, is_binary):
        if input_data['pod_id'] == None:
            input_data['pod_id'] = getId(ip)

        if not is_binary:
            input_data['audio_initial_message'] = json.loads(payload.decode('utf-8'))
            sample_rate = input_data['audio_initial_message']['audio_format']['sample_rate']
            samples_per_frame = input_data['audio_initial_message']['audio_format']['samples_per_frame']
            frames_per_second = sample_rate / samples_per_frame
            max_audio_secs = 120
            input_data['audio'] = collections.deque(maxlen=int(max_audio_secs * frames_per_second))
        else:
            raise Exception('invalid initial message (audio), expected JSON formatted string got binary data')

    # Connect to input streams
    connectWS(websockets.RoutingClientFactory(on_transcript, on_transcript_initial_message, 'ws://127.0.0.1:9000/transcripts'))
    connectWS(websockets.RoutingClientFactory(on_audio, on_audio_initial_message, 'ws://127.0.0.1:9000/audio/' + ip))

def start_route():
    websockets.RoutingServerFactory.handler('/transcripts_extras/question', QuestionDetectorService)
