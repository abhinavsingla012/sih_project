"""Reinstall supervised local-demo processes from persistent configuration."""
from pathlib import Path
import shutil,subprocess
source=Path(__file__).with_name('samanvay-supervisor.conf')
if not shutil.which('redis-server'):
    subprocess.run(['apt-get','update','-qq'],check=True)
    subprocess.run(['apt-get','install','-y','redis-server','redis-tools'],check=True)
shutil.copyfile(source,'/etc/supervisor/conf.d/samanvay.conf')
subprocess.run(['supervisorctl','reread'],check=True)
subprocess.run(['supervisorctl','update'],check=True)