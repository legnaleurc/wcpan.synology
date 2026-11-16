from .types import (
    SynologyChildRef,
    SynologyFileId,
    SynologyLookupRef,
    SynologyNodeRef,
    SynologyParentRef,
    SynologyPath,
)


def to_path_parameter_value(value: SynologyLookupRef) -> str:
    if isinstance(value, SynologyPath):
        return value.path
    if isinstance(value, SynologyFileId):
        return f"id:{value.file_id}"
    if isinstance(value, SynologyChildRef):
        return f"{to_parent_parameter_value(value.parent_ref)}/{value.name}"
    return f"link:{value.permanent_link}"


def to_file_identifier_value(value: SynologyNodeRef) -> str:
    if isinstance(value, SynologyFileId):
        return f"id:{value.file_id}"
    return f"link:{value.permanent_link}"


def to_parent_parameter_value(value: SynologyParentRef) -> str:
    if isinstance(value, SynologyPath):
        return value.path
    # Child-addressing with `id:<id>/<name>` is already documented and
    # validated, so normalize file-id parents to that form when composing.
    return f"id:{value.file_id}"
