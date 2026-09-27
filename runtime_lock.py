"""Hold a Windows byte-range lock while a data directory is in use."""
from pathlib import Path
import msvcrt

class DataLock:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.file=(self.root/'.instance.lock').open('a+b')
        self.file.seek(0)
        try:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.file.close()
            raise RuntimeError('This data folder is in use. Close the application before retrying.')
        if self.file.seek(0,2)==0:self.file.write(b'0');self.file.flush()
    def close(self):
        self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1);self.file.close()

if __name__=='__main__':
    lock=DataLock(Path(__file__).resolve().parent/'data');lock.close()
