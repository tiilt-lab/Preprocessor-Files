import json
import websockets
import sqlite3 as lite
import os
import websockets

from .respeaker_hi_liwc import populate_dictionary_index_hi, populate_dictionary_index_liwc, process_text #added for feature coding
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

class FeaturesCodingService(websockets.RouteService):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def onOpen(self):
        self.protocol.sendMessage(json.dumps({
            'version': 1.0,
            'type': 'transcript_extras'
        }).encode('utf-8'), False)

class FeaturesCodingProcessor():

    def __init__(self, ip):
        self.hgi_emots, self.hgi_dictionary = populate_dictionary_index_hi()
        self.hgi_emots = ['Positiv','Know', 'Causal','SureLw']
        self.liwc_emots, self.liwc_dictionary = populate_dictionary_index_liwc()
        self.liwc_emots = ['CogMech', 'Assent', 'Conj', 'Insight', 'Certain','I']
        self.input_data = {
            'transcripts_initial_message': {}
        }
        self.ip = ip
        self.pod_id = None

    def on_transcript(self, payload, is_binary):
        if not is_binary:
            if not self.pod_id:
                self.pod_id = getId(self.ip)

            transcript = json.loads(payload.decode('utf-8'))
            if 'op' in transcript:
                # op not a transcript so ignore
                return

            if (transcript['pod_id'] == self.pod_id):
                self.process_transcript(self.input_data, transcript)
        else:
            raise Exception('invalid transcript message, expected JSON formatted string')

    def on_transcript_initial_message(self, payload, is_binary):

        self.pod_id = getId(self.ip)

        if not is_binary:
            transcript = json.loads(payload.decode('utf-8'))
            self.input_data['transcripts_initial_message'] = transcript
        else:
            raise Exception('invalid initial message (transcripts), expected JSON formatted string got binary data')

    def process_transcript(self, input_data, transcript):
        # NOTE: features coding logic should be implemented here
        hgi_count, hgi_emot_dict = process_text(str(transcript['transcript']), self.hgi_dictionary, self.hgi_emots)
        liwc_count, liwc_emot_dict = process_text(str(transcript['transcript']), self.liwc_dictionary, self.liwc_emots)
        emotion_val = 0.0
        analytic_val = 0.0
        collab_quality_val = 0.0
        certainty_val = 0.0
        authenticity_val = 0.0
        if liwc_count > 0:
            emotion_val = 100.0 * max([hgi_emot_dict['Positiv']])/float(liwc_count)
            analytic_val = 100.0 * max([hgi_emot_dict['Causal'], liwc_emot_dict['CogMech'], liwc_emot_dict['Insight']])/float(liwc_count)
            collab_quality_val = 100.0 * max([liwc_emot_dict['Conj'], liwc_emot_dict['Assent']])/float(liwc_count)
            certainty_val = 100.0 * max([hgi_emot_dict['SureLw'],liwc_emot_dict['Certain']])/float(liwc_count)
            authenticity_val = 100.0 * liwc_emot_dict['I']/float(liwc_count)

        websockets.RoutingServerFactory.broadcast('/transcripts_extras/features', json.dumps({
            'transcript_id': transcript['transcript_id'],
            'pod_id': self.pod_id,
            'emotional_tone_value': emotion_val,
            'analytic_thinking_value': analytic_val,
            'clout_value': collab_quality_val,
            'authenticity_value': authenticity_val,
            'certainty_value':certainty_val,
        }).encode('utf-8'), False)

def connect(ip):
    feat_coding_proc = FeaturesCodingProcessor(ip)
    # Connect to input streams
    connectWS(websockets.RoutingClientFactory(
                feat_coding_proc.on_transcript,
                feat_coding_proc.on_transcript_initial_message,
                'ws://127.0.0.1:9000/transcripts'))

def start_route():
    websockets.RoutingServerFactory.handler('/transcripts_extras/features', FeaturesCodingService)
