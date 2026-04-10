from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TermCandIDPair(_message.Message):
    __slots__ = ("term", "candidateID")
    TERM_FIELD_NUMBER: _ClassVar[int]
    CANDIDATEID_FIELD_NUMBER: _ClassVar[int]
    term: int
    candidateID: int
    def __init__(self, term: _Optional[int] = ..., candidateID: _Optional[int] = ...) -> None: ...

class RequestVoteRequest(_message.Message):
    __slots__ = ("candidate", "lastLogIndex", "lastLogTerm")
    CANDIDATE_FIELD_NUMBER: _ClassVar[int]
    LASTLOGINDEX_FIELD_NUMBER: _ClassVar[int]
    LASTLOGTERM_FIELD_NUMBER: _ClassVar[int]
    candidate: TermCandIDPair
    lastLogIndex: int
    lastLogTerm: int
    def __init__(self, candidate: _Optional[_Union[TermCandIDPair, _Mapping]] = ..., lastLogIndex: _Optional[int] = ..., lastLogTerm: _Optional[int] = ...) -> None: ...

class TermResultPair(_message.Message):
    __slots__ = ("term", "verdict")
    TERM_FIELD_NUMBER: _ClassVar[int]
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    term: int
    verdict: bool
    def __init__(self, term: _Optional[int] = ..., verdict: bool = ...) -> None: ...

class RequestVoteResponse(_message.Message):
    __slots__ = ("result",)
    RESULT_FIELD_NUMBER: _ClassVar[int]
    result: TermResultPair
    def __init__(self, result: _Optional[_Union[TermResultPair, _Mapping]] = ...) -> None: ...

class TermLeaderIDPair(_message.Message):
    __slots__ = ("term", "leaderID")
    TERM_FIELD_NUMBER: _ClassVar[int]
    LEADERID_FIELD_NUMBER: _ClassVar[int]
    term: int
    leaderID: int
    def __init__(self, term: _Optional[int] = ..., leaderID: _Optional[int] = ...) -> None: ...

class LogEntry(_message.Message):
    __slots__ = ("term", "command")
    TERM_FIELD_NUMBER: _ClassVar[int]
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    term: int
    command: str
    def __init__(self, term: _Optional[int] = ..., command: _Optional[str] = ...) -> None: ...

class AppendEntriesRequest(_message.Message):
    __slots__ = ("leader", "prevLogIndex", "prevLogTerm", "entries", "leaderCommit")
    LEADER_FIELD_NUMBER: _ClassVar[int]
    PREVLOGINDEX_FIELD_NUMBER: _ClassVar[int]
    PREVLOGTERM_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    LEADERCOMMIT_FIELD_NUMBER: _ClassVar[int]
    leader: TermLeaderIDPair
    prevLogIndex: int
    prevLogTerm: int
    entries: _containers.RepeatedCompositeFieldContainer[LogEntry]
    leaderCommit: int
    def __init__(self, leader: _Optional[_Union[TermLeaderIDPair, _Mapping]] = ..., prevLogIndex: _Optional[int] = ..., prevLogTerm: _Optional[int] = ..., entries: _Optional[_Iterable[_Union[LogEntry, _Mapping]]] = ..., leaderCommit: _Optional[int] = ...) -> None: ...

class AppendEntriesResponse(_message.Message):
    __slots__ = ("result",)
    RESULT_FIELD_NUMBER: _ClassVar[int]
    result: TermResultPair
    def __init__(self, result: _Optional[_Union[TermResultPair, _Mapping]] = ...) -> None: ...

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetLeaderResponse(_message.Message):
    __slots__ = ("nodeId", "nodeAddress")
    NODEID_FIELD_NUMBER: _ClassVar[int]
    NODEADDRESS_FIELD_NUMBER: _ClassVar[int]
    nodeId: int
    nodeAddress: str
    def __init__(self, nodeId: _Optional[int] = ..., nodeAddress: _Optional[str] = ...) -> None: ...

class SuspendRequest(_message.Message):
    __slots__ = ("period",)
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    period: int
    def __init__(self, period: _Optional[int] = ...) -> None: ...

class SetValRequest(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class SetValResponse(_message.Message):
    __slots__ = ("verdict",)
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    verdict: bool
    def __init__(self, verdict: bool = ...) -> None: ...

class GetValRequest(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class GetValResponse(_message.Message):
    __slots__ = ("verdict", "value")
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    verdict: bool
    value: str
    def __init__(self, verdict: bool = ..., value: _Optional[str] = ...) -> None: ...
