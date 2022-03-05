import logging
import time
from functools import wraps


def timeit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        name = func.__name__
        logging.debug("start: %s.", name)
        start = time.time()
        try:
            result = func(*args, **kwargs)
        finally:
            elapsed = time.time() - start
            logging.debug("finished: %s (took %.3f s).", name, elapsed)
        return result

    return wrapper
