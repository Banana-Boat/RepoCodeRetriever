import logging
import time
from typing import List

from constants import LOG_SEPARATOR

from sim_caculator import SimCaculator


class Retriever:
    def __init__(self, logger: logging.Logger, sim_caculator: SimCaculator):
        self.logger = logger

        self.sim_caculator = sim_caculator

        self.result_path = []  # result path, reset every retrieval

    def _retrieve_in_file(self, des: str, file_sum_obj: dict):
        '''
            Retrieve the method according to the description and the summary of the class.
        '''
        # get information list of method
        infos = []
        for method_sum_obj in file_sum_obj['methods']:
            infos.append({
                'id': method_sum_obj['id'],
                'name': method_sum_obj['name'],
                'summary': method_sum_obj['summary'],
            })

        # calculate similarity, and sort infos according to similarity
        summaries = [info['summary'] for info in infos]
        similarities = self.sim_caculator.calc_similarities(des, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # select the method with the highest similarity
        self.result_path.append(infos[0]['name'])

    def _retrieve_in_dir(self, des: str, dir_sum_obj: dict):
        '''
            Retrieve the method according to the description and the summary of the directory.
        '''
        # get information list of subdirectory and file
        infos = []
        for sub_dir_sum_obj in dir_sum_obj['subdirectories']:
            infos.append({
                'id': sub_dir_sum_obj['id'],
                'name': sub_dir_sum_obj['name'],
                'summary': sub_dir_sum_obj['summary'],
            })

        for file_sum_obj in dir_sum_obj['files']:
            infos.append({
                'id': file_sum_obj['id'],
                'name': file_sum_obj['name'],
                'summary': file_sum_obj['summary'],
            })

        # calculate similarity, and sort infos according to similarity
        summaries = [info['summary'] for info in infos]
        similarities = self.sim_caculator.calc_similarities(des, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # select the subdirectory or file with the highest similarity
        infer_id = infos[0]['id']
        file_sum_obj = None
        sub_dir_sum_obj = None
        next_sum_obj = None

        file_sum_obj = next(
            filter(lambda x: x['id'] == infer_id, dir_sum_obj['files']))
        sub_dir_sum_obj = next(
            filter(lambda x: x['id'] == infer_id, dir_sum_obj['subdirectories']))

        if file_sum_obj is not None:
            next_sum_obj = file_sum_obj
            self._retrieve_in_file(des, file_sum_obj)
        elif sub_dir_sum_obj is not None:
            next_sum_obj = sub_dir_sum_obj
            self._retrieve_in_dir(des, sub_dir_sum_obj)

        self.result_path.append(next_sum_obj['name'])

    def retrieve_in_repo(self, des: str, repo_sum_obj: dict) -> List[str]:
        '''
            Retrieve the method according to the description and the summary of the entire repo.
        '''
        start_time = time.time()

        self.result_path = []

        self._retrieve_in_dir(des, repo_sum_obj)

        self.logger.info(f"COMPLETION{LOG_SEPARATOR}")
        self.logger.info(
            f"Retrieval time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

        self.result_path.reverse()
        return self.result_path
