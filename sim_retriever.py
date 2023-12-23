import logging
from typing import Tuple
from sim_caculator import SimCaculator


class SimRetriever:
    def __init__(self, sim_caculator: SimCaculator):
        self.sim_caculator = sim_caculator

    def _retrieve_in_file(self, file_sum_obj: dict):
        '''Retrieve the method according to its description and the summary of the class.'''
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
        similarities = self.sim_caculator.calc_similarities(
            self.query, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # select the method with the highest similarity
        self.ret_times += 1
        self.result_path.append(infos[0]['name'])

    def _retrieve_in_dir(self, dir_sum_obj: dict):
        '''Retrieve the method according to its description and the summary of the directory.'''
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
        similarities = self.sim_caculator.calc_similarities(
            self.query, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # select the subdirectory or file with the highest similarity
        infer_id = infos[0]['id']
        file_sum_obj = None
        sub_dir_sum_obj = None
        next_sum_obj = None

        file_sum_obj = next(
            filter(lambda x: x['id'] == infer_id, dir_sum_obj['files']), None)
        sub_dir_sum_obj = next(
            filter(lambda x: x['id'] == infer_id, dir_sum_obj['subdirectories']), None)

        if file_sum_obj is not None:
            next_sum_obj = file_sum_obj
            self._retrieve_in_file(file_sum_obj)
        elif sub_dir_sum_obj is not None:
            next_sum_obj = sub_dir_sum_obj
            self._retrieve_in_dir(sub_dir_sum_obj)

        self.result_path.append(next_sum_obj['name'])
        self.ret_times += 1

    def retrieve(self, query: str, repo_sum_obj: dict, logger: logging.Logger) -> Tuple[bool, dict]:
        '''
            Retrieve the method according to its description and the summary of the entire repo.
            return (is_error: bool, {is_found: bool, path: List[str], ret_times: int}).
        '''
        self.query = query
        self.logger = logger

        self.result_path = []
        self.ret_times = 0

        self._retrieve_in_dir(repo_sum_obj)
        self.result_path.reverse()

        return False, {
            'is_found': True,
            'path': self.result_path,
            'ret_times': self.ret_times,
        }
