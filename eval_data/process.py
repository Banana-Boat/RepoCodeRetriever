import json
import os
import random
import re
from time import sleep
from tqdm import tqdm

import requests


def parse_repo(repo_path, output_path, log_path) -> int:
    return os.system(
        f"java -jar ../java-repo-parser.jar -r={repo_path} -o={output_path} -l={log_path}")


exclude_repo_set = set([
    'streamsets/datacollector',
    'DataSketches/sketches-core',
    'xiancloud/xian',
    'apache/incubator-gobblin',
    'box/box-java-sdk',
    'alibaba/jstorm',
    'line/armeria',
    'jenkinsci/jenkins',
    'aws/aws-sdk-java',
    'Whiley/WhileyCompilerCollection',
    'javalite/activejdbc',
    'apache/incubator-zipkin',
    'banq/jdonframework',
    'sshtools/j2ssh-maverick',
    'BranchMetrics/android-branch-deep-linking',
    'OpenLiberty/open-liberty',
    'alkacon/opencms-core',
    'google/j2objc',
    'hazelcast/hazelcast',
    'liferay/com-liferay-commerce',
    'apache/incubator-druid',
    'deeplearning4j/deeplearning4j',
    'jamesagnew/hapi-fhir',
    'att/AAF',
    'Pi4J/pi4j',
    'fcrepo4/fcrepo4',
    'b3log/latke',
    'Koekiebox-PTY-LTD/Fluid',
    'Red5/red5-server-common',
    'twitter/elephant-bird',
    'box/box-android-sdk',
    'beanshell/beanshell',
    'Impetus/Kundera',
    'Hygieia/Hygieia',
    'GoogleCloudPlatform/bigdata-interop',
    'VoltDB/voltdb',
    'groovy/groovy-core',
    'Samsung/GearVRf',
    'infinispan/infinispan',
    'lucee/Lucee',
    'apache/groovy',
    'jeremylong/DependencyCheck',
    'Alluxio/alluxio',
    'Stratio/stratio-cassandra',
    'kite-sdk/kite',
    'rhuss/jolokia',
    'sarl/sarl',
    'apache/flink',
    'pravega/pravega',
    'mozilla/rhino',
    'raphw/byte-buddy',
    'paypal/SeLion',
    'stratosphere/stratosphere',
    'graknlabs/grakn',
    'mongodb/mongo-java-driver',
    'jenetics/jenetics',
    'RestComm/sip-servlets',
    'molgenis/molgenis',
    'google/guava',
    'playn/playn',
    'h2oai/h2o-2',
    'atomix/atomix',
    'Sciss/abc4j',
    'deeplearning4j/nd4j',
    'pushbit/sprockets-android',
    'Stratio/bdt',
    'elki-project/elki',
    'pippo-java/pippo',
    'rometools/rome',
    'Graylog2/graylog2-server',
    'datastax/java-driver',
    'kiegroup/jbpm',
    'LearnLib/learnlib',
    'jooby-project/jooby',
    'googleapis/cloud-bigtable-client',
    'qos-ch/slf4j',
    'stapler/stapler',
    'basho/riak-java-client',
])


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

                # exclude repos(can't be parsed / too large / renamed / difficult to understand)
                if obj['repo'] in exclude_repo_set:
                    continue

                # exclude repos

                if obj['repo'] + obj['sha'] != cur_repo:
                    # limitation for data count in one repo
                    if len(filtered_repo_data) >= 50:
                        res.extend(filtered_repo_data)
                        repo_set.add(cur_repo)

                    filtered_repo_data = []
                    cur_repo = obj['repo'] + obj['sha']
                    cur_repo_path_set.clear()

                # limitation for whether the file equals to the class name
                if obj['path'].split('/')[-1].split('.')[0] != obj['func_name'].split('.')[0]:
                    continue

                # limitation for same path(file path + method name) in one repo
                if obj['path'] + '/' + obj['func_name'].split('.')[1] in cur_repo_path_set:
                    continue

                # limitation for directory hierarchy in path field
                if obj['path'].count('/') < 3 or obj['path'].count('/') > 15:
                    continue

                # limitation for query's token count in docstring_tokens field
                if len(obj['docstring_tokens']) < 10:
                    continue

                # limitation for content of query in docstring field
                if not obj['docstring'].isascii():
                    continue
                if "TODO" in obj['docstring'] or \
                    "NOTE" in obj['docstring'] or \
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
                query = re.sub(r'\(e\.g\.[^\)]*\)', '', query)
                query = re.sub(r'\(i\.e\.[^\)]*\)', '', query)
                query = re.sub(r'@.*', '', query)
                query = query.split('.')[0] + '.'
                query = query.replace('\n', ' ')
                query = re.sub(r'\s+', ' ', query)
                query = query.strip()

                # ignore query which is too short or too long
                if len(query) < 50 or len(query) > 200:
                    continue

                # ignore duplicate query in one repo
                if query in [item['query'] for item in filtered_repo_data]:
                    continue

                path = obj['path'] + '/' + obj['func_name'].split('.')[1]
                filtered_repo_data.append({
                    'repo': obj['repo'],
                    'query': query,
                    'path': path,
                    'sha': obj['sha'],
                })

                cur_repo_path_set.add(path)

    print('Filtered data count: {}\nRatio: {}\nRepo count: {}'.format(
        len(res), len(res) / raw_data_count, len(repo_set)))

    with open(output_file_path, 'w') as out_f:
        for obj in res:
            json.dump(obj, out_f)
            out_f.write('\n')


