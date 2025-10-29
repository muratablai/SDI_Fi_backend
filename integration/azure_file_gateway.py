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

def _nz(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    return s if s else None

class AzureFileGateway:
    def __init__(
        self,
        *,
        connection_string: Optional[str] = None,
        account_name: Optional[str] = None,
        account_key: Optional[str] = None,
        sas_url: Optional[str] = None,
        share_name: str,
        base_dir: str = "",
    ):
        connection_string = _nz(connection_string)
        account_name = _nz(account_name)
        account_key = _nz(account_key)
        sas_url = _nz(sas_url)

        if connection_string:
            self.svc = ShareServiceClient.from_connection_string(connection_string)
        elif sas_url:
            self.svc = ShareServiceClient(account_url=sas_url)
        elif account_name and account_key:
            account_url = f"https://{account_name}.file.core.windows.net"
            self.svc = ShareServiceClient(account_url=account_url, credential=account_key)
        else:
            raise ValueError(
                "AzureFileGateway: missing credentials. Provide connection string, or (account_name+account_key), or SAS URL."
            )

        share_name = (share_name or "").strip()
        if not share_name:
            raise ValueError("AzureFileGateway: AZURE_FILES_SHARE must be set.")

        self.share = self.svc.get_share_client(share_name)
        self.base_dir = (base_dir or "").strip("/")

    # ---------- internal helpers ----------
    def _resolve_path(self, path: str) -> str:
        path = (path or "").strip("/")
        if self.base_dir and path:
            return f"{self.base_dir}/{path}"
        if self.base_dir and not path:
            return self.base_dir
        return path  # may be ""

    def _file_client_full(self, path: str, filename: str):
        """
        Build a FileClient from the share directly using a full, slash-joined path.
        This matches your working sample: share.get_file_client("<full/path>").
        """
        full_dir = self._resolve_path(path)
        if full_dir:
            full_path = f"{full_dir}/{filename}".strip("/")
        else:
            full_path = filename.strip("/")
        return self.share.get_file_client(full_path)

    def _dir_client(self, path: str):
        full = self._resolve_path(path)
        if not full:
            # root: treat separately; there isn't a distinct "root dir client"
            return None
        return self.share.get_directory_client(full)

    def _file_client(self, path: str, filename: str):
        full = self._resolve_path(path)
        if not full:
            # root file
            return self.share.get_file_client(filename)
        d = self.share.get_directory_client(full)
        return d.get_file_client(filename)

    # ---------- public API ----------
    def ensure_dir(self, dir_path: str):
        full = self._resolve_path(dir_path)
        if not full:
            # root: nothing to create
            return None
        d = self.share.get_directory_client(full)
        try:
            d.create_directory()
        except ResourceExistsError:
            pass
        return d

    def upload_bytes(self, dir_path: str, filename: str, data: bytes):
        full_dir = self._resolve_path(dir_path)
        if full_dir:
            # create missing directories for uploads
            self.ensure_dir(dir_path)
        f = self._file_client_full(dir_path, filename)
        f.upload_file(io.BytesIO(data))

    def download_bytes(self, dir_path: str, filename: str) -> bytes:
        f = self._file_client_full(dir_path, filename)
        return f.download_file().readall()

    def list_files(self, dir_path: str) -> List[FileInfo]:
        """
        Lists files (not subdirectories) in a directory. Works for root as well.
        """
        full = self._resolve_path(dir_path)
        out: List[FileInfo] = []
        if full:
            d = self.share.get_directory_client(full)
            iterator = d.list_directories_and_files()
        else:
            iterator = self.share.list_directories_and_files()  # root
        for entry in iterator:
            if not getattr(entry, "is_directory", False):
                out.append(FileInfo(name=entry.name, size=getattr(entry, "size", 0)))
        return out

    def list_dirs_and_files(self, dir_path: str):
        """
        Returns {"dirs": [...], "files": [FileInfo(...)]} for the given path (supports root).
        """
        full = self._resolve_path(dir_path)
        dirs, files = [], []
        if full:
            d = self.share.get_directory_client(full)
            iterator = d.list_directories_and_files()
        else:
            iterator = self.share.list_directories_and_files()  # root
        for entry in iterator:
            if getattr(entry, "is_directory", False):
                dirs.append(entry.name)
            else:
                files.append(FileInfo(name=entry.name, size=getattr(entry, "size", 0)))
        return {"dirs": dirs, "files": files}

    def read_head(self, dir_path: str, filename: str, nbytes: int = 1024) -> bytes:
        f = self._file_client_full(dir_path, filename)
        stream = f.download_file(offset=0, length=max(1, nbytes))
        return stream.readall()

    def exists(self, dir_path: str) -> tuple[bool, Optional[str]]:
        """
        Checks directory existence. For root, use share properties.
        Returns (exists, error_message_or_None).
        """
        full = self._resolve_path(dir_path)
        try:
            if not full:
                # root exists if we can fetch share properties
                self.share.get_share_properties()
                return True, None
            # subdirectory props
            d = self.share.get_directory_client(full)
            d.get_directory_properties()
            return True, None
        except Exception as e:
            return False, str(e)
