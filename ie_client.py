import logging
import os
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
        res = requests.post(self.url,
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

        if res.status_code != 200 or len(res.json()) == 0:
            raise Exception(res.json())

        return res.json()[0]['generated_text']


if __name__ == '__main__':

    load_dotenv()

    try:
        ie_client = IEClient()
    except Exception as e:
        print(e)
        exit(1)

    print(ie_client.check_health())

#     input_text = '''<s>[INST] Summarize the directory below in about 50 words, don't include examples.
# ######################################################
# Directory name: core.
# The following is the file in the directory and the corresponding summary:
# 	- The summary of file named CachedQuery.java:   The CachedQuery class implements the CanEstimateSize interface and provides methods for increasing the execution count and calculating the size of the query. The getSize() method calculates the size of the query by multiplying the number of characters in the key by 2 if the key is a string, or by calling the getSize() method on the key object if the key is not a string.
# 	- The summary of file named CachedQueryCreateAction.java:   The `CachedQueryCreateAction` class is a part of the `LruCache` class and implements the `CreateAction` interface. It creates a `CachedQuery` object based on the given `key`. If the `key` is a `String`, it creates a `CachedQuery` with the `key` as the SQL query. If the `key` is a `BaseQueryKey`, it extracts the `sql` property and creates a `Cached
# 	- The summary of file named BaseStatement.java:   The `BaseStatement` interface extends both `PGStatement` and `Statement` interfaces and is a base interface for all statement types in the `java.sql` package.
# 	- The summary of file named BaseConnection.java:   The `BaseConnection` interface is a base interface for a connection to a PostgreSQL database. It extends both `PGConnection` and `Connection`.
# 	- The summary of file named BaseQueryKey.java:   The BaseQueryKey class implements the CanEstimateSize interface and provides a method getSize() that returns the size of the object in bytes. The size is calculated based on the length of the sql field, which is a string. If the sql field is null, the size is 16, otherwise it is 16 plus the length of the sql field multiplied by 2.
# 	- The summary of file named ConnectionFactory.java:   The `ConnectionFactory` class is an abstract class that provides a way to create connections to a PostgreSQL database. It has two methods: `openConnection` and `closeStream`. The `openConnection` method creates a new connection using the specified `HostSpec`, `user`, `database`, and `info` parameters, and the `closeStream` method closes a `PGStream` object if it is not null.
# 	- The summary of file named CommandCompleteParser.java:   The `CommandCompleteParser` class has two methods: `set` and `parse`. The `set` method sets the `oid` and `rows` fields of the object to the given values. The `parse` method takes a string `status` and parses it to extract the OID and rows. It assumes that the command does not start or end with a digit, and scans backwards in the string to find the maximum of two number groups, which are assumed to
# 	- The summary of file named CallableQueryKey.java:   The CallableQueryKey class is a subclass of BaseQueryKey that represents a query key that can be called to retrieve a value. It does not have any additional functionality beyond what is provided by BaseQueryKey.
#  [/INST]'''

#     output = ie_client.generate(input_text, 200)

#     print(output)
