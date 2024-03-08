import asyncio
import aiohttp
from bs4 import BeautifulSoup


class AudDIO:
    """Async library to recognize a song by file using https://audd.io/ API.\nNOTE: It really likes to ban your ip or similar randomly"""

    def __init__(self, api_key: str):
        self.__api_key__ = api_key

    async def recognize(self, filepath: str):
        """Try to recognize a song by file\n
            filepath - path to file of song
        """

        async with aiohttp.ClientSession() as s:
            with open(filepath, "rb") as f:
                data = {
                    "file": f,
                    "api_token": self.__api_key__
                }
                
                async with s.post("https://api.audd.io/", data=data) as resp:
                    return await resp.json()

    @staticmethod
    async def send_verification_email(s: aiohttp.ClientSession, email: str, password: str) -> str | None:
        """
            Setup the account creation, after this call your mail will get a verification email\n
            email - email name (e.g. test@gmail.com)\n
            password - password for the audd account\n
            returns the "state" needed for the next step if success, None if failure
        """

        async with aiohttp.ClientSession() as temp_s: # needs to be different session for some reason
            r = await temp_s.get("https://oauth.audd.io/3rd/auth0?redirect_url=https://dashboard.audd.io/api/auth/-89d21759", headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://dashboard.audd.io/",
            })
        
        start_url = str(r.history[1].url)
        

        if True:
            r = await s.get(start_url)
            if r.status != 200:
                return None
            
            soup = BeautifulSoup(await r.text(), "lxml")
            state = soup.find("input")["value"]
            

            r = await s.get("https://auth.audd.io/u/signup/identifier?state="+state, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://dashboard.audd.io/"
            })
            
            
            if r.status != 200:
                return None

            signup_identifier_data = {
                "state": state,
                "email": email,
                "action": "default"
            }
            r = await s.post("https://auth.audd.io/u/signup/identifier?state="+state, data=signup_identifier_data, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://auth.audd.io/u/signup/identifier?state="+state,
                "Content-Type": "application/x-www-form-urlencoded"
            })
            

            if r.status != 200:
                return None
            
            signup_password_data = {
                "state": state,
                "strengthPolicy": "good",
                "complexityOptions.minLength": "8",
                "email": email,
                "password": password,
                "action": "default"
            }
            r =  await s.post("https://auth.audd.io/u/signup/password?state="+state, data=signup_password_data, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://auth.audd.io/u/signup/password?state="+state,
                "Content-Type": "application/x-www-form-urlencoded"
            })

            
            if not r.status in (401,):# 500, 200): # for some reason only works if it is 401, 200 doesnt send the email, 500 breaks it later on
                return None
            
            return s, state


      
    @staticmethod
    async def verify_account(s: aiohttp.ClientSession, email: str, password: str, verifcation_link: str, get_api_key: bool=True, state: str="hKFo2SA2b1hfa2FfTG9YSlNkUmtvSkRIRDJuS1REVDZKX3RVbKFur3VuaXZlcnNhbC1sb2dpbqN0aWTZIHJiTUh4WnlzcmtGLXA4STVhNWUtSF9UZnNaOVBDRXZVo2NpZNkgcTZGSW9qbEp0aVlTRm1TQ0t1Z3gxVjNKeUZwaVdKblA") -> str | bool:
        """
            Verifies the account using the verifcation link created in send_verification_email, also gets the api key by default\n
            email - email name (e.g. test@gmail.com)\n
            password - password for the audd account\n
            verification_link - the verification link in the email\n
            get_api_key - return the api key of the account\n
            returns the api key if get_api_key is true, otherwise True if success, False if failure\n
            there is no reason to not get the api key since its the only reason I do this, you can of course extend the functionality for with a single login function
        """
        r = await s.get(verifcation_link)

        
        if r.status != 200:
            return False
    
        soup = BeautifulSoup(await r.text(), "lxml")

        r = await s.post(str(r.url), data={"state": soup.find("input")["value"]}) # https://auth.audd.io/u/email-verification?ticket = 
        

        if r.status != 200:
            return False
        
        r = await s.post("https://auth.audd.io/u/login/identifier?state="+state, data={
            "state": state,
            "username": email,
            "js-available": "true",
            "webauthn-available": "true",
            "is-brave": "false",
            "webauthn-platform-available": "false",
            "action": "default"
        })


        r = await s.post("https://auth.audd.io/u/login/password?state="+state, data={
            "state": state,
            "username": email,
            "password": password,
            "action": "default"
        })

        
        if r.status != 200:
            return False
    

        if not get_api_key:
            return True
        

        r = await s.get("https://dashboard.audd.io/api/js.php?url=https%3A%2F%2Fdashboard.audd.io%2F")
        
        if r.status != 200:
            return False
        
        content = await r.text()
        

        first_split = content.split("copyTextToClipboard('", maxsplit=1)
        if len(first_split) == 1: # if no api key
            return False
        
        
        return first_split[1].split("'", maxsplit=1)[0]
    

# generate audio api_keys which is highly unreliable (due to their auth tho)
if __name__ == "__main__":
    from temp_mails import temp_mailboxdotcom # requires some form of mail api, you may need to implement a wrapper
    from random import choices
    from string import ascii_lowercase, ascii_uppercase, digits
    import os

    async def main():

        email = temp_mailboxdotcom.Mail()
        password = "".join(choices(ascii_lowercase, k=4)+choices(ascii_uppercase, k=4)+choices(digits, k=4))+"@"
        print(email.email, password)
           
        async with aiohttp.ClientSession() as session:
            session, state = await AudDIO.send_verification_email(session, email.email, password)
            
            verification_email = email.wait_for_new_email()
            if verification_email:
                verfiy_link = BeautifulSoup(verification_email["content"], "lxml").find("span").a["href"]
                print(verfiy_link)
                api_key = await AudDIO.verify_account(session, email.email, password, verfiy_link)
                
                print(api_key)
                if api_key:
                    FILE_PATH = os.path.dirname(os.path.realpath(__file__))
                    with open(FILE_PATH+"/api_tokens.csv", "a") as f: # you'll need to manually place the codes in config.json
                        f.write(f"{api_key}, {email.email}, {password}\n")
        
    while True:
        asyncio.run(main())
#         time.sleep(60) 
#         # idk, it seems like that at point 5 there is a cooldown or smth
#         # need to try after some time while changing nothing
#         # try without headers (dont believe they are for anything)
#         # ratelimit hits hard