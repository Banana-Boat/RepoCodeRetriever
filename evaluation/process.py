import json
import os
import re
from tqdm import tqdm

import requests


def get_repos(input_file_path, output_file_path):
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
        json.dump(respos, out_f, indent=4)


def download_repos(repo_file_path, repo_dir_path, start_idx=0):
    with open(repo_file_path, 'r') as json_f:
        repos = json.load(json_f)

        for i, repo in enumerate(tqdm(repos[start_idx:])):
            try:
                response = requests.get(repo['zip_url'])
                with open(os.path.join(repo_dir_path, 'temp.zip'), 'wb') as zip_f:
                    zip_f.write(response.content)

                # unzip & remove temp.zip
                os.system(
                    'unzip -q -d {} {}'.format(repo_dir_path, os.path.join(repo_dir_path, 'temp.zip')))
                os.system(
                    'rm -rf {}'.format(os.path.join(repo_dir_path, 'temp.zip')))
            except Exception as e:
                print(e)
                print('Stop at {}'.format(i + start_idx))
                return


def filter_data(raw_dir_path, output_file_path):
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
                    if len(filtered_repo_data) >= 18:
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
                if len(query) < 50 or len(query) > 100:
                    continue

                # ignore duplicate query in one repo
                if query in [item['query'] for item in filtered_repo_data]:
                    continue

                # get line num in url
                # https://github.com/soimort/you-get/blob/b746ac01c9f39de94cac2d56f665285b0523b974/src/you_get/extractors/youtube.py#L135-L143
                start_line_num = int(obj['url'].split('#')[
                                     1].split('-')[0][1:])

                filtered_repo_data.append({
                    'repo': obj['repo'],
                    'sha': obj['sha'],
                    'query': query,
                    'func_name': obj['func_name'],
                    'start_line_num': start_line_num,
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


if __name__ == "__main__":
    raw_dir_path = os.path.join(os.getcwd(), 'raw')
    repo_dir_path = os.path.join(os.getcwd(), 'repo')
    filtered_dir_path = os.path.join(os.getcwd(), 'filtered')

    data_file_path = os.path.join(filtered_dir_path, 'data.jsonl')
    repo_file_path = os.path.join(filtered_dir_path, 'repos.json')

    filter_data(raw_dir_path, data_file_path)

    # get_repos(data_file_path, repo_file_path)

    # download_repos(repo_file_path, repo_dir_path, 0)
