from contextlib import contextmanager
import os
import tempfile
import time
from typing import Iterator
import unittest


def stress_test(func):
    @unittest.skipIf(int(os.getenv("TEST_LEVEL", 0)) < 1, "Stress test")
    def inner(*args, **kwargs):
        return func(*args, **kwargs)

    return inner


@contextmanager
def temp_file_with_content(content: bytes) -> Iterator[str]:
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        tmp.write(content)
        tmp.close()
        yield tmp.name
    finally:
        os.remove(tmp.name)