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

                if obj['repo'] + obj['sha'] != cur_repo:
                    # limitation for data count in one repo
                    if len(filtered_repo_data) >= 20:
                        res.extend(filtered_repo_data)
                        repo_set.add(cur_repo)

                    filtered_repo_data = []
                    cur_repo = obj['repo'] + obj['sha']
                    cur_repo_path_set.clear()

                # limitation for same path in one repo
                if obj['path'] in cur_repo_path_set:
                    continue

                # limitation for directory hierarchy in path field
                if obj['path'].count('/') < 3 or obj['path'].count('/') > 8:
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
                if len(query) < 60 or len(query) > 120:
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


def get_repo(input_file_path, output_file_path):
    repo_set = set()
    respos = []

    with open(input_file_path, 'r') as input_f:
        for line in input_f:
            obj = json.loads(line)

            if obj['repo'] + obj['sha'] in repo_set:
                continue

            repo_set.add(obj['repo'] + obj['sha'])

            # convert url
            # https://github.com/soimort/you-get/blob/b746ac01c9f39de94cac2d56f665285b0523b974/src/you_get/extractors/youtube.py#L135-L143
            # https://github.com/soimort/you-get/archive/b746ac01c9f39de94cac2d56f665285b0523b974.zip
            url_list = obj['url'].split('/')
            blob_idx = url_list.index('blob')
            url_list[blob_idx] = 'archive'
            zip_url = '/'.join(url_list[:blob_idx + 2]) + '.zip'

            respos.append({
                'repo': obj['repo'],
                'sha': obj['sha'],
                'zip_url': zip_url,
            })

    with open(output_file_path, 'w') as out_f:
        for obj in respos:
            json.dump(obj, out_f)
            out_f.write('\n')


def get_repo_info(repo_name: str):
    for _ in range(2):
        try:
            res = requests.get(
                f"https://api.github.com/repos/{repo_name}")

            if res.status_code != 200:
                print(res.json())
                sleep(random.randint(5, 15))
                continue

            return res.json()
        except Exception as e:
            print(e)
            sleep(random.randint(5, 15))
            continue

    return None


def filter_repo1(repo_file_path, output_file_path, start_idx=0):
    respos = []

    with open(repo_file_path, 'r') as input_f:
        for i, line in enumerate(tqdm(input_f.readlines()[start_idx:])):
            repo = json.loads(line)

            # get repo info
            repo_info = get_repo_info(repo['repo'])
            if repo_info is None:
                print(f'Stop at {i + start_idx}')
                break

            # limitation for star count
            if repo_info['stargazers_count'] < 100:
                continue

            # limitation for size
            if repo_info['size'] > 10000:
                continue

            respos.append({
                'repo': repo['repo'],
                'sha': repo['sha'],
                'zip_url': repo['zip_url'],
                'star': repo_info['stargazers_count'],
                'size': repo_info['size']
            })

    with open(output_file_path, 'a') as out_f:
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
    with open(repo_file_path, 'r') as json_f:
        repos = json_f.readlines()

        for i, repo in enumerate(tqdm(repos[start_idx:])):
            repo_obj = json.loads(repo)
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
    repo1_file_path = os.path.join(filtered_dir_path, 'repo1.jsonl')
    repo2_file_path = os.path.join(filtered_dir_path, 'repo2.jsonl')
    data2_file_path = os.path.join(filtered_dir_path, 'data2.jsonl')

    # filter_data1(raw_dir_path, data1_file_path)

    # get_repo(data1_file_path, repo1_file_path)

    # filter_repo1(repo1_file_path, repo2_file_path, 0)

    filter_data2(repo2_file_path, data1_file_path, data2_file_path)

    # download_repos(repo2_file_path, repo_dir_path, 0)
