#!/usr/bin/env python 
# A Tool which combines different websites/tool to get a (background) song from a youtube video
# Steps:
#  1. Download Youtube Audio
#  2. Remove Vocals from the site (https://vocalremover.media.io/app/, https://vocalremover.org/, https://www.lalal.ai/)
#  3. Recognize the song using Shazam or AudD.io, would do acrcloud, but you would need multiple accounts or you could 
#     abuse the musixmatch api (uses acrcloud) (even though it is only for live songs and not from a file, so you would need to implement your own logic)
    # Muixmatch API data
    # access_key = "1f142ebb285ef8e0c0f19915916e1f84"
    # access_secrets = ["Uydil8cdA1Onrf6wxmpdBJaKFE2iEhTGLL11QKT6", "IymlQCE9AS7vxGNFBcqZdJs6labIUrsJbg0iQCMR", "sMSfC4nEavjMD6NMtL97h6koavs6PkUZrHIRJCbh"] # not sure which one
    # requrl = "https://identify-global.acrcloud.com/rec"


import json
import os
from sys import exit, platform
import argparse
from time import time
from datetime import datetime

import asyncio
from threading import Thread, Lock

import vocalremovers
from shazamio import Shazam
import songidentifiers

def tprint(*args):
    """Print anything with a timestamp"""
    print(f"[{datetime.now():%H:%M:%S}]", *args)


FILE_PATH = os.path.dirname(os.path.realpath(__file__))

with open(FILE_PATH+"/config.json", "rb") as f:
    config = json.load(f)

# "store_true" = false by default 
parser = argparse.ArgumentParser(prog="yt2song", description="A Tool which combines different websites/tools to get a (background) song from a youtube video.\n The shorter the snippet the better")
parser.add_argument("-l", "--link", help="The Youtube Video Link", required=True) # validation through yt-dlp
parser.add_argument("-t", "--time", help="The time window in which the song is played (format: hh:mm:ss-hh:mm:ss/mm:ss-mm:ss)", required=True)
parser.add_argument("-sv", "--skipvocalremover", action="store_true", help="Skip vocalremovers")
parser.add_argument("-sa", "--skipaudio", action="store_true", help="Skip the download of the original file")
parser.add_argument("-a", "--ask", action="store_true", help="Ask which processed files to use, uses every file otherwise")
parser.add_argument("-o", "--original", action="store_true", help="Also shazam the original file when not asking for which files to use")
parser.add_argument("-f", "--first", action="store_true", help="Use the first vocalremover which finishes")
parser.add_argument("-c", "--clean", action="store_true", help="not implemented, Clean files before and after usage")
args = parser.parse_args()


time_specify_string = ""
if args.time:
    if not "-" in args.time or args.time.count(":") < 2:
        exit("Invalid Time Range")

    args.time = args.time.split("-")
    format_table = ["%S", "%M:%S", "%H:%M:%S"]
    audio_length = ( datetime.strptime(args.time[1], format_table[args.time[1].count(":")]) - datetime.strptime(args.time[0], format_table[args.time[0].count(":")]) ).total_seconds()

    time_specify_string = f"-ss {args.time[0]} -to {args.time[1]}"

if not args.skipaudio:
    tprint("Downloading Audio")
    
    if platform == "linux":
        download_audio_cmd = f'''yt-dlp --skip-download -g "{args.link}" | tail -n 1 | while read -r f; do ffmpeg -y -hide_banner -loglevel error -stats {time_specify_string} -i "$f" -c:v copy "{FILE_PATH}/outputs/original.mp3"; done'''
    else:
        download_audio_cmd = f'''for /f "skip=1" %f in ('yt-dlp.exe -g "{args.link}"') do @ffmpeg -y -hide_banner -loglevel error -stats {time_specify_string} -i "%f" -c:v copy "{FILE_PATH}/outputs/original.mp3"'''
    
    os.system(download_audio_cmd)

    tprint("Finished Audio Download")

