from enum import IntEnum


class ErrorCode(IntEnum):
    INPUT = 2
    NO_CAPTIONS = 3
    INACCESSIBLE = 4
    AUDIO = 5
    TRANSCRIPTION = 6
    MODEL_DOWNLOAD_REQUIRED = 7
    MODEL = 8
    OUTPUT = 9
    DEPENDENCY = 10
    CAPTION_LOOKUP = 11


class TranscriptError(Exception):
    def __init__(self, code: ErrorCode, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details