def get_repo_info_by_api(repo_name: str):
    for _ in range(3):
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
            sleep(random.randint(10, 20))
            continue

    return None


def filter_repo1(data_file_path, repo_file_path, output_file_path):
    respos = []
    repo_set = set()

    with open(data_file_path, 'r') as f_data, open(repo_file_path, 'r') as f_repo_info:
        data_objs = [json.loads(line) for line in f_data]
        repo_infos = [json.loads(line) for line in f_repo_info]

        for data_obj in tqdm(data_objs):
            if data_obj['repo'] in repo_set:
                continue
            repo_set.add(data_obj['repo'])

            # get repo info
            repo_info = next(
                filter(lambda x: x['name'] == data_obj['repo'].split('/')[-1], repo_infos), None)
            if repo_info is None:
                repo_info = get_repo_info_by_api(data_obj['repo'])
                if repo_info is None:
                    print(f'Cannot get repo info: {data_obj["repo"]}')
                    return

                with open(repo_file_path, 'a') as f_out:
                    f_out.write(json.dumps(repo_info) + '\n')

            # # limitation for star count
            if repo_info['stargazers_count'] < 100:
                continue

            # cancat zip url
            # https://github.com/soimort/you-get/archive/b746ac01c9f39de94cac2d56f665285b0523b974.zip
            zip_url = f"https://github.com/{data_obj['repo']}/archive/{data_obj['sha']}.zip"

            respos.append({
                'repo': data_obj['repo'],
                'sha': data_obj['sha'],
                'star': repo_info['stargazers_count'],
                'description': repo_info['description'],
                'zip_url': zip_url,
            })

    print(f'Filtered repo count: {len(respos)}')

    with open(output_file_path, 'w') as out_f:
        for obj in respos:
            json.dump(obj, out_f)
            out_f.write('\n')


