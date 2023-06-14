import os, re
import errno
import random
import urllib.request as urllib
import numpy as np
from scipy.io import loadmat
from sklearn.utils import shuffle
# ok


def fliter_key(keys):
    fkeys = []
    for key in keys:
        matchObj = re.match(r'(.*)FE_time', key, re.M | re.I)
        if matchObj:
            fkeys.append(matchObj.group(1))
    if (len(fkeys) > 1):
        print(keys)
    return fkeys[0] + 'DE_time', fkeys[0] + 'FE_time'


exps_idx = {
    '12DriveEndFault': 0,
    '12FanEndFault': 9,
    '48DriveEndFault': 0
}

faults_idx = {
    'Normal': 0,
    '0.007-Ball': 1,
    '0.014-Ball': 2,
    '0.021-Ball': 3,
    '0.007-InnerRace': 4,
    '0.014-InnerRace': 5,
    '0.021-InnerRace': 6,
    '0.007-OuterRace6': 7,
    '0.014-OuterRace6': 8,
    '0.021-OuterRace6': 9,
    #     '0.007-OuterRace3': 10,
    #     '0.014-OuterRace3': 11,
    #     '0.021-OuterRace3': 12,
    #     '0.007-OuterRace12': 13,
    #     '0.014-OuterRace12': 14,
    #     '0.021-OuterRace12': 15,
}


def get_class(exp, fault):
    if fault == 'Normal':
        return 0
    return exps_idx[exp] + faults_idx[fault]


class CWRU:
    def __init__(self, exps, rpms, length):
        for exp in exps:
            if exp not in ('12DriveEndFault', '12FanEndFault', '48DriveEndFault'):
                print("wrong experiment name: {}".format(exp))
                return
        for rpm in rpms:
            if rpm not in ('1797', '1772', '1750', '1730'):  # 对应0、1、2、3hp
                print("wrong rpm value: {}".format(rpm))
                return
        # root directory of all data 所有数据的根目录
        rdir = os.path.join('Datasets/CWRU')
        print(rdir, exp, rpm)

        fmeta = os.path.join(os.path.dirname('__file__'), 'metadata.txt')
        # all_lines = open(fmeta).readlines()
        all_lines = open(fmeta).readlines()
        lines = []
        for line in all_lines:
            l = line.split()
            if (l[0] in exps or l[0] == 'NormalBaseline') and l[1] in rpms:
                if 'Normal' in l[2] or '0.007' in l[2] or '0.014' in l[2] or '0.021' in l[2]:
                    if faults_idx.get(l[2], -1) != -1:
                        lines.append(l)

        self.length = length  # sequence length  序列长度2048
        lines = sorted(lines, key=lambda line: get_class(line[0], line[2]))
        self._load_and_slice_data(rdir, lines)
        # shuffle training and test arrays 打乱顺序
        self._shuffle()
        self.all_labels = tuple(((line[0] + line[2]), get_class(line[0], line[2])) for line in lines)
        self.classes = sorted(list(set(self.all_labels)), key=lambda label: label[1])
        self.nclasses = len(self.classes)  # number of classes

    def _mkdir(self, path):
        try:
            os.makedirs(path)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                print("can't create directory '{}''".format(path))
                exit(1)

    def _download(self, fpath, link):
        print(link + " Downloading to: '{}'".format(fpath))
        urllib.urlretrieve(link, fpath)

    def _load_and_slice_data(self, rdir, infos):  # infos 即 lines 即 metadata文件中的一行
        self.X_train = np.zeros((0, self.length, 2))
        self.X_test = np.zeros((0, self.length, 2))
        self.y_train = []
        self.y_test = []
        train_cuts = list(range(0, 60000, 80))[:660]  # 660表示个数
        test_cuts = list(range(60000, 120000, self.length))[:25]  # 25表示个数
        for idx, info in enumerate(infos):
            # enumerate()枚举函数用于将一个可遍历的数据对象组合为一个索引序列，同时列出数据和数据下标

            # directory of this file 这个文件的目录
            fdir = os.path.join(rdir, info[0], info[1])
            self._mkdir(fdir)
            fpath = os.path.join(fdir, info[2] + '.mat')
            # print(idx, fpath)
            print('idx：', idx)
            print('fpath：', fpath)
            
            if not os.path.exists(fpath):
                self._download(fpath, info[3].rstrip('\n'))

            mat_dict = loadmat(fpath)
            key1, key2 = fliter_key(mat_dict.keys())  # key1=X121_DE_time ; key2=X121_FE_time
            time_series = np.hstack((mat_dict[key1], mat_dict[key2]))  # 这里的 time-series 包括DE FE两种数据
            idx_last = -(time_series.shape[0] % self.length)  # 121556 % 2048 = 724

            print('time_series.shape:', time_series.shape)

            clips = np.zeros((0, 2))
            for cut in shuffle(train_cuts):  # train_cuts样本个数：660（间隔80），先打乱再遍历
                clips = np.vstack((clips, time_series[cut:cut + self.length]))  # 将间隔80且长度为2048的数据堆叠起来
            clips = clips.reshape(-1, self.length, 2)  # reshape成（660，2048，2）
            self.X_train = np.vstack((self.X_train, clips))  # 添加到 X_train 训练集中

            clips = np.zeros((0, 2))
            for cut in shuffle(test_cuts):
                clips = np.vstack((clips, time_series[cut:cut + self.length]))  # 将无间隔且长度为2048的数据堆叠起来
            clips = clips.reshape(-1, self.length, 2)  # reshape成（25，2048，2）
            self.X_test = np.vstack((self.X_test, clips))

            self.y_train += [get_class(info[0], info[2])] * 660  # 设置对应标签
            self.y_test += [get_class(info[0], info[2])] * 25

        self.X_train.reshape(-1, self.length, 2)
        self.X_test.reshape(-1, self.length, 2)

    def _shuffle(self):
        # shuffle training samples
        index = list(range(self.X_train.shape[0]))
        random.Random(0).shuffle(index)
        self.X_train = self.X_train[index]
        self.y_train = np.array(tuple(self.y_train[i] for i in index))

        # shuffle test samples
        index = list(range(self.X_test.shape[0]))
        random.Random(0).shuffle(index)
        self.X_test = self.X_test[index]
        self.y_test = np.array(tuple(self.y_test[i] for i in index))
