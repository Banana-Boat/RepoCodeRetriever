import os
import random
from time import sleep
import requests
from dotenv import load_dotenv


class IEClient:
    def __init__(self):
        token = os.getenv('IE_TOKEN')
        url = os.getenv('IE_URL')
        model_name = os.getenv('IE_MODEL_NAME')
        max_number_of_tokens = os.getenv('IE_MAX_NUMBER_OF_TOKENS')
        max_batch_size = os.getenv('IE_MAX_BATCH_SIZE')
        if token == None or url == None or model_name == None or max_number_of_tokens == None or max_batch_size == None:
            raise Exception("Cannot get value in .env file.")

        self.token = token
        self.url = url
        self.model_name = model_name
        # = context window = max_input_length + max_output_length
        self.max_number_of_tokens = int(max_number_of_tokens)
        # = number of requests processed concurrently by the server
        if int(max_batch_size) > 1:
            # -1 to reduce pressure on server
            self.max_batch_size = int(max_batch_size) - 1
        else:
            self.max_batch_size = 1

    def check_health(self) -> bool:
        res = requests.get(self.url + '/health')
        return res.status_code == 200

    def generate(self, input_text: str, max_output_length: int) -> str:
        error_msg = ""

        for _ in range(5):
            try:
                res = requests.post(self.url,
                                    timeout=20,
                                    headers={
                                        "Authorization": f"Bearer {self.token}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "inputs": input_text,
                                        "parameters": {
                                            "max_new_tokens": max_output_length,
                                            "do_sample": True,
                                            "temperature": 0.2,
                                            "top_p": 0.9,
                                            "num_return_sequences": 1
                                        }
                                    })

                # if request failed, retry
                if res.status_code != 200 or len(res.json()) == 0:
                    raise Exception(res.json())

                return res.json()[0]['generated_text']
            except Exception as e:
                error_msg = e
                # wait random time to reduce pressure on server
                sleep(random.randint(5, 15))
                continue

        raise Exception(error_msg)


if __name__ == '__main__':

    load_dotenv()

    try:
        ie_client = IEClient()
    except Exception as e:
        print(e)
        exit(1)

    input_text = '''<s>[INST]<<SYS>>
Summarize the Java method provided to you in about 30 words.
<</SYS>>
ClassInfoList exclude(final ClassInfoList other){ final Set<ClassInfo> reachableClassesDifference = new LinkedHashSet<>(this); final Set<ClassInfo> directlyRelatedClassesDifference = new LinkedHashSet<>(directlyRelatedClasses); reachableClassesDifference.removeAll(other); directlyRelatedClassesDifference.removeAll(other.directlyRelatedClasses); return new ClassInfoList(reachableClassesDifference, directlyRelatedClassesDifference, sortByName); }
[/INST]'''
    output_text = ie_client.generate(input_text, 60)
    # 最后一句完整的句子之后部分截断
    last_dot_index = output_text.rfind('.')
    if last_dot_index != -1:
        output_text = output_text[:last_dot_index + 1]
    print(output_text)
