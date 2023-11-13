import os
import requests
from dotenv import load_dotenv


class IEClient:
    def __init__(self, url: str, token: str):
        self.token = token
        self.url = url

    def generate(self, input_text: str) -> str:
        response = requests.post(self.url,
                                 headers={
                                     "Authorization": f"Bearer {self.token}",
                                     "Content-Type": "application/json"
                                 },
                                 json={
                                     "inputs": input_text,
                                     "parameters": {
                                         "do_sample": True,
                                         "temperature": 0.2,
                                         "max_new_tokens": 100,
                                         "top_p": 0.9,
                                         "num_return_sequences": 1
                                     }
                                 })

        if response.status_code != 200 or len(response.json()) == 0:
            return ""

        return response.json()[0]['generated_text']


if __name__ == '__main__':

    load_dotenv()

    client = IEClient()

    input_text = '''<s>[INST] Summarize the Java class below in about 50 words
    ======================================================
    Class ReloadingFileBasedConfigurationBuilder<T extends FileBasedConfiguration> {
        ReloadingFileBasedConfigurationBuilder<T> configure​(BuilderParameters... params); // Appends the content of the specified BuilderParameters objects to the current initialization parameters.
        protected ReloadingDetector createReloadingDetector​(FileHandler handler, FileBasedBuilderParametersImpl fbparams); // Creates a ReloadingDetector which monitors the passed in FileHandler.
        ReloadingController getReloadingController(); // Gets the ReloadingController associated with this builder.
        protected void initFileHandler​(FileHandler handler); // Initializes the new current FileHandler.
    } [/INST]'''

    output = client.generate(input_text)

    print(output)
