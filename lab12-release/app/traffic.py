import concurrent.futures
import time
import urllib.error
import urllib.request


def checkout():
    try:
        with urllib.request.urlopen(urllib.request.Request('http://shop:8000/checkout',
                                                          method='POST', data=b''), timeout=10) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError):
        pass


with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    while True:
        pool.submit(checkout)
        time.sleep(.5)
