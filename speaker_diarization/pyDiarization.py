from __future__ import print_function
from multiprocessing import Process
from pyAudioAnalysis import audioSegmentation as aS
import numpy
import sklearn.cluster
import scipy
import os
from pyAudioAnalysis import audioFeatureExtraction as aF
from pyAudioAnalysis import audioTrainTest as aT
from pyAudioAnalysis import audioBasicIO
from scipy.spatial import distance
import matplotlib.pyplot as plt
import sklearn.discriminant_analysis
import csv
import os.path
import sklearn
import sklearn.cluster
import hmmlearn.hmm
import pickle as cPickle
import glob
import json
import sys
import pyaudio
import wave
import curses

def speakerDiarization(x, fs, n_speakers, mt_size=2.0, mt_step=0.2,
                       st_win=0.05, lda_dim=35, plot_res=False, prev_mt_feats=numpy.array([])):
    '''
    ARGUMENTS:
        - filename:        the name of the WAV file to be analyzed
        - n_speakers    the number of speakers (clusters) in the recording (<=0 for unknown)
        - mt_size (opt)     mid-term window size
        - mt_step (opt)     mid-term window step
        - st_win  (opt)     short-term window size
        - lda_dim (opt)     LDA dimension (0 for no LDA)
        - plot_res     (opt)   0 for not plotting the results 1 for plottingy
    '''
    #[fs, x] = audioBasicIO.readAudioFile(filename)
    #x = numpy.frombuffer(x, dtype=float)
    #print("The signal is:\n{}\n\nFS is:\n{}\n\n".format(x,fs))
    x = audioBasicIO.stereo2mono(x)
    #data = numpy.fromstring(rawaudio, numpy.int64)
    #x = []
    #for chn in list(range(8)):
     #   x.append(data[chn::8])
    #x =  numpy.array(x).T
    print(x)
    duration = len(x) / fs
    print(duration)
    print(len(x))
    print(fs)
    #utterances = getUtterances()

    [classifier_1, MEAN1, STD1, classNames1, mtWin1, mtStep1, stWin1, stStep1, computeBEAT1] = aT.load_model_knn(os.path.join(os.path.dirname(os.path.realpath(__file__)), "data", "knnSpeakerAll"))
    [classifier_2, MEAN2, STD2, classNames2, mtWin2, mtStep2, stWin2, stStep2, computeBEAT2] = aT.load_model_knn(os.path.join(os.path.dirname(os.path.realpath(__file__)), "data", "knnSpeakerFemaleMale"))
    #print(fs)
    #print(fs*st_win*.5)
    [mt_feats, st_feats, _] = aF.mtFeatureExtraction(x, fs, mt_size * fs,
                                                     mt_step *fs,
                                                     round(fs * st_win),
                                                     round(fs*st_win * 0.5))

    MidTermFeatures2 = numpy.zeros((mt_feats.shape[0] + len(classNames1) +
                                    len(classNames2), mt_feats.shape[1]))

    for i in range(mt_feats.shape[1]):
        cur_f1 = (mt_feats[:, i] - MEAN1) / STD1
        cur_f2 = (mt_feats[:, i] - MEAN2) / STD2
        [res, P1] = aT.classifierWrapper(classifier_1, "knn", cur_f1)
        [res, P2] = aT.classifierWrapper(classifier_2, "knn", cur_f2)
        MidTermFeatures2[0:mt_feats.shape[0], i] = mt_feats[:, i]
        MidTermFeatures2[mt_feats.shape[0]:mt_feats.shape[0]+len(classNames1), i] = P1 + 0.0001
        MidTermFeatures2[mt_feats.shape[0] + len(classNames1)::, i] = P2 + 0.0001

    mt_feats = MidTermFeatures2    # TODO
    iFeaturesSelect = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 41,
                       42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53]

    mt_feats = mt_feats[iFeaturesSelect, :]
    #print(mt_feats.shape)
    #print()
    if(prev_mt_feats.size != 0):
        mt_feats = numpy.concatenate((prev_mt_feats, mt_feats), 1)
    #print(mt_feats.shape)

    (mt_feats_norm, MEAN, STD) = aT.normalizeFeatures([mt_feats.T])
    mt_feats_norm = mt_feats_norm[0].T
    n_wins = mt_feats.shape[1]

    # remove outliers:
    dist_all = numpy.sum(distance.squareform(distance.pdist(mt_feats_norm.T)),
                         axis=0)
    m_dist_all = numpy.mean(dist_all)
    i_non_outliers = numpy.nonzero(dist_all < 1.2 * m_dist_all)[0]

    # TODO: Combine energy threshold for outlier removal:
    #EnergyMin = numpy.min(mt_feats[1,:])
    #EnergyMean = numpy.mean(mt_feats[1,:])
    #Thres = (1.5*EnergyMin + 0.5*EnergyMean) / 2.0
    #i_non_outliers = numpy.nonzero(mt_feats[1,:] > Thres)[0]
    #print i_non_outliers


    mt_feats_norm_or = mt_feats_norm
    #print(mt_feats_norm_or.shape)
    #print()
    #if(prev_mt_feats_norm_or.size != 0):
        #mt_feats_norm_or = numpy.concatenate((prev_mt_feats_norm_or,mt_feats_norm_or), 1)
    #print(mt_feats_norm_or.shape)
    n_wins = mt_feats_norm_or.shape[1]
    perOutLier = (100.0 * (n_wins - i_non_outliers.shape[0])) / n_wins
    mt_feats_norm = mt_feats_norm[:, i_non_outliers]

    # LDA dimensionality reduction:
    if lda_dim > 0:
        #[mt_feats_to_red, _, _] = aF.mtFeatureExtraction(x, fs, mt_size * fs, st_win * fs, round(fs*st_win), round(fs*st_win));
        # extract mid-term features with minimum step:
        mt_win_ratio = int(round(mt_size / st_win))
        mt_step_ratio = int(round(st_win / st_win))
        mt_feats_to_red = []
        num_of_features = len(st_feats)
        num_of_stats = 2
        #for i in range(num_of_stats * num_of_features + 1):
        for i in range(num_of_stats * num_of_features):
            mt_feats_to_red.append([])

        for i in range(num_of_features):        # for each of the short-term features:
            curPos = 0
            N = len(st_feats[i])
            while (curPos < N):
                N1 = curPos
                N2 = curPos + mt_win_ratio
                if N2 > N:
                    N2 = N
                curStFeatures = st_feats[i][N1:N2]
                mt_feats_to_red[i].append(numpy.mean(curStFeatures))
                mt_feats_to_red[i+num_of_features].append(numpy.std(curStFeatures))
                curPos += mt_step_ratio
        mt_feats_to_red = numpy.array(mt_feats_to_red)
        mt_feats_to_red_2 = numpy.zeros((mt_feats_to_red.shape[0] +
                                        len(classNames1) + len(classNames2),
                                         mt_feats_to_red.shape[1]))
        for i in range(mt_feats_to_red.shape[1]):
            cur_f1 = (mt_feats_to_red[:, i] - MEAN1) / STD1
            cur_f2 = (mt_feats_to_red[:, i] - MEAN2) / STD2
            [res, P1] = aT.classifierWrapper(classifier_1, "knn", cur_f1)
            [res, P2] = aT.classifierWrapper(classifier_2, "knn", cur_f2)
            mt_feats_to_red_2[0:mt_feats_to_red.shape[0], i] = mt_feats_to_red[:, i]
            mt_feats_to_red_2[mt_feats_to_red.shape[0]:mt_feats_to_red.shape[0] + len(classNames1), i] = P1 + 0.0001
            mt_feats_to_red_2[mt_feats_to_red.shape[0]+len(classNames1)::, i] = P2 + 0.0001
        mt_feats_to_red = mt_feats_to_red_2
        mt_feats_to_red = mt_feats_to_red[iFeaturesSelect, :]
        #mt_feats_to_red += numpy.random.rand(mt_feats_to_red.shape[0], mt_feats_to_red.shape[1]) * 0.0000010
        (mt_feats_to_red, MEAN, STD) = aT.normalizeFeatures([mt_feats_to_red.T])
        mt_feats_to_red = mt_feats_to_red[0].T
        #dist_all = numpy.sum(distance.squareform(distance.pdist(mt_feats_to_red.T)), axis=0)
        #m_dist_all = numpy.mean(dist_all)
        #iNonOutLiers2 = numpy.nonzero(dist_all < 3.0*m_dist_all)[0]
        #mt_feats_to_red = mt_feats_to_red[:, iNonOutLiers2]
        Labels = numpy.zeros((mt_feats_to_red.shape[1], ));
        LDAstep = 1.0
        LDAstepRatio = LDAstep / st_win
        #print LDAstep, LDAstepRatio
        for i in range(Labels.shape[0]):
            Labels[i] = int(i*st_win/LDAstepRatio);
        clf = sklearn.discriminant_analysis.LinearDiscriminantAnalysis(n_components=lda_dim)
        clf.fit(mt_feats_to_red.T, Labels)
        mt_feats_norm = (clf.transform(mt_feats_norm.T)).T

    #print(mt_feats_norm)
    #print()

    #print(prev_mt_feats_norm)
    #print(len(mt_feats_norm[0]))

    if n_speakers <= 0:
        s_range = range(2, min(len(mt_feats_norm[0]), 10))
    else:
        s_range = [n_speakers]
    clsAll = []
    sil_all = []
    centersAll = []

    #print(mt_feats_norm)

    for iSpeakers in s_range:
        k_means = sklearn.cluster.KMeans(n_clusters=iSpeakers)
        k_means.fit(mt_feats_norm.T)
        cls = k_means.labels_
        means = k_means.cluster_centers_
        #print(means)
        #print(iSpeakers)
        #print("Number of speakers testing: {}".format(iSpeakers))
        #print(cls)

        # Y = distance.squareform(distance.pdist(mt_feats_norm.T))
        clsAll.append(cls)
        centersAll.append(means)
        sil_1 = []; sil_2 = []
        for c in range(iSpeakers):
            # for each speaker (i.e. for each extracted cluster)
            clust_per_cent = numpy.nonzero(cls == c)[0].shape[0] / \
                             float(len(cls))
            if clust_per_cent < 0.020:
                sil_1.append(0.0)
                sil_2.append(0.0)
            else:
                # get subset of feature vectors
                mt_feats_norm_temp = mt_feats_norm[:, cls==c]
                # compute average distance between samples
                # that belong to the cluster (a values)
                Yt = distance.pdist(mt_feats_norm_temp.T)
                sil_1.append(numpy.mean(Yt)*clust_per_cent)
                silBs = []
                for c2 in range(iSpeakers):
                    # compute distances from samples of other clusters
                    if c2 != c:
                        clust_per_cent_2 = numpy.nonzero(cls == c2)[0].shape[0] /\
                                           float(len(cls))
                        MidTermFeaturesNormTemp2 = mt_feats_norm[:, cls == c2]
                        Yt = distance.cdist(mt_feats_norm_temp.T,
                                            MidTermFeaturesNormTemp2.T)
                        silBs.append(numpy.mean(Yt)*(clust_per_cent
                                                     + clust_per_cent_2)/2.0)
                silBs = numpy.array(silBs)
                # ... and keep the minimum value (i.e.
                # the distance from the "nearest" cluster)
                sil_2.append(min(silBs))
        sil_1 = numpy.array(sil_1);
        sil_2 = numpy.array(sil_2);
        sil = []
        for c in range(iSpeakers):
            # for each cluster (speaker) compute silhouette
            sil.append( ( sil_2[c] - sil_1[c]) / (max(sil_2[c],
                                                      sil_1[c]) + 0.00001))
        # keep the AVERAGE SILLOUETTE
        sil_all.append(numpy.mean(sil))

    imax = numpy.argmax(sil_all)
    # optimal number of clusters
    nSpeakersFinal = s_range[imax]

    # generate the final set of cluster labels
    # (important: need to retrieve the outlier windows:
    # this is achieved by giving them the value of their
    # nearest non-outlier window)
    cls = numpy.zeros((mt_feats_norm_or.shape[1],))
    centers = centersAll[imax]
    #print(centers)
    #print(centersAll[imax])
    for i in range(mt_feats_norm_or.shape[1]):
        j = numpy.argmin(numpy.abs(i-i_non_outliers))
        cls[i] = clsAll[imax][j]
    #print(cls)
    #print()
    #if(prev_cls.size != 0):
    #    cls = numpy.concatenate((prev_cls,cls),0)
    #print(cls.shape)
    # Post-process method 1: hmm smoothing
    for i in range(1):
        # hmm training
        #print("HMM: {} - {}".format(mt_feats_norm_or.shape, cls.shape))
        start_prob, transmat, means, cov = \
            aS.trainHMM_computeStatistics(mt_feats_norm_or, cls)
        hmm = hmmlearn.hmm.GaussianHMM(start_prob.shape[0], "diag")
        hmm.startprob_ = start_prob
        hmm.transmat_ = transmat
        hmm.means_ = means; hmm.covars_ = cov
        #sprint(cov)
        cls = hmm.predict(mt_feats_norm_or.T)

    # Post-process method 2: median filtering:
    cls = scipy.signal.medfilt(cls, 13)
    cls = scipy.signal.medfilt(cls, 11)

    sil = sil_all[imax]
    class_names = ["speaker{0:d}".format(c) for c in range(nSpeakersFinal)];


    # load ground-truth if available
    '''
    gt_file = filename.replace('.wav', '.segments')
    # if groundturh exists
    if os.path.isfile(gt_file):
        [seg_start, seg_end, seg_labs] = aS.readSegmentGT(gt_file)
        flags_gt, class_names_gt = aS.segs2flags(seg_start, seg_end, seg_labs, mt_step)

    if plot_res:
        fig = plt.figure()
        if n_speakers > 0:
            ax1 = fig.add_subplot(111)
        else:
            ax1 = fig.add_subplot(211)
        ax1.set_yticks(numpy.array(range(len(class_names))))
        ax1.axis((0, duration, -1, len(class_names)))
        ax1.set_yticklabels(class_names)
        ax1.plot(numpy.array(range(len(cls)))*mt_step+mt_step/2.0, cls)

    if os.path.isfile(gt_file):
        if plot_res:
            ax1.plot(numpy.array(range(len(flags_gt))) *
                     mt_step + mt_step / 2.0, flags_gt, 'r')
        purity_cluster_m, purity_speaker_m = \
            aS.evaluateSpeakerDiarization(cls, flags_gt)
        print("{0:.1f}\t{1:.1f}".format(100 * purity_cluster_m,
                                        100 * purity_speaker_m))
        if plot_res:
            plt.title("Cluster purity: {0:.1f}% - "
                      "Speaker purity: {1:.1f}%".format(100 * purity_cluster_m,
                                                        100 * purity_speaker_m))
    if plot_res:
        plt.xlabel("time (seconds)")
        #print s_range, sil_all
        if n_speakers<=0:
            plt.subplot(212)
            plt.plot(s_range, sil_all)
            plt.xlabel("number of clusters");
            plt.ylabel("average clustering's sillouette");
        plt.show()
    #print(centers)
    '''
    return cls, mt_feats, class_names, centers

