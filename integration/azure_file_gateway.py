# integration/azure_file_gateway.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import io
from azure.storage.fileshare import ShareServiceClient
from azure.core.exceptions import ResourceExistsError

@dataclass
class FileInfo:
    name: str
    size: int

class AzureFileGateway:
    def __init__(
        self,
        *,
        account_name: Optional[str] = None,
        account_key: Optional[str] = None,
        sas_url: Optional[str] = None,
        share_name: str,
        base_dir: str = "",
    ):
        if sas_url:
            self.svc = ShareServiceClient(account_url=sas_url)
        else:
            account_url = f"https://{account_name}.file.core.windows.net"
            self.svc = ShareServiceClient(account_url=account_url, credential=account_key)
        self.share = self.svc.get_share_client(share_name)
        self.base_dir = base_dir.strip("/")

    def _dir_client(self, path: str):
        full = f"{self.base_dir}/{path}".strip("/")
        return self.share.get_directory_client(full)

    def _file_client(self, path: str, filename: str):
        d = self._dir_client(path)
        return d.get_file_client(filename)

    def ensure_dir(self, dir_path: str):
        d = self._dir_client(dir_path)
        try:
            d.create_directory()
        except ResourceExistsError:
            pass
        return d

    def upload_bytes(self, dir_path: str, filename: str, data: bytes):
        d = self.ensure_dir(dir_path)
        f = d.get_file_client(filename)
        stream = io.BytesIO(data)
        f.upload_file(stream)

    def download_bytes(self, dir_path: str, filename: str) -> bytes:
        f = self._file_client(dir_path, filename)
        return f.download_file().readall()

    def list_files(self, dir_path: str) -> List[FileInfo]:
        d = self.ensure_dir(dir_path)
        out: List[FileInfo] = []
        for entry in d.list_directories_and_files():
            if not getattr(entry, "is_directory", False):
                out.append(FileInfo(name=entry.name, size=entry.size))
        return out