if not args.skipvocalremover:
    tprint("Starting removing vocals\n")
    

    def remove_vocals(vocalremover):
        start = time()
        vocalremovers_functions = {
            "vocalremovermediaio": vocalremovers.VocalRemoverMediaIO,
            "vocalremoverorg": vocalremovers.VocalremoverDotOrg,
            "lalalai": vocalremovers.LalalAI
        }

        tprint(f"{vocalremover} is processing file...")
        
        api = vocalremovers_functions[vocalremover]()
        url = api.process_file(filepath=FILE_PATH+"/outputs/original.mp3")
        
        if already_done_so_dont_download_when_finished:
            return
        
        if url:
            vocalremovers.download_file(url, f"{FILE_PATH}/outputs/{vocalremover}.mp3")
            tprint(f"{vocalremover} finished processing file")
            with lock:
                time_per_second_length = round((time()-start) / audio_length, 1) # calculate how long the process took for each second of the audio file (for this run)
                print(f"{vocalremover} took {time_per_second_length} seconds per second of the audio file")
                if stats["average_process_time_per_second_length"][vocalremover] == 0: # first run
                    stats["average_process_time_per_second_length"][vocalremover] = time_per_second_length
                else:
                    stats["average_process_time_per_second_length"][vocalremover] = ( stats["average_process_time_per_second_length"][vocalremover] + time_per_second_length ) / 2 # average the time of the run with the other runs

        else:
            tprint(f"{vocalremover} failed to process file")

    lock = Lock()
    with open(FILE_PATH+"/stats.json", "r") as f:
        stats = json.loads(f.read())
    
    threads = {}
    for vocalremover in config["vocalremovers"]:
        if config["vocalremovers"][vocalremover]:
            t = Thread(target=remove_vocals, args=[vocalremover])
            t.daemon = True
            threads[vocalremover] = t
            t.start()

    already_done_so_dont_download_when_finished = False
    if args.first:
        while already_done_so_dont_download_when_finished == False:
            
            for vocalremover in threads:
                t = threads[vocalremover]
                t.join(timeout=0.1)
                
                if not t.is_alive():
                    already_done_so_dont_download_when_finished = vocalremover
                    break      
    else:
        for vocalremover in threads:
            threads[vocalremover].join()
    
    with open(FILE_PATH+"/stats.json", "w") as f:
        f.write(json.dumps(stats, indent=4))

    tprint("Finished Removing Vocals\n")



all_files = os.listdir(FILE_PATH+"/outputs")
s = ""
for i, file in enumerate(all_files):
    s += f"[{i}] {file}\n"
    
if args.first and len(all_files) > 1:
    chosen_files = [all_files.index(already_done_so_dont_download_when_finished+".mp3")] 
    if args.original:
        chosen_files += [all_files.index("original.mp3")]

elif args.ask:
    chosen_files = input(s+"\nWhich file(s) to identify (e.g. 0,1,3) (all/* for all files): ")
    if chosen_files.strip() in ("all", "*"):
        chosen_files = range(len(all_files))
    else:
        chosen_files = chosen_files.replace(" ", "").split(",")
else:
    chosen_files = []
    for i, v in enumerate(all_files):
        if not args.original and v == "original.mp3":
            continue
        chosen_files.append(i)

files = [all_files[chosen_file] for chosen_file in chosen_files]



    

max_song_length = 0
if config["songidentifiers"]["shazam"]:
    async def shazam_it() -> list:
        shazam = Shazam()
        async with asyncio.TaskGroup() as tg:
            tasks = []
            for file in files:
                    tprint(f"Shazaming {file}")
                    tasks.append(tg.create_task(shazam.recognize(FILE_PATH+'/outputs/'+file)))
            results = await asyncio.gather(*tasks)
        
        return results
    
    shazam_results = asyncio.run(shazam_it())
    
    for result in shazam_results:
        if "track" in result:
            max_song_length = max(max_song_length, len(result["track"]["title"]))


if config["songidentifiers"]["audD"]:
    async def audd_it() -> list:
        audd = songidentifiers.AudDIO(config["apikeys"]["audD"][0])
        print(config["apikeys"]["audD"][0])
        async with asyncio.TaskGroup() as tg:
            tasks = []
            for file in files:
                    tprint(f"AudDing {file}")
                    tasks.append(tg.create_task(audd.recognize(FILE_PATH+'/outputs/'+file)))
            results = await asyncio.gather(*tasks)
        
        return results
    
    while True:
        audd_results = asyncio.run(audd_it())
        if audd_results[0]["status"] == "error" and audd_results[0]["error"]["error_code"] == 900:
            print("AudD API Token invalid, removing and using next in list")
            
            with open(FILE_PATH+"config.json", "r+") as f:
                config = json.loads(f.read())
                audd_api_keys = config["apikeys"]["audD"]
                audd_api_keys.pop(0)
                config["apikeys"]["audD"] = audd_api_keys
                f.seek(0)
                f.truncate()
                f.write(json.dumps(config, indent=4))
        else:
            break

    for result in audd_results:
        if result["status"] == "success" and result["result"] != None:
            max_song_length = max(max_song_length, len(result["result"]["title"]))
            result["result"]["title"]




print("\nResults:\n--------\n")
s = ""

if config["songidentifiers"]["shazam"]:
    for i, result in enumerate(shazam_results):
        if "track" in result:
            s += f'[Shazam] [{files[i].removesuffix(".mp3")+"]":<23} Song: {result["track"]["title"]:<{max_song_length}} | Artist: {result["track"]["subtitle"]}\n'
        else:
            s += f'[Shazam] [{files[i].removesuffix(".mp3")+"]":<23} Song: {"NOT FOUND":<{max_song_length}} | Artist: NOT FOUND\n'

if config["songidentifiers"]["audD"]:
    for i, result in enumerate(audd_results):
        if result["status"] == "success" and result["result"] != None:
            s += f'[AudD]   [{files[i].removesuffix(".mp3")+"]":<23} Song: {result["result"]["title"]:<{max_song_length}} | Artist: {result["result"]["artist"]}\n'
        else:
            s += f'[AudD]   [{files[i].removesuffix(".mp3")+"]":<23} Song: {"NOT FOUND":<{max_song_length}} | Artist: NOT FOUND\n'
print(s)