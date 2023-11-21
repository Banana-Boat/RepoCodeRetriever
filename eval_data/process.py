import json
import os
import random
import re
from time import sleep
from tqdm import tqdm

import requests


def filter_data1(raw_dir_path, output_file_path):
    res = []
    filtered_repo_data = []  # list contains filtered data in one repo
    cur_repo = ''
    cur_repo_path_set = set()  # use to ignore same path data in one repo
    repo_set = set()  # use to calculate repo count, there has discontinuous data in one repo
    raw_data_count = 0

    for filename in tqdm(os.listdir(raw_dir_path)):
        if not filename.endswith('.jsonl'):
            continue

        with open(os.path.join(raw_dir_path, filename), 'r') as jsonl_f:
            for line in jsonl_f:
                raw_data_count += 1
                obj = json.loads(line)

                # exclude repos not open source this time
                if obj['repo'] == 'streamsets/datacollector':
                    continue

                if obj['repo'] + obj['sha'] != cur_repo:
                    # limitation for data count in one repo
                    if len(filtered_repo_data) >= 50:
                        res.extend(filtered_repo_data)
                        repo_set.add(cur_repo)

                    filtered_repo_data = []
                    cur_repo = obj['repo'] + obj['sha']
                    cur_repo_path_set.clear()

                # limitation for same path in one repo
                if obj['path'] in cur_repo_path_set:
                    continue

                # limitation for directory hierarchy in path field
                if obj['path'].count('/') < 3 or obj['path'].count('/') > 10:
                    continue

                # limitation for query's token count in docstring_tokens field
                if len(obj['docstring_tokens']) < 10:
                    continue

                # limitation for content of query in docstring field
                if not obj['docstring'].isascii():
                    continue
                if "TODO:" in obj['docstring'] or \
                    "NOTE:" in obj['docstring'] or \
                    "/*" in obj['docstring'] or \
                    "(non-Javadoc)" in obj['docstring'] or \
                    "https://" in obj['docstring'] or \
                    "http://" in obj['docstring'] or \
                    re.search(r'<img[^>]*>', obj['docstring']) or \
                        re.search(r'<a[^>]*>', obj['docstring']):
                    continue

                # handle content of query in docstring field
                query = obj['docstring']
                query = re.sub(r'<[^>]*>', '', query)
                query = re.sub(r'\{@link([^\}]*)\}', r'\1', query)
                query = re.sub(r'\{@code([^\}]*)\}', r'\1', query)
                query = re.sub(r'$\{([^\}]*)\}', r'\1', query)
                query = re.sub(r'@.*', '', query)
                query = re.sub(r'\..*', '.', query)
                query = query.replace('\n', ' ')
                query = re.sub(r'\s+', ' ', query)
                query = query.strip()

                # ignore query which is too short or too long
                if len(query) < 50 or len(query) > 150:
                    continue

                # ignore duplicate query in one repo
                if query in [item['query'] for item in filtered_repo_data]:
                    continue

                filtered_repo_data.append({
                    'repo': obj['repo'],
                    'sha': obj['sha'],
                    'query': query,
                    'func_name': obj['func_name'],
                    'path': obj['path'],
                    'url': obj['url'],
                })

                cur_repo_path_set.add(obj['path'])

    print('Filtered data count: {}\nRatio: {}\nRepo count: {}'.format(
        len(res), len(res) / raw_data_count, len(repo_set)))

    with open(output_file_path, 'w') as out_f:
        for obj in res:
            json.dump(obj, out_f)
            out_f.write('\n')


def get_repo_info_by_api(repo_name: str):
    for _ in range(2):
        try:
            res = requests.get(
                f"https://api.github.com/repos/{repo_name}")

            if res.status_code != 200:
                raise Exception(
                    f"Status code: {res.status_code}, {res.json()}")

            return res.json()
        except Exception as e:
            print(f'Error: {repo_name}')
            print(e)
            sleep(random.randint(5, 15))
            continue

    return None


def get_repo_infos(data_file_path: str, output_file_path: str, start_idx=0):
    repo_set = set()

    with open(data_file_path, 'r') as f_jsonl, open(output_file_path, 'a') as f_out:
        repo_objs = [json.loads(line) for line in f_jsonl]
        for idx, repo_obj in enumerate(tqdm(repo_objs[start_idx:])):
            if repo_obj['repo'] in repo_set:
                continue
            repo_set.add(repo_obj['repo'])

            repo_info = get_repo_info_by_api(repo_obj['repo'])
            if repo_info is None:
                print(f'Stop at {idx + start_idx}')
                return

            json.dump(repo_info, f_out)
            f_out.write('\n')


