"""Supervised Redis launcher; self-heals a missing system binary on pod resume."""
import os, shutil, subprocess, time
from urllib.parse import urlparse
from pathlib import Path
from core.config import setting

def locate_binary():
    for _ in range(10):
        binary = shutil.which('redis-server')
        if binary: return binary
        time.sleep(2)
    env = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}
    subprocess.run(['apt-get', 'update', '-qq'], check=True, env=env)
    subprocess.run(['apt-get', 'install', '-y', '-qq', '--no-install-recommends', 'redis-server', 'redis-tools'], check=True, env=env)
    binary = shutil.which('redis-server')
    if not binary: raise SystemExit('redis-server unavailable after installation attempt')
    return binary

url = urlparse(setting('REDIS_URL'))
data = Path(__file__).parent / 'runtime-data'; data.mkdir(exist_ok=True)
binary = locate_binary()
if shutil.which('redis-cli'):
    # A distro postinst may have daemonized a stray instance on our port; stop it so the supervised one owns it.
    subprocess.run(['redis-cli', '-h', url.hostname, '-p', str(url.port), 'shutdown', 'nosave'], capture_output=True)
os.execv(binary, [binary, '--bind', url.hostname, '--port', str(url.port), '--protected-mode', 'yes', '--appendonly', 'yes', '--appendfsync', 'everysec', '--dir', str(data)])
