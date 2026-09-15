"""Reinstall supervised local-demo processes from persistent configuration."""
from pathlib import Path
import os,shutil,subprocess
source=Path(__file__).with_name('samanvay-supervisor.conf')
if not shutil.which('redis-server'):
    env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'}
    subprocess.run(['apt-get','update','-qq'],check=True,env=env)
    subprocess.run(['apt-get','install','-y','-qq','--no-install-recommends','redis-server','redis-tools'],check=True,env=env)
subprocess.run(['python',str(Path(__file__).parents[1]/'backend'/'setup_local.py')],check=True)
shutil.copyfile(source,'/etc/supervisor/conf.d/samanvay.conf')
subprocess.run(['supervisorctl','reread'],check=True)
subprocess.run(['supervisorctl','update'],check=True)
subprocess.run(['supervisorctl','start','samanvay-redis','samanvay-events'])
