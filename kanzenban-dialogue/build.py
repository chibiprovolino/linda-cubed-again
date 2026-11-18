"""Build the experimental Kanzenban dialogue image from the v0.95.9 English BIN.

Usage: python build.py original.bin output-directory

Steps: apply the dialogue draft (dialogue.py), check the result, add the
playing-doctor event to MIC slot 71 (doctor_event.py), check again, and write
"Kanzenban dialogue.bin/.cue" with a build report. Python standard library only.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dialogue
import doctor_event as doctor
import verify

NAME = "Kanzenban dialogue"
SLOT = 71


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def add_doctor_event(path):
    """Append the expanded slot-71 archive to the end of the MIC, in place."""
    with path.open("r+b") as f:
        def raw(lba):
            f.seek(lba * 2352)
            return f.read(2352)

        def data(lba, n):
            return b"".join(raw(i)[24:2072] for i in range(lba, lba + n))

        def write(lba, blob, sub):
            for k in range(0, len(blob), 2048):
                f.seek((lba + k // 2048) * 2352)
                f.write(doctor.sector(lba + k // 2048, blob[k:k + 2048], sub))

        total = path.stat().st_size // 2352
        pvd, iso = bytearray(data(16, 1)), bytearray(data(23, 1))
        assert doctor.u32(pvd, 80) == total
        pos = 0
        while iso[pos]:
            if iso[pos + 33:pos + 33 + iso[pos + 32]] == b"LINDA.MIC;1":
                break
            pos += iso[pos]
        assert iso[pos], "LINDA.MIC not found"
        mic, size = doctor.u32(iso, pos + 2), doctor.u32(iso, pos + 10)
        assert size % 2048 == 0 and mic + size // 2048 == total
        head = bytearray(data(mic, 1))
        start, count, _, csum = struct.unpack_from("<4I", head, SLOT * 16)
        old = data(mic + start, count)
        assert csum == doctor.checkword(old)
        bank = doctor.rebuild(old)
        newcount = len(bank) // 2048

        struct.pack_into("<II", head, SLOT * 16, size // 2048, newcount)
        struct.pack_into("<I", head, SLOT * 16 + 12, doctor.checkword(bank))
        newsize = size + len(bank)
        struct.pack_into("<I", iso, pos + 10, newsize)
        struct.pack_into(">I", iso, pos + 14, newsize)
        struct.pack_into("<I", pvd, 80, total + newcount)
        struct.pack_into(">I", pvd, 84, total + newcount)
        write(total, bank, raw(mic + start)[16:20])
        write(mic, head, raw(mic)[16:20])
        write(23, iso, raw(23)[16:20])
        write(16, pvd, raw(16)[16:20])
        assert data(total, newcount) == bank
    return {"slot": SLOT, "archive_lba": total, "archive_sectors": newcount}


def build(source, outdir):
    final = outdir / (NAME + ".bin")
    if final.exists():
        raise FileExistsError(final)
    stage, report = dialogue.build(source, outdir)
    checks = verify.dialogue_stage(source, stage)
    stage_copy = stage.read_bytes()
    report["doctor_event"] = add_doctor_event(stage)
    checks.update(verify.doctor_stage(stage_copy, stage))
    del stage_copy
    stage.rename(final)
    stage.with_suffix(".cue").unlink()
    (outdir / (NAME + ".cue")).write_text(
        f'FILE "{NAME}.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    report["source_sha256"] = file_sha(source)
    report["output_sha256"] = file_sha(final)
    report["checks"] = checks
    (outdir / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Wrote", final)
    print("SHA-256", report["output_sha256"])


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python build.py original.bin output-directory")
    build(Path(sys.argv[1]), Path(sys.argv[2]))