def filter_repo1(data_file_path, repo_file_path, output_file_path):
    respos = []
    repo_set = set()

    with open(data_file_path, 'r') as f_data, open(repo_file_path, 'r') as f_repo_info:
        datas = [json.loads(line) for line in f_data]
        repo_infos = [json.loads(line) for line in f_repo_info]

        for data in tqdm(datas):
            if data['repo'] in repo_set:
                continue
            repo_set.add(data['repo'])

            # get repo info
            repo_info = next(
                filter(lambda x: x['name'] == data['repo'].split('/')[-1], repo_infos), None)
            if repo_info is None:
                repo_info = get_repo_info_by_api(data['repo'])
                if repo_info is None:
                    print(f'Cannot get repo info: {data["repo"]}')
                    return

            # limitation for star count
            if repo_info['stargazers_count'] < 50:
                continue

            # limitation for size
            if repo_info['size'] > 10000:
                continue

            # cancat zip url
            # https://github.com/soimort/you-get/blob/b746ac01c9f39de94cac2d56f665285b0523b974/src/you_get/extractors/youtube.py#L135-L143
            # https://github.com/soimort/you-get/archive/b746ac01c9f39de94cac2d56f665285b0523b974.zip
            url_list = data['url'].split('/')
            blob_idx = url_list.index('blob')
            url_list[blob_idx] = 'archive'
            zip_url = '/'.join(url_list[:blob_idx + 2]) + '.zip'

            respos.append({
                'repo': data['repo'],
                'sha': data['sha'],
                'zip_url': zip_url,
                'star': repo_info['stargazers_count'],
                'size': repo_info['size']
            })

    print(f'Filtered repo count: {len(respos)}')

    with open(output_file_path, 'w') as out_f:
        for obj in respos:
            json.dump(obj, out_f)
            out_f.write('\n')


def filter_data2(repo_file_path, data_file_path, output_file_path):
    res = []
    repo_set = set()

    with open(repo_file_path, 'r') as repo_f:
        for line in repo_f:
            repo_set.add(json.loads(line)['repo'])

    idx = 0
    with open(data_file_path, 'r') as data_f:
        for line in data_f:
            obj = json.loads(line)

            if obj['repo'] not in repo_set:
                continue

            obj['idx'] = idx
            idx += 1
            res.append(obj)

    print(f'Filtered data count: {len(res)}')

    with open(output_file_path, 'w') as out_f:
        for obj in res:
            json.dump(obj, out_f)
            out_f.write('\n')


def download_repos(repo_file_path, repo_dir_path, start_idx=0):
    repo_dir_name_list = os.listdir(repo_dir_path)

    with open(repo_file_path, 'r') as json_f:
        repo_objs = [json.loads(line) for line in json_f]

        for i, repo_obj in enumerate(tqdm(repo_objs[start_idx:])):
            # if repo is already downloaded, skip it
            repo_dir_name = f"{repo_obj['repo'].split('/')[-1]}-{repo_obj['sha']}"
            if repo_dir_name in repo_dir_name_list:
                continue

            try:
                response = requests.get(repo_obj['zip_url'])
                with open(os.path.join(repo_dir_path, 'temp.zip'), 'wb') as zip_f:
                    zip_f.write(response.content)

                # unzip & remove temp.zip
                os.system(
                    'unzip -q -d {} {}'.format(repo_dir_path, os.path.join(repo_dir_path, 'temp.zip')))
                os.system(
                    'rm -rf {}'.format(os.path.join(repo_dir_path, 'temp.zip')))
            except Exception as e:
                print(e)
                print(f'Stop at {i + start_idx}')
                return


if __name__ == "__main__":
    raw_dir_path = os.path.join(os.getcwd(), 'raw')
    repo_dir_path = os.path.join(os.getcwd(), 'repo')
    filtered_dir_path = os.path.join(os.getcwd(), 'filtered')

    data1_file_path = os.path.join(filtered_dir_path, 'data1.jsonl')
    repo_info_file_path = os.path.join(filtered_dir_path, 'repo_info.jsonl')
    repo1_file_path = os.path.join(filtered_dir_path, 'repo1.jsonl')
    data2_file_path = os.path.join(filtered_dir_path, 'data2.jsonl')

    # filter_data1(raw_dir_path, data1_file_path)

    # get_repo_infos(data1_file_path, repo_info_file_path, 0)

    # filter_repo1(data1_file_path, repo_info_file_path, repo1_file_path)

    # filter_data2(repo1_file_path, data1_file_path, data2_file_path)

    download_repos(repo1_file_path, repo_dir_path, 0)