'''
def getUtterances():
    with open('data.json', 'r') as f:
        data_dict=json.load(f)

    utterances = []
    for i in range(len(data_dict['results'])):
        utterances = utterances + data_dict['results'][i]['alternatives'][0]['timestamps']
    return(utterances)

#print(utterances[0])

def sample(CHUNK=1024, FORMAT=pyaudio.paInt16, CHANNELS=2, RATE=44100, RECORD_SECONDS=5, WAVE_OUTPUT_FILENAME="output.wav"):
    """PyAudio example: Record a few seconds of audio and save to a WAVE file."""

    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 2
    RATE = 44100
    RECORD_SECONDS = 5
    WAVE_OUTPUT_FILENAME = "output.wav"

    p = pyaudio.PyAudio()

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    print("* recording")

    frames = []

    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("* done recording")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()


def checkExit():
    stdscr = curses.initscr()
    curses.noecho()
    stdscr.keypad(True)
    print("Press q to exit")
    while True:
        c = stdscr.getch()
        if(c ==  ord('q')):
            stdscr.keypad(False)
            curses.echo()
            sys.exit()

p = Process(target = checkExit, args = ())
p.daemon = True
p.start()

class_names = ""
i=0


dir = sys.argv[1]
mt_size = float(sys.argv[2])
mt_step = float(sys.argv[3])
prev_mt_feats = numpy.array([])

while os.path.isfile("{}/chunk{}.wav".format(dir, i)):
    file = "{}/chunk{}.wav".format(dir, i)
    cls, curr_mt_feats, class_names, centers = speakerDiarization(file, 0, mt_size, mt_step, .05, 0, False, prev_mt_feats)
    prev_mt_feats = curr_mt_feats
    i += 1

#print(cls)
[fs, x] = audioBasicIO.readAudioFile("{}.wav".format(dir))
duration = len(x) / fs
fig = plt.figure()
ax1 = fig.add_subplot(111)
ax1.set_yticks(numpy.array(range(len(class_names))))
ax1.axis((0, duration, -1, len(class_names)))
ax1.set_yticklabels(class_names)
ax1.plot(numpy.array(range(len(cls)))*mt_step+mt_step/mt_size, cls)
plt.show()
'''

#print(speakerDiarization("data/diarizationExample.wav",0,1.0,.2,.05,0,False))
#print(aS.speakerDiarization("{}.wav".format(dir) , 0 , 1.0, .2, .05, 0, True))
