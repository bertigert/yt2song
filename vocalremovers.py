from os.path import basename
from time import sleep, time
from datetime import datetime, UTC
import json

import requests
import websocket

from hashlib import md5
from base64 import b64encode
import hmac
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.backends import default_backend



# supported formats for all removers: MP3, OGG, WAV, FLAC, AIFF, AAC (lalalai is weakest link)


def download_file(url: str, filename: str):
    """Downloads any file to an output file, Vocalremovers export to mp3"""
    r = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })

    if r.ok:
        with open(filename, "wb") as f:
            f.write(r.content)


class LalalAI:
    """Class for removing vocals using the https://www.lalal.ai/ website. Maximum 1 min files, file needs to be mp3"""

    def __init__(self) -> None:
        self.session =  requests.Session()
        self.session.get("https://www.lalal.ai/")
    

    def __queue_file_into_preview(self, task_id: str):
        """Queues the file into preview, meaning that it will be processed"""

        data = {
            "id": task_id,
            "filter": "1", 
            "stem": "vocals",
            "splitter": "orion",
            "dereverb_enabled": "false"
        }

        r = self.session.post("https://www.lalal.ai/api/preview/", data=data)
        if r.ok:
            return r.json()


    def upload_file(self, filepath: str, only_upload: bool=False) -> dict:
        """ 
            Uploads the file, but (if only_upload is true) does not queue it for preview-> doesnt get processed i believe (thats how the site work)\n
            Return the file/task id
        """
        
        with open(filepath, "rb") as f:
            headers = {
                "Content-Disposition": "attachment; filename*=UTF-8''"+basename(filepath)
            }
            r = self.session.post("https://www.lalal.ai/api/upload/", files={"f": f}, headers=headers)
        
        if r.ok and (resp := r.json())["status"] == "success":
            if not only_upload:
                self.__queue_file_into_preview(resp["id"])

            return resp["id"]
    

    def check_progress(self, task_id: str):
        """
            Checks the progress of processing of a file.\n
            Returns the url of the edited file if its finished
        """
        
        r = self.session.post("https://www.lalal.ai/api/check/", data={"id": task_id})
        if r.ok and (resp := r.json())["status"] == "success":
            if resp["result"][task_id]["task"]["state"] == "success":
                return resp["result"][task_id]["preview"]["back_track"]


    def wait_for_task_finish(self, task_id: str, delay: float=3.0, timeout: int=300) -> str:
        """Waits for the task to be processed, returns the url when its finished"""

        start = time()
        while True:
            if time()-start > timeout:
                return None
            
            url = self.check_progress(task_id=task_id)
            if url:
                return url
            
            sleep(delay)


    def process_file(self, filepath: str, debug: bool=False):
        """ 
            Uploads the file and waits for the processing to finish\n
            returns the url of the processed file\n
            filepath - path to the file
        """
        task_id = self.upload_file(filepath)
        if not task_id:
            return None
        
        return self.wait_for_task_finish(task_id=task_id)


