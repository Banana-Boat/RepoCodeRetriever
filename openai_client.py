import os
import requests
from dotenv import load_dotenv


class OpenAIClient:
    def __init__(self):
        session_id = os.getenv('OPENAI_SESSION_ID')
        token = os.getenv('OPENAI_TOKEN')
        model_name = os.getenv('OPENAI_MODEL_NAME')
        max_number_of_tokens = os.getenv('OPENAI_MAX_NUMBER_OF_TOKENS')

        if session_id == None or token == None or model_name == None or max_number_of_tokens == None:
            raise Exception("Cannot get value in .env file.")

        # get form openai login API, and used for account's credit checking
        self.session_id = session_id
        self.token = token
        self.model_name = model_name
        # = context window = max_input_length + max_output_length
        self.max_number_of_tokens = int(max_number_of_tokens)

    def get_credit_grants(self) -> float:
        '''
            get available credit grants(USD) of the account
        '''
        res = requests.get(
            "https://api.openai.com/dashboard/billing/credit_grants",
            headers={
                "Authorization": f"Bearer {self.session_id}"
            })

        if res.status_code != 200:
            return -1.0

        return res.json()['total_available']

    def generate(self, input_text: str, max_output_length: int) -> dict:
        '''
            return {total_tokens: int, output_text: str}
        '''
        res = requests.post("https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.token}",
                                "Content-Type": "application/json"
                            },
                            json={
                                "model": self.model_name,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": input_text
                                    }
                                ],
                                "max_tokens": max_output_length,
                                "n": 1,
                                "temperature": 0.2,
                            })

        if res.status_code != 200:
            raise Exception(
                f"OpenAI API error code: {res.status_code}\n{res.json()}")

        return {
            "total_tokens": res.json()['usage']['total_tokens'],
            "output_text": res.json()['choices'][0]['message']['content']
        }


if __name__ == '__main__':
    load_dotenv()

    try:
        openai_client = OpenAIClient()
    except Exception as e:
        print(e)
        exit(1)

    print(openai_client.get_credit_grants())

#     input_text = '''Summarize the directory below in about 100 words, don't include examples and details.
# ######################################################
# Directory name: timer.
# The following is the file in the directory and the corresponding summary:
# 	- The summary of file named ZTimer.java:   The ZTimer class provides methods for creating and managing timers, while the Timer class provides methods for setting and resetting an interval, as well as canceling the timer.
# 	- The summary of file named ZTicker.java:   The ZTicker class provides methods for adding timer and ticket objects, as well as a method to determine the minimum of their timeouts. It also has an execute() method that combines the results of the timer and ticket methods.
# 	- The summary of file named TimerHandler.java:   The TimerHandler interface extends the Timers.Handler interface and defines a single method, time, which takes an arbitrary number of Object arguments.
# 	- The summary of file named ZTicket.java:   The ZTicket class manages a list of tickets with a delay and a handler. It provides methods to add new tickets, check the time difference between the start time of the first ticket and the current time plus the delay of the first ticket, and execute the tickets. The class also provides a method to sort the tickets if necessary. The Ticket class implements the Comparable interface and provides methods for resetting and canceling a timer, as well as comparing the start
# '''

#     output = openai_client.generate(input_text, 200)

#     print(output)
