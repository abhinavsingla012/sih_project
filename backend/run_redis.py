import os
from urllib.parse import urlparse
from pathlib import Path
from core.config import setting
url=urlparse(setting('REDIS_URL'))
data=Path(__file__).parent/'runtime-data';data.mkdir(exist_ok=True)
os.execvp('redis-server',['redis-server','--bind',url.hostname,'--port',str(url.port),'--protected-mode','yes','--appendonly','yes','--appendfsync','everysec','--dir',str(data)])