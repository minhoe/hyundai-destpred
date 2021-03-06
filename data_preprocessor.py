import codecs
from datetime import date
from itertools import product
import json
import os
import pickle

import numpy as np
import pandas as pd
from tqdm import tqdm

from log import log
from utils import get_pkl_file_name, convert_str_to_time, maybe_exist

DATA_DIR = './data'
HOLIDAY_JSON_FNAME = 'kor_event_days.json'
INPUT_DATA_EXT = '.csv'
OUTPUT_DATA_EXT = '.p'


def global_latitude_convertor(x):
    if abs(x) > 500:
        return (x + 600) / (-19)
    else:
        return x - 36


def global_longitude_convertor(y):
    if abs(y) > 500:
        return (y - 660) / (5)
    else:
        return y - 128


class MetaHandler(object):
    def __init__(self, event_data_fname):
        self.holiday_date_set = self._load_holiday_set(event_data_fname)

    def _load_holiday_set(self, fname):
        with codecs.open(fname, 'rb', encoding='utf-8') as fp:
            lines = fp.read()
        event_days = json.loads(lines)['results']

        def _date_from_day_dict(day_dict):
            year, month, day = int(day_dict['year']), int(day_dict['month']), int(day_dict['day'])
            return date(year, month, day)

        return set(  # h: 법정공휴일, i: 대체 공휴일
            _date_from_day_dict(day) for day in event_days if day['type'] in ['h', 'i'])

    def _event_chk(self, start_dt):
        return int(start_dt.date() in self.holiday_date_set)

    def _hour_chk(self, start_dt):
        return start_dt.hour

    def _week_chk(self, start_dt):
        return start_dt.weekday()

    def _week_num_chk(self, start_dt):
        # Monday : 0 ~ Sunday : 6
        return start_dt.isocalendar()[1]

    def convert_to_meta(self, start_dt):
        """
        input: start_dt ; 2006-01-10 13:56:16
        output: meta data list [공휴일, 요일, 시간대, 주차]
        """
        start_dt = convert_str_to_time(start_dt)
        # print(start_dt)

        return [self._event_chk(start_dt), self._week_num_chk(start_dt),
                self._hour_chk(start_dt), self._week_chk(start_dt)]


class Path(object):
    def __init__(self, car_id, start_dt):
        self.car_id = car_id
        self.start_dt = start_dt
        self.xy_list = []
        self.link_id_list = []

    def add_point(self, x, y, link_id):
        self.xy_list.append([x, y])
        self.link_id_list.append(link_id)

    def get_partial_path_and_short_term_dest(self,
                                             proportion_or_minute,
                                             short_term_pred_min=5):
        path_length = len(self.xy_list)
        if proportion_or_minute < 1: # proportion
            partial_path_length = int(path_length * proportion_or_minute)
        else:
            partial_path_length = proportion_or_minute * 2

        # "0" stands for the final destination
        if short_term_pred_min == 0:
            short_term_dest_idx = -1
            is_valid_dest = partial_path_length < path_length
        else:
            short_term_dest_idx = partial_path_length + short_term_pred_min * 2
            is_valid_dest = short_term_dest_idx < path_length

        if is_valid_dest:
            partial_path = np.array(
                self.xy_list[:partial_path_length])
            short_term_dest = np.array(
                self.xy_list[short_term_dest_idx])
            return partial_path, short_term_dest
        else:
            return None

    def get_meta_feature(self, meta_handler):
        return meta_handler.convert_to_meta(self.start_dt)


