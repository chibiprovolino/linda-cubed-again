"""Structural checks for the two build stages. These do not test gameplay."""
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dialogue as b
import doctor_event as doctor


def read(image, lba, n):
    raw = image[lba * 2352:(lba + n) * 2352]
    return b"".join(raw[i + 24:i + 2072] for i in range(0, len(raw), 2352))


def sectors_valid(image, lbas):
    for lba in lbas:
        raw = image[lba * 2352:(lba + 1) * 2352]
        assert doctor.sector(lba, raw[24:2072], raw[16:20]) == raw, lba


def dialogue_stage(source, stage):
    """Compare the dialogue-only image with the source BIN."""
    old, new = source.read_bytes(), stage.read_bytes()
    start = len(old) // 2352
    h0, h1 = read(old, 387, 35), read(new, start, 35)
    changed, preserved = [], 0
    for slot in range(768):
        a, n, stamp, cs = struct.unpack_from("<4I", h0, slot * 16)
        aa, nn, ss, cc = struct.unpack_from("<4I", h1, slot * 16)
        if not n:
            assert (a, n, stamp, cs) == (aa, nn, ss, cc)
            continue
        x, y = read(old, 387 + a, n), read(new, start + aa, nn)
        assert doctor.checkword(x) == cs and doctor.checkword(y) == cc and stamp == ss
        if x == y:
            preserved += 1
            continue
        assert slot != 71
        _, _, xm = b.directory(x)
        _, _, ym = b.directory(y)
        assert xm.keys() == ym.keys()
        assert all(xm[k] == ym[k] for k in xm if k != b"PROG.BIN")
        xp, xg = b.pointer_groups(xm[b"PROG.BIN"])
        yp, yg = b.pointer_groups(ym[b"PROG.BIN"])
        assert len(xg) == len(yg)
        for (_, xr), (_, yr) in zip(xg, yg):
            # Only trailing alignment padding may add empty records.
            while xr and not xr[-1]:
                xr.pop()
            while yr and not yr[-1]:
                yr.pop()
            assert len(xr) == len(yr), (slot, len(xr), len(yr))
        assert xm[b"PROG.BIN"][:xp[0][0]] == ym[b"PROG.BIN"][:yp[0][0]]
        code0 = bytearray(xm[b"PROG.BIN"][:xg[0][0]])
        code1 = bytearray(ym[b"PROG.BIN"][:xg[0][0]])
        for p, _ in xp:
            code0[p:p + 2] = code1[p:p + 2]
        if slot == 600:
            code0[0x9E8:0x9EB] = code1[0x9E8:0x9EB]
        assert code0 == code1, slot
        changed.append(slot)
    assert preserved + len(changed) == 413
    touched = [lba for lba in range(start)
               if old[lba * 2352:(lba + 1) * 2352] != new[lba * 2352:(lba + 1) * 2352]]
    assert touched == [16, 23]
    assert struct.unpack_from("<I", read(new, 16, 1), 80)[0] == len(new) // 2352
    sectors_valid(new, [16, 23] + list(range(start, len(new) // 2352)))
    return {"active_archives_checked": 413, "dialogue_archives_changed": len(changed),
            "dialogue_archives_unchanged": preserved, "non_program_assets_unchanged": True,
            "original_disc_sectors_modified": touched, "new_sector_edc_ecc_valid": True}


def doctor_stage(before, final):
    """Compare the final image with the dialogue-only image it was made from."""
    new = final.read_bytes()
    n0, n1 = len(before) // 2352, len(new) // 2352
    iso = read(new, 23, 1)
    entry = iso.index(b"LINDA.MIC;1") - 33
    mic = doctor.u32(iso, entry + 2)
    touched = [lba for lba in range(n0)
               if before[lba * 2352:(lba + 1) * 2352] != new[lba * 2352:(lba + 1) * 2352]]
    assert touched == [16, 23, mic], touched
    sectors_valid(new, touched + list(range(n0, n1)))
    assert struct.unpack_from("<I", read(new, 16, 1), 80)[0] == n1
    assert doctor.u32(iso, entry + 10) == (n1 - mic) * 2048
    h0, h1 = read(before, mic, 35), read(new, mic, 35)
    for slot in range(768):
        e0 = struct.unpack_from("<4I", h0, slot * 16)
        e1 = struct.unpack_from("<4I", h1, slot * 16)
        if slot != 71:
            assert e0 == e1
            if e1[1]:
                assert doctor.checkword(read(new, mic + e1[0], e1[1])) == e1[3]
            continue
        x, y = read(before, mic + e0[0], e0[1]), read(new, mic + e1[0], e1[1])
        assert e1[0] + e1[1] == n1 - mic and doctor.checkword(y) == e1[3] and e0[2] == e1[2]
        _, _, xm = b.directory(x)
        _, _, ym = b.directory(y)
        assert list(xm) == list(ym)
        assert all(xm[k] == ym[k] for k in xm if k != b"PROG.BIN")
        want, got = doctor.program(xm[b"PROG.BIN"]), ym[b"PROG.BIN"]
        assert got[:len(want)] == want and not any(got[len(want):]) and len(got) - len(want) < 4
    return {"doctor_room_assets_unchanged": True, "doctor_sectors_appended": n1 - n0}
