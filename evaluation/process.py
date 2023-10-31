import json
import os
from tqdm import tqdm

import requests


def download_repos():
    raw_dir = os.path.join(os.getcwd(), 'raw')
    repo_dir = os.path.join(os.getcwd(), 'repo')
    repo_set = set()

    for filename in tqdm(os.listdir(raw_dir)):
        if not filename.endswith('.jsonl'):
            break

        with open(os.path.join(raw_dir, filename), 'r') as jsonl_f:
            for line in jsonl_f:
                obj = json.loads(line)
                if obj['repo'] in repo_set:
                    break

                repo_set.add(obj['repo'])

                # convert url
                # https://github.com/soimort/you-get/blob/b746ac01c9f39de94cac2d56f665285b0523b974/src/you_get/extractors/youtube.py#L135-L143
                # https://github.com/soimort/you-get/archive/b746ac01c9f39de94cac2d56f665285b0523b974.zip
                url_list = obj['url'].split('/')
                blob_idx = url_list.index('blob')
                url_list[blob_idx] = 'archive'
                url = '/'.join(url_list[:blob_idx + 2]) + '.zip'

                # download
                response = requests.get(url)
                with open(os.path.join(repo_dir, 'temp.zip'), 'wb') as zip_f:
                    zip_f.write(response.content)

                # unzip and remove
                os.system('unzip -q -d {} {}'.format(repo_dir,
                          os.path.join(repo_dir, 'temp.zip')))
                os.system('rm -rf {}'.format(os.path.join(repo_dir, 'temp.zip')))


if __name__ == "__main__":
    download_repos()