class DataPreprocessor(object):
    def __init__(self, to_dir):
        self.from_dir = DATA_DIR
        self.to_dir = to_dir
        maybe_exist(self.to_dir)
        self._meta_handler = MetaHandler(HOLIDAY_JSON_FNAME)

    def _load_and_parse_data(self):
        header = ['car_id', 'start_dt', 'seq_id', 'x', 'y', 'link_id']
        df = pd.read_csv(self.from_path, header=None,
                         delimiter=',', names=header, low_memory=False,
                         dtype={'link_id': str})

        # print("Use {} data for preprocessing.".format(self.data_num))
        paths_by_car = dict()

        prev_car_id, prev_start_dt = '', 0 # cnt_path = 0
        for i, row in enumerate(df.itertuples()):
            # filter
            if len(row) < 6 + 1:  # column_size + index
                print('Pass the {}-th row : '.format(i), row)
                continue

            is_new_car = prev_car_id != row.car_id
            is_new_path = prev_start_dt != row.start_dt

            # if self.data_num != 'all':
            #     is_cnt_path_limit = cnt_path == self.data_num
            #     if is_cnt_path_limit:
            #         if not is_new_car:
            #             prev_car_id, prev_start_dt = row.car_id, row.start_dt
            #             continue
            #         cnt_path = 0

            if is_new_car:
                paths_by_car[row.car_id] = list()
            if is_new_path:
                new_path = Path(row.car_id, row.start_dt)
                paths_by_car[row.car_id].append(new_path)
                # cnt_path += 1

            this_path = paths_by_car[row.car_id][-1]
            # scaling x and y to the original scale of latitude and longitude system
            x = global_latitude_convertor(row.x)
            y = global_longitude_convertor(row.y)
            this_path.add_point(x, y, row.link_id)

            prev_car_id, prev_start_dt = row.car_id, row.start_dt

            progress_msg = '\r---Progress...{:10}/{}, num_cars={:3}'
            print(progress_msg.format(i + 1, df.shape[0], len(paths_by_car)),
                  end='', flush=True)

        print('')
        return paths_by_car

    def process_and_save(self, data_fname):

        print('Start data preprocessing.')
        self.from_path = os.path.join(self.from_dir, data_fname)
        self.pkl_fname = data_fname.replace(INPUT_DATA_EXT, OUTPUT_DATA_EXT)

        # load data parsing results
        tmp_pkl_file = os.path.join(self.to_dir, self.pkl_fname)
        print('Check the existence of {} ...'.format(tmp_pkl_file))
        if not os.path.exists(tmp_pkl_file):
            print('Reading and parsing raw data ...')
            paths_by_car = self._load_and_parse_data()
            pickle.dump(paths_by_car, open(tmp_pkl_file, 'wb'))
            print('Saved to temp pkl file.')
        else:
            print('Use existing pkl file that already parsed.')
            paths_by_car = pickle.load(open(tmp_pkl_file, 'rb'))

        minute_or_proportion_list = [x/50 for x in range(1, 50)] # [0.2, 0.4, 0.6, 0.8]
        data_limit_list = ['all'] # 100, 200, 400, 800, 
        short_term_pred_min_list = [5]  # 0 for final destination

        # preprocess and save
        for car_id, paths in tqdm(paths_by_car.items()):
            car_id = 'KMH' if car_id == 'KMHFR412BGA011216' else car_id

            # delete the initial point
            for path in paths:
                path.xy_list.pop(0)

            # exclude too short path
            paths = [path for path in paths if len(path.xy_list) >= 10]

            for prop_or_min, dest_term, data_limit in product(minute_or_proportion_list,
                                                              short_term_pred_min_list,
                                                              data_limit_list):
                # data to save
                full_path_list, path_list, meta_list, dest_list, dt_list = [], [], [], [], []

                for path in paths:
                    result = path.get_partial_path_and_short_term_dest(prop_or_min, dest_term)

                    if result is not None:
                        partial_path, short_term_dest = result
                        meta_feature = path.get_meta_feature(self._meta_handler)

                        full_path_list.append(np.array(path.xy_list))
                        path_list.append(partial_path)
                        meta_list.append(meta_feature)
                        dest_list.append(short_term_dest)
                        dt_list.append(path.start_dt)
                        # print(car_id, proportion, dest_term)
                        # print(path.xy_list, partial_path, short_term_dest)

                    if data_limit != 'all' and len(path_list) == data_limit:
                        break

                data_dict = dict(
                    full_path=full_path_list,
                    path=path_list,
                    meta=meta_list,
                    dest=dest_list,
                    dt=dt_list,
                )

                # save the results
                fname = get_pkl_file_name(car_id, prop_or_min, dest_term)
                pickle.dump(data_dict, open(os.path.join(self.to_dir, fname), 'wb'))