class VocalRemoverMediaIO:

    def __init__(self) -> None:
        self.session =  requests.Session()
       

    def __calculate_data_for_file_upload__(self, resp_data: dict, file_name: str):
        """ 
            Calculate the needed data for authorizing the upload.\n 
            data needs to be response_json["data"] from the token request.\n
            file_name needs to be a random (md5) hash. I would use the md5 hash of the file with a timestamp, it should not matter though 
        """
        # everything here is copying https://resource.media.io/vocalremover/assets/js/36964411-71a6be4c.js, column 20180
        
        auth_data = {
            "curr_date": datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "host": f'{resp_data["params"]["bucket_name"]}.{resp_data["params"]["bucket_endpoint"].replace("https://", "")}',
            "file_path_on_server": resp_data["path"],
            "security_token": resp_data["params"]["security_token"]
        }
        
        auth_data["x_oss_callback"] = b64encode(json.dumps(
            {
                "callbackBody": resp_data["params"].get("call_back_body", "storage_key=${object}&file_size=${size}&mime_type=${mimeType}&etag=${etag}&bucket=${bucket}&format=${imageInfo.format}&height=${imageInfo.height}&width=${imageInfo.width}&user_id=${x:user_id}&region=${x:region}&description=${x:description}&file_name=${x:file_name}&action=${x:action}&expire=${x:expire}"),
                "callbackBodyType": resp_data["params"].get("callback_body_type", "application/x-www-form-urlencoded"),
                "callbackHost": resp_data["params"].get("callback_host", "third-oss-sgp.300624.com"),
                "callbackUrl": resp_data["params"].get("callback_url", "https://third-oss-sgp.300624.com/v3/storage/callback/aliyun")
            }
            ).encode()).decode()

        #encode some access_key_secret and shit into some form of authorization token (thx chatgpt)
        some_data_for_auth = f'PUT\n\naudio/mpeg\n{auth_data["curr_date"]}\nx-oss-callback:{auth_data["x_oss_callback"]}\nx-oss-date:{auth_data["curr_date"]}\nx-oss-security-token:{resp_data["params"]["security_token"]}\nx-oss-user-agent:aliyun-sdk-js/6.17.1 Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36\n/{resp_data["params"]["bucket_name"]}/{resp_data["path"]}{file_name}.mp3'                                 
        h = hmac.HMAC(resp_data["params"]["access_key_secret"].encode(), hashes.SHA1(), backend=default_backend())
        h.update(some_data_for_auth.encode())
        digest = h.finalize()
        encoded_digest = b64encode(digest).decode()
        auth_data["authorization"] = f'OSS {resp_data["params"]["access_key_id"]}:{encoded_digest}'
        
        return auth_data


    def __create_task(self, create_task_payload: dict):
        """
            Creates the task for the file to be processed\n
            create_task_payload should be the final payload for the request, see upload_file\n
            returns the task id for the process
        """

        r = self.session.post("https://jk.media.io/v1/asn/create", json=create_task_payload, headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://vocalremover.media.io",
            "Referer": "https://vocalremover.media.io/app/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })

        if r.ok:
            return r.json()["data"]["task_id"]


    def upload_file(self, filepath: str, only_upload: bool=False):
        """ 
            Uploads the file, but does not create a task if only_upload is true\n
            Either returns the task id if the task is created. otherwise returns an dictionary payload which would be used to create the task  
        """
        
        t = f"{time()*1000:.0f}"

        with open(filepath, "rb") as f:            
            file_data = f.read()
        
        #file_hash = md5(file_data).hexdigest # not needed bc hardcoded
        file_name = md5(file_data+t.encode()).hexdigest() # can be dead wrong

        r = self.session.get(f"https://jk.media.io/v1/storage/token?kind=vocalremover&_t="+t)
        
        auth_data = self.__calculate_data_for_file_upload__(r.json()["data"], file_name)
        
        # upload
        r = self.session.put(f'https://{auth_data["host"]}/{auth_data["file_path_on_server"]}{file_name}.mp3', headers={
            "Authorization": auth_data["authorization"],
            "Content-Type": "audio/mpeg",
            "Host": auth_data["host"],
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "X-Oss-Callback": auth_data["x_oss_callback"],
            "X-Oss-Date": auth_data["curr_date"],
            "X-Oss-Security-Token": auth_data["security_token"],
            "X-Oss-User-Agent": "aliyun-sdk-js/6.17.1 Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }, data=file_data) 

        create_task_payload = {
            "file_link": f"{auth_data['file_path_on_server']}{file_name}.mp3",
            "file_name": basename(filepath),
            "pic_info": {
                "file_md5": "1bf1f1e6f112b2fb5836c1c3abcb5411", # for some reason hard coded
                "file_ext": basename(filepath).rsplit(".", maxsplit=1)[1],
                "file_time": 168 # for some reason hard coded
            },
            "file_ext": "mp3",
            "alType": "asn"
        }

        if only_upload:
            return create_task_payload
        
        return self.__create_task(create_task_payload)
        

    def check_progress(self, task_id: str):
        """
            Checks the progress of processing of a file.\n
            Returns the url of the edited file if its finished else None
        """

        r = self.session.get(f"https://jk.media.io/v1/asn/result/{task_id}?&_t={time()*1000:.0f}")
        
        if not r.ok:
            return None

        resp = r.json()
        
        if resp["data"]["status"] == 3:
            return resp["data"]["instrument_link"]


    def wait_for_task_finish(self, task_id: str, delay: float=3.0, timeout: int=300) -> str:
        """Waits for the task to be processed, returns the url when its finished, None if timeout is hit"""
        start = time()
        while True:
            if time()-start > timeout:
                return None
            
            url = self.check_progress(task_id)
            if url:
                return url

            sleep(delay)


    def process_file(self, filepath: str, debug: bool=False):
        """ 
            Uploads the file and waits for the processing to finish\n
            returns the url of the processed file\n
            filepath - path to the file
        """
        task_id = self.upload_file(filepath)
        if not task_id:
            return None
        
        return self.wait_for_task_finish(task_id=task_id)

        


class VocalremoverDotOrg:
    def __init__(self) -> None:
        self.session = requests.Session()    
        
    def process_file(self, filepath: str, debug: bool=False):
        """ 
            Uploads the file and waits for the processing to finish\n
            returns the url of the processed file\n
            filepath - path to the file
        """

        self.session.headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Locale": "en",
            "Origin": "https://vocalremover.org",
            "Referer": "https://vocalremover.org/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        
        r = self.session.get("https://api.vocalremover.org/split/get_server")
        if r.status_code == 429:
            print("Vocalremover.org free limit reached")
            return
        
        if r.ok:
            server = r.json()["server"]
        
        with open(filepath, "rb") as f:
            files = {"file": (basename(filepath), f)}
            body, content_type = requests.models.RequestEncodingMixin._encode_files(files, {}) #https://stackoverflow.com/questions/36286656/python-set-up-boundary-for-post-using-multipart-form-data-with-requests/64586578#64586578
            
            r = self.session.post(f"https://api{server}.vocalremover.org/split/tracks", data=body, headers={
                "Content-Type": content_type,
            })
        
            if r.ok:
                resp = r.json()
                session_id = resp["id"]
                key = resp["key"]

        if debug:
            print("Uploaded file, connecting to websocket")

        def on_open(ws):
            if debug:
                print("Connected to websocket, waiting for processing to finish")

        def on_message(ws: websocket.WebSocketApp, message: str):
            data = json.loads(message)
            
            if "type" in data and data["type"] == "welcome":
                msg = {
                    "command": "subscribe",
                    "identifier": f"{{\"id\":{session_id},\"channel\":\"FileSpleeterChannel\"}}"
                }
                ws.send(json.dumps(msg))
            
            elif "identifier" in data and data["message"]["status"] == "ready":
                ws.close()
            

        def on_error(ws, error: KeyError):
            if type(error) != KeyError:
                print("\n------ WEBSOCKET ENCOUNTERED ERROR ------\n" + str(error))

        ws = websocket.WebSocketApp(f"wss://api{server}.vocalremover.org/cable", on_open=on_open, on_message=on_message, on_error=on_error, header={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"})
        ws.run_forever(reconnect=5)
        
        if debug:
            print("Processing done")
        
        return f"https://api{server}.vocalremover.org/split/listen/music/{session_id}/{key}"
    

       