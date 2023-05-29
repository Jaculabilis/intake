"""
Common exception types.
"""


class IntakeException(Exception):
    """
    Base class for intake application exceptions.
    """


class InvalidConfigException(IntakeException):
    """
    Could not interact with a source because the source's config was not valid.
    """


class SourceUpdateException(Exception):
    """
    The source update process did not return valid data and signal success.
    """