def filter_repo2(repo_file_path, repo_root_path, output_file_path):
    repos = []
    temp_dir_path = './parse_temp'
    temp_file_list = os.listdir(temp_dir_path)

    with open(repo_file_path, 'r') as f_repo:
        repo_objs = [json.loads(line) for line in f_repo]

        for repo_obj in tqdm(repo_objs):
            repo_dir_name = f"{repo_obj['repo'].split('/')[-1]}-{repo_obj['sha']}"
            repo_dir_path = os.path.join(repo_root_path, repo_dir_name)

            parse_log_path = os.path.join(
                temp_dir_path, f"parse_log_{repo_dir_name}.txt")
            parse_out_path = os.path.join(
                temp_dir_path, f"parse_out_{repo_dir_name}.json")

            # if repo is already parsed, skip it
            if f"parse_out_{repo_dir_name}.json" not in temp_file_list:
                if (0 != parse_repo(repo_dir_path, parse_out_path, parse_log_path)):
                    print(f"Failed to parse repo: {repo_obj['repo']}")
                    continue

            with open(parse_out_path, 'r') as f_parse_out:
                try:
                    parse_obj = json.loads(f_parse_out.read())
                except Exception as e:
                    print(f"Failed to parse json: {parse_out_path}")
                    print(e)
                    return
                node_count = parse_obj['nodeCount']
                max_sub_dir_count = parse_obj['maxSubDirCount']
                max_file_count = parse_obj['maxFileCount']
                max_sub_dir_and_file_count = parse_obj['maxSubDirAndFileCount']
                # print(
                #     f"Repo: {repo_obj['repo']}, Node count: {node_count}")
                if node_count > 2000:
                    continue

                if max_sub_dir_count > 6 or max_sub_dir_count < 2:
                    continue

                if max_sub_dir_and_file_count > 50:
                    continue

                repo_obj['node_count'] = node_count
                repo_obj['max_sub_dir_count'] = max_sub_dir_count
                repo_obj['max_file_count'] = max_file_count
                repo_obj['max_sub_dir_and_file_count'] = max_sub_dir_and_file_count

                repos.append(repo_obj)

    print(f'Filtered repo count: {len(repos)}')

    with open(output_file_path, 'w') as out_f:
        for obj in repos:
            json.dump(obj, out_f)
            out_f.write('\n')


def has_true_path_arr(parse_obj, true_path_str) -> bool:
    def get_method_path(file_obj, path_str):
        if path_str[0] == '/':
            path_str = path_str[1:]

        for method_obj in file_obj['methods']:
            if path_str.startswith(method_obj['name']):
                return True

        return False

    def get_file_path(dir_obj, path_str):
        if path_str[0] == '/':
            path_str = path_str[1:]

        for sub_dir_obj in dir_obj['subdirectories']:
            if path_str.startswith(sub_dir_obj['name']):
                return get_file_path(sub_dir_obj, path_str[len(sub_dir_obj['name']):])

        for file_obj in dir_obj['files']:
            if path_str.startswith(file_obj['name']):
                return get_method_path(file_obj, path_str[len(file_obj['name']):])

        return False

    return get_file_path(parse_obj['mainDirectory'], true_path_str)


def filter_data2(repo_file_path, data_file_path, output_file_path):
    res = []
    repo_set = set()
    no_true_path_count = 0

    with open(repo_file_path, 'r') as repo_f:
        for line in repo_f:
            repo_set.add(json.loads(line)['repo'])

    with open(data_file_path, 'r') as data_f:
        for line in data_f:
            data_obj = json.loads(line)

            if data_obj['repo'] not in repo_set:
                continue

            # java-repo-parser ignores the constructor / getter / setter / equals / toString / hashCode
            # so we need to filter them out
            parse_out_path = os.path.join(
                './parse_temp', f"parse_out_{data_obj['repo'].split('/')[-1]}-{data_obj['sha']}.json")
            if not os.path.exists(parse_out_path):
                print(f'Parse out file not exists: {parse_out_path}')
                continue
            with open(parse_out_path, 'r') as parse_f:
                parse_obj = json.load(parse_f)

                if not has_true_path_arr(parse_obj, data_obj['path']):
                    no_true_path_count += 1
                    continue

                res.append(data_obj)

    # print(f'No true path count: {no_true_path_count}')
    print(f'Filtered data count: {len(res)}')

    with open(output_file_path, 'w') as out_f:
        for obj in res:
            json.dump(obj, out_f)
            out_f.write('\n')


def filter_data3(repo_file_path, data_file_path, output_file_path):
    res = []
    repo_set = set()

    with open(repo_file_path, 'r') as repo_f:
        for line in repo_f:
            repo_set.add(json.loads(line)['repo'])

    with open(data_file_path, 'r') as data_f:
        for line in data_f:
            data_obj = json.loads(line)

            if data_obj['repo'] not in repo_set:
                continue

            res.append(data_obj)

    print(f'Filtered data count: {len(res)}')

    with open(output_file_path, 'w') as out_f:
        for obj in res:
            json.dump(obj, out_f)
            out_f.write('\n')


def get_data_final(data_file_path):
    res = []

    idx = 0
    with open(data_file_path, 'r') as data_f:
        for line in data_f:
            data_obj = json.loads(line)

            data_obj['id'] = idx
            idx += 1
            res.append(data_obj)

    print(f'Total data count: {len(res)}')

    with open(data_file_path, 'w') as out_f:
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


