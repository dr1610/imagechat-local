"""Copy stopped-app data to a fresh install; never overwrite either side."""
from pathlib import Path
import os,shutil,sys,uuid
from runtime_lock import DataLock

def migrate(old, new):
    old=Path(old).resolve();new=Path(new).resolve()
    source=old/'data';target=new/'data'
    if old==new or old in new.parents or new in old.parents:raise ValueError('Use separate installation folders.')
    if target.exists():raise ValueError('Destination data already exists. Use a fresh unstarted install.')
    if not source.is_dir():raise ValueError('Source data folder not found.')
    def linked(p):return p.is_symlink() or bool(getattr(p.stat(follow_symlinks=False),'st_file_attributes',0)&0x400)
    if linked(source) or any(linked(p) for p in source.rglob('*')):raise ValueError('Linked files or folders are not imported.')
    if not (source/'.instance.lock').exists():raise ValueError('Source predates the data lock. Use the manual offline backup procedure in UPDATING.md.')
    lock=DataLock(source)
    staging=new/('data-import-'+uuid.uuid4().hex)
    try:
        shutil.copytree(source,staging,ignore=shutil.ignore_patterns('.instance.lock'))
        # Windows rename refuses an existing destination, including concurrent app startup.
        os.rename(staging,target)
    finally:lock.close()
    print('Copied data. Original installation remains unchanged.')

if __name__=='__main__':migrate(sys.argv[1],Path(__file__).resolve().parent)
