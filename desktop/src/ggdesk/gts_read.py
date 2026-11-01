"""Independent record-level reader for .m20 (GTS) job bytes.

This is the seed of the output gate's decoder (build plan section 9). It is
written from docs/GTS_FORMAT.md, not from the builder, and walks every byte:

    94-byte header
    records: FF FD <op:2> <arg:u16 BE>       6-byte opcode command
             <pw1 pw2 speed accel dx dy>     12-byte segment (int16 BE x 6)

It refuses (raises GtsFormatError) rather than guessing on anything it
cannot account for, so a gate built on it never passes unexplained bytes.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

HEADER_LEN = 94
MAGIC = b"!MM88;"
MODEL_CODE_OFFSET = 0x24
CMD_PREFIX = b"\xff\xfd"


class GtsFormatError(ValueError):
    """The bytes are not a well-formed GTS job."""


@dataclass(frozen=True)
class Command:
    offset: int
    op: str
    arg: int


@dataclass(frozen=True)
class Segment:
    offset: int
    pw1: int
    pw2: int
    speed: int
    accel: int
    dx: int
    dy: int


Record = Command | Segment


@dataclass
class Job:
    model_code: int
    records: list[Record] = field(default_factory=list)

    @property
    def commands(self) -> list[Command]:
        return [r for r in self.records if isinstance(r, Command)]

    def setup(self) -> list[tuple[str, int]]:
        """Opcode commands before the first segment, in order."""
        out: list[tuple[str, int]] = []
        for r in self.records:
            if isinstance(r, Segment):
                break
            out.append((r.op, r.arg))
        return out

    def cut_points(self) -> list[tuple[int, int]]:
        """Head positions while the tool is down: from each PD to the next PU."""
        x = y = 0
        down = False
        out: list[tuple[int, int]] = []
        for r in self.records:
            if isinstance(r, Segment):
                x += r.dx
                y += r.dy
                if down:
                    out.append((x, y))
            elif r.op == "PD":
                down = True
                out.append((x, y))
            elif r.op == "PU":
                down = False
        return out

    def positions(self) -> list[tuple[int, int]]:
        """Head position after every segment, integrated from home (0, 0)."""
        x = y = 0
        out: list[tuple[int, int]] = []
        for r in self.records:
            if isinstance(r, Segment):
                x += r.dx
                y += r.dy
                out.append((x, y))
        return out


def read_job(data: bytes) -> Job:
    if len(data) < HEADER_LEN:
        raise GtsFormatError(f"{len(data)} bytes is shorter than the {HEADER_LEN}-byte header")
    if data[:6] != MAGIC:
        raise GtsFormatError(f"header magic {data[:6]!r} is not {MAGIC!r}")
    (model_code,) = struct.unpack_from(">H", data, MODEL_CODE_OFFSET)
    job = Job(model_code=model_code)
    pos = HEADER_LEN
    while pos < len(data):
        if data[pos:pos + 2] == CMD_PREFIX:
            if pos + 6 > len(data):
                raise GtsFormatError(f"truncated command at offset {pos}")
            op_bytes = data[pos + 2:pos + 4]
            if not all(0x20 < b < 0x7F for b in op_bytes):
                raise GtsFormatError(f"non-ASCII opcode {op_bytes!r} at offset {pos}")
            (arg,) = struct.unpack_from(">H", data, pos + 4)
            job.records.append(Command(pos, op_bytes.decode("ascii"), arg))
            pos += 6
        else:
            if pos + 12 > len(data):
                raise GtsFormatError(f"truncated segment at offset {pos}")
            job.records.append(Segment(pos, *struct.unpack_from(">hhhhhh", data, pos)))
            pos += 12
    return job