def get_datas_from_sum_out(sum_obj, repo_name, repo_sha):
    NO_SUMMARY = "*** No summary ***"

    def wonder_in_file(file_obj, path_str):
        for method_obj in file_obj['methods']:
            summary = method_obj['summary']
            if summary == NO_SUMMARY:
                continue

            if summary[-1] != '.':
                continue

            summary = summary.replace(method_obj['name'], '')
            summary = summary.replace('()', '')
            summary = summary.replace('``', '')
            summary = summary.replace(', ,', ',')
            summary = summary.replace('\"\"', '')
            summary = re.sub(r'\s+', ' ', summary)
            summary = summary.strip()

            res_path = "/".join(path_str.split('/')[1:])
            datas.append({
                'repo': repo_name,
                'sha': repo_sha,
                'query': summary,
                'path': res_path + '/' + method_obj['name']
            })

    def wonder_in_dir(dir_obj, path_str):
        for sub_dir_obj in dir_obj['subdirectories']:
            wonder_in_dir(sub_dir_obj, f"{path_str}/{sub_dir_obj['name']}")

        for file_obj in dir_obj['files']:
            wonder_in_file(file_obj, f"{path_str}/{file_obj['name']}")

    datas = []
    wonder_in_dir(sum_obj, sum_obj['name'])

    return datas


def generate_data(repo_file_path, out_put_path):
    datas = []
    with open(repo_file_path, 'r') as repo_f:
        repo_objs = [json.loads(line) for line in repo_f]

        for repo_obj in tqdm(repo_objs):
            sum_out_path = os.path.join('./sum_result', repo_obj['repo'].split(
                '/')[-1], f"sum_out_{repo_obj['repo'].split('/')[-1]}.json")

            if not os.path.exists(sum_out_path):
                print(f'Sum out file not exists: {sum_out_path}')
                continue

            with open(sum_out_path, 'r') as sum_f:
                sum_obj = json.load(sum_f)
                temp_datas = get_datas_from_sum_out(
                    sum_obj, repo_obj['repo'], repo_obj['sha'])
                datas.extend(temp_datas)

    random.shuffle(datas)
    datas = datas[:100]
    for idx, data in enumerate(datas):
        data['id'] = idx

    print(f'Generated data count: {len(datas)}')

    with open(out_put_path, 'w') as out_f:
        for data in datas:
            json.dump(data, out_f)
            out_f.write('\n')


if __name__ == "__main__":
    raw_dir_path = os.path.join(os.getcwd(), 'raw')
    repo_dir_path = os.path.join(os.getcwd(), 'repo')
    filtered_dir_path = os.path.join(os.getcwd(), 'filtered')
    generated_dir_path = os.path.join(os.getcwd(), 'generated')

    data1_file_path = os.path.join(filtered_dir_path, 'data1.jsonl')
    repo_info_file_path = os.path.join(filtered_dir_path, 'repo_info.jsonl')
    repo1_file_path = os.path.join(filtered_dir_path, 'repo1.jsonl')
    repo2_file_path = os.path.join(filtered_dir_path, 'repo2.jsonl')
    data2_file_path = os.path.join(filtered_dir_path, 'data2.jsonl')
    repo_final_file_path = os.path.join(filtered_dir_path, 'repo_final.jsonl')
    data3_file_path = os.path.join(filtered_dir_path, 'data3.jsonl')
    data_final_file_path = os.path.join(filtered_dir_path, 'data_final.jsonl')
    generated_data_file_path = os.path.join(generated_dir_path, 'data.jsonl')

    # filter_data1(raw_dir_path, data1_file_path)

    # filter_repo1(data1_file_path, repo_info_file_path, repo1_file_path)

    # download_repos(repo1_file_path, repo_dir_path, 0)

    # filter_repo2(repo1_file_path, repo_dir_path, repo2_file_path)

    # filter_data2(repo2_file_path, data1_file_path, data2_file_path)

    # filter_data3(repo_final_file_path, data2_file_path, data3_file_path)

    get_data_final(data_final_file_path)

    # generate_data(repo2_file_path, generated_data_file_path)
