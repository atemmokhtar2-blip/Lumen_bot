"""
Builders package — low-level file and directory creators.

Generators delegate physical file creation to builders so that
generators stay focused on *what* to produce while builders handle
*how* it is written.  All builders implement the
:class:`~core.contracts.Builder` contract.
"""

from .directory_builder import DirectoryBuilder
from .file_builder import FileBuilder
from .python_module_builder import PythonModuleBuilder

__all__ = [
    "DirectoryBuilder",
    "FileBuilder",
    "PythonModuleBuilder",
]